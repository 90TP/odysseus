"""Aerith speech synthesis bridge.

Aerith's interaction layer owns text; this module owns turning that text into
her voice. The GPU-heavy TTS/RVC runtime stays in its own process/virtualenv.

The default backend is the existing ``TTS-RVC-API`` service used by the
project. It accepts text and a speaker name and returns a WAV response. This
keeps Coqui/RVC dependencies out of the Odysseus application environment.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    media_type: str = "audio/wav"
    voice: str = "aerith"


class AerithSpeechError(RuntimeError):
    """Raised when Aerith speech generation fails."""


class AerithSpeech:
    """Call the standalone TTS-RVC service used to generate Aerith's voice."""

    def __init__(self) -> None:
        self.rvc_url = os.getenv("AERITH_RVC_URL", "http://127.0.0.1:8001").rstrip("/")
        self.rvc_endpoint = os.getenv("AERITH_RVC_ENDPOINT", "/generate/")
        self.rvc_speaker = os.getenv("AERITH_RVC_SPEAKER", "aerith")
        self.rvc_emotion = os.getenv("AERITH_RVC_EMOTION", "")
        self.rvc_speed = float(os.getenv("AERITH_RVC_SPEED", "1.0"))
        self.timeout = float(os.getenv("AERITH_SPEECH_TIMEOUT", "120"))
        self.enabled = os.getenv("AERITH_VOICE_ENABLED", "1").lower() not in {"0", "false", "no", "off"}

    async def synthesize(self, text: str) -> SpeechResult:
        text = str(text or "").strip()
        if not text:
            raise AerithSpeechError("Cannot synthesise empty text")
        if not self.enabled:
            raise AerithSpeechError("Aerith voice is disabled")

        return await asyncio.to_thread(self._generate, text)

    def _generate(self, text: str) -> SpeechResult:
        url = f"{self.rvc_url}/{self.rvc_endpoint.lstrip('/')}"
        payload = {
            "speaker_name": self.rvc_speaker,
            "input_text": text,
            "speed": self.rvc_speed,
        }
        if self.rvc_emotion:
            payload["emotion"] = self.rvc_emotion

        try:
            response = httpx.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AerithSpeechError(f"TTS-RVC request failed: {exc}") from exc

        content_type = response.headers.get("content-type", "")
        if content_type.startswith("audio/"):
            return SpeechResult(audio=response.content, media_type=content_type.split(";", 1)[0])

        raise AerithSpeechError(
            "TTS-RVC returned a non-audio response "
            f"({content_type or 'unknown content type'}): {response.text[:300]}"
        )
