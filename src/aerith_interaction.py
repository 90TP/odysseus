"""Aerith interaction state and orchestration.

Keeps Aerith's perception/action state separate from Odysseus' transport and
agent-loop machinery.  Odysseus can feed the latest visual observation and
conversation into this layer, while Aerith remains responsible for perception
and actions.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class VisualState:
    description: str = ""
    monitor_id: int | None = None
    timestamp: float = 0.0
    pending: bool = False

    @property
    def age(self) -> float:
        if not self.timestamp:
            return float("inf")
        return time.monotonic() - self.timestamp


@dataclass
class InteractionState:
    visual: VisualState = field(default_factory=VisualState)
    listening: bool = False
    speaking: bool = False
    acting: bool = False
    last_user_message: str = ""
    last_aerith_response: str = ""
    conversation: list[dict[str, str]] = field(default_factory=list)


class AerithInteraction:
    """Central interaction/orchestration layer for Aerith.

    The class deliberately has no FastAPI/UI dependency.  It can therefore be
    used by the desktop client, Odysseus' agent loop, voice input, and future
    perception workers without making those systems depend on each other.
    """

    def __init__(
        self,
        llm: Callable[[str], str],
        action_handler: Callable[[str, dict[str, Any]], Any] | None = None,
        max_history: int = 20,
    ) -> None:
        self.llm = llm
        self.action_handler = action_handler
        self.max_history = max(1, max_history)
        self.state = InteractionState()
        self._lock = threading.RLock()
        self._listeners: list[Callable[[InteractionState], None]] = []

    # ------------------------------------------------------------------
    # State listeners
    # ------------------------------------------------------------------

    def add_listener(self, callback: Callable[[InteractionState], None]) -> None:
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[InteractionState], None]) -> None:
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def _notify(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
            state = self.state
        for callback in listeners:
            try:
                callback(state)
            except Exception as exc:
                print(f"[INTERACTION] listener failed: {exc}", flush=True)

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------

    def vision_started(self) -> None:
        with self._lock:
            self.state.visual.pending = True
        self._notify()
        print("[INTERACTION] vision analysis started", flush=True)

    def vision_updated(self, monitor_id: int, description: str) -> None:
        with self._lock:
            self.state.visual = VisualState(
                description=str(description or "").strip(),
                monitor_id=monitor_id,
                timestamp=time.monotonic(),
                pending=False,
            )
        self._notify()
        print(f"[INTERACTION] vision updated monitor={monitor_id}", flush=True)

    def clear_vision(self) -> None:
        with self._lock:
            self.state.visual = VisualState()
        self._notify()

    # ------------------------------------------------------------------
    # Interaction state
    # ------------------------------------------------------------------

    def set_listening(self, value: bool) -> None:
        with self._lock:
            self.state.listening = bool(value)
        self._notify()

    def set_speaking(self, value: bool) -> None:
        with self._lock:
            self.state.speaking = bool(value)
        self._notify()

    def set_acting(self, value: bool) -> None:
        with self._lock:
            self.state.acting = bool(value)
        self._notify()

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def _build_context(self) -> str:
        with self._lock:
            visual = self.state.visual
            conversation = list(self.state.conversation)

        parts: list[str] = []

        if visual.description:
            age = visual.age
            if age < 5:
                freshness = "very recent"
            elif age < 30:
                freshness = "recent"
            elif age < 120:
                freshness = "somewhat stale"
            else:
                freshness = "stale"
            parts.append(
                "CURRENT VISUAL PERCEPTION:\n"
                f"{visual.description}\n"
                f"(Observation is {freshness}; {age:.0f}s old.)"
            )

        if visual.pending:
            parts.append(
                "A NEW VISUAL ANALYSIS IS CURRENTLY IN PROGRESS. "
                "Use the latest completed observation rather than waiting for it."
            )

        if conversation:
            history = conversation[-self.max_history :]
            lines = [
                f"{item['role'].upper()}: {item['content']}"
                for item in history
                if item.get("role") and item.get("content")
            ]
            if lines:
                parts.append("RECENT CONVERSATION:\n" + "\n".join(lines))

        return "\n\n".join(parts)

    # Public alias for consumers that need to inspect the prompt context.
    def build_context(self) -> str:
        return self._build_context()

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    def respond(self, user_message: str) -> str:
        user_message = str(user_message or "").strip()
        if not user_message:
            return ""

        print(f"[INTERACTION] User: {user_message}", flush=True)

        with self._lock:
            self.state.last_user_message = user_message
            self.state.conversation.append({"role": "user", "content": user_message})
            self._trim_history_locked()

        context = self._build_context()
        prompt = f"""
You are Aerith.

You are an interactive computer assistant.

You have access to:
- visual perception of the user's screen
- audio/user input
- computer interaction capabilities

Do not claim to have seen something unless it appears in the visual perception context.
Do not wait for a pending vision analysis. Use the most recent completed observation.
If an action is required, identify the action clearly for the action system.

{context}

USER:
{user_message}

Respond naturally and concisely.
""".strip()

        try:
            response = str(self.llm(prompt)).strip()
        except Exception as exc:
            response = "I ran into a problem processing that."
            print(f"[INTERACTION] LLM error: {exc}", flush=True)

        with self._lock:
            self.state.last_aerith_response = response
            self.state.conversation.append({"role": "assistant", "content": response})
            self._trim_history_locked()

        print("[INTERACTION] Response generated", flush=True)
        return response

    def _trim_history_locked(self) -> None:
        limit = self.max_history * 2
        if len(self.state.conversation) > limit:
            self.state.conversation = self.state.conversation[-limit:]

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def handle_action(self, action: str, payload: dict[str, Any] | None = None) -> Any:
        """Dispatch an Aerith action through the configured action handler."""
        if not self.action_handler:
            raise RuntimeError("AerithInteraction has no action handler")

        payload = dict(payload or {})
        self.set_acting(True)
        try:
            return self.action_handler(str(action), payload)
        finally:
            self.set_acting(False)

    def snapshot(self) -> InteractionState:
        """Return a detached state snapshot suitable for UI listeners/tests."""
        with self._lock:
            visual = self.state.visual
            return InteractionState(
                visual=VisualState(
                    description=visual.description,
                    monitor_id=visual.monitor_id,
                    timestamp=visual.timestamp,
                    pending=visual.pending,
                ),
                listening=self.state.listening,
                speaking=self.state.speaking,
                acting=self.state.acting,
                last_user_message=self.state.last_user_message,
                last_aerith_response=self.state.last_aerith_response,
                conversation=list(self.state.conversation),
            )
