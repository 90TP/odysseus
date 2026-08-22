"""Native Agent-backed execution for the 3D Aerith companion.

The companion endpoint must use Odysseus' real agent loop rather than a plain
LLM completion.  This module is deliberately small: it reuses the existing
agent-loop/tool policy and only supplies Aerith-specific behavioural guidance
plus the tools she is explicitly authorised to use.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agent_loop import stream_agent_loop

logger = logging.getLogger(__name__)


AERITH_AGENT_DIRECTIVE = """You are Aerith, the user's interactive computer assistant.

You are operating in Odysseus Agent mode. You have access to the real computer
through the tools supplied to you by Odysseus. Those tools are real execution
interfaces, not examples or hypothetical capabilities.

BEHAVIOUR:
- When the user asks you to inspect, verify, find, read, create, edit, run,
  configure, test, or otherwise act on the computer, USE THE APPROPRIATE TOOL.
- Do not merely describe a command that could be run.
- Do not claim that you ran a command unless the tool actually returned its
  result.
- Do not invent usernames, hostnames, paths, command output, IP addresses,
  process IDs, file contents, or other environmental facts.
- If a tool returns an error, report the real error and adapt when possible.
- You may perform multiple tool calls in sequence when the task requires it.
- Inspect the environment before making assumptions about it.
- Use the terminal for terminal/Linux tasks. Do not ask the user to run a
  command that you are authorised and able to run yourself.
- The user's explicit request authorises normal computer actions within the
  capabilities and safety restrictions of the available tools. Do not invent
  an additional approval requirement merely because an action involves the
  terminal.
- Follow the user's requested task in order and verify important actions with
  the computer rather than relying on assumptions.
- If the task is genuinely impossible with the available tools, say exactly
  what capability is missing. Do not simulate the missing capability.

TERMINAL PRACTICE:
When asked to practise terminal access, start by using the real bash tool and
execute the requested verification commands. Treat their returned output as
authoritative. Never manufacture plausible-looking output.

You are not a text-only assistant for this session. Your job is to reason,
choose tools, observe their real results, and then answer the user."""


async def run_aerith_agent(
    *,
    owner: str,
    message: str,
    endpoint_url: str,
    model: str,
    headers: dict[str, str] | None = None,
    history: list[dict[str, Any]] | None = None,
    workspace: str | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Run one Aerith turn through the real Odysseus Agent loop.

    Returns ``(response, updated_history, metrics)``.  Bash is explicitly
    forced into the selected tool set so a computer request cannot silently
    degrade into a plain chat completion because tool retrieval missed it.
    """
    if not owner:
        raise ValueError("Aerith Agent requires an owner")

    user_message = str(message or "").strip()
    if not user_message:
        return "", list(history or []), {}

    messages = list(history or [])
    if not messages or messages[0].get("_aerith_system") is not True:
        messages.insert(
            0,
            {
                "role": "system",
                "content": AERITH_AGENT_DIRECTIVE,
                "_aerith_system": True,
            },
        )
    messages.append({"role": "user", "content": user_message})

    # Bash is the important capability here.  The native Agent loop still
    # applies the user's privilege policy and tool security before execution.
    forced_tools = {"bash"}

    deltas: list[str] = []
    metrics: dict[str, Any] = {}
    terminal_content = ""
    tool_events: list[dict[str, Any]] = []

    async for chunk in stream_agent_loop(
        endpoint_url=endpoint_url,
        model=model,
        messages=messages,
        headers=headers or {},
        temperature=0.3,
        max_tokens=2048,
        prompt_type="aerith",
        max_rounds=12,
        max_tool_calls=100,
        owner=owner,
        forced_tools=forced_tools,
        workspace=workspace,
        workload="foreground",
    ):
        if not isinstance(chunk, str):
            continue

        for raw_line in chunk.splitlines():
            if not raw_line.startswith("data: "):
                continue
            raw = raw_line[6:].strip()
            if raw == "[DONE]":
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if not isinstance(data, dict):
                continue

            if data.get("type") == "metrics":
                metrics.update(data.get("data") or {})
                tool_events.extend(data.get("data", {}).get("tool_events") or [])
                continue

            if data.get("type") == "agent_terminal":
                terminal_content = str(
                    data.get("data", {}).get("content")
                    or data.get("content")
                    or ""
                )
                continue

            if "delta" in data and not data.get("thinking"):
                deltas.append(str(data.get("delta") or ""))

    response = "".join(deltas).strip()
    if not response and terminal_content:
        response = terminal_content.strip()

    if not response:
        response = "The agent completed the turn without producing a final response."

    updated_history = list(messages)
    updated_history.append({
        "role": "assistant",
        "content": response,
        "metadata": {
            "agent": True,
            "tool_events": tool_events,
        },
    })

    logger.info(
        "[aerith-agent] owner=%s model=%s tool_calls=%s response_chars=%s",
        owner,
        model,
        len(tool_events),
        len(response),
    )

    metrics["aerith_agent"] = True
    metrics["aerith_tool_events"] = tool_events
    return response, updated_history, metrics
