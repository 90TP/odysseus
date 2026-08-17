"""Aerith speech synthesis bridge.

The interaction layer owns text; this module owns turning that text into the
Aerith voice.  The implementation is deliberately HTTP based so the RVC
runtime can live in its own GPU process/virtualenv.  Base TTS is generated with
Edge TTS and then sent to the configured RVC service for conversion.
"""

from __future__ import annotations

import asyncio
import base64
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    media_type: str = "audio/wav"
    voice: str = "aerith"


class AerithSpeechError(RuntimeError):
    """Raised when Aerith speech generation fails."""


class AerithSpeech:
    """Generate Aerith speech using Edge TTS followed by an RVC HTTP service."""

    def __init__(self) -> None:
        self.rvc_url = os.getenv("AERITH_RVC_URL", "http://127.0.0.1:8001").rstrip("/")
        self.rvc_endpoint = os.getenv("AERITH_RVC_ENDPOINT", "/clone/")
        self.rvc_speaker = os.getenv("AERITH_RVC_SPEAKER", "aerith")
        self.edge_voice = os.getenv("AERITH_TTS_VOICE", "en-GB-SoniaNeural")
        self.edge_rate = os.getenv("AERITH_TTS_RATE", "+0%")
        self.edge_pitch = os.getenv("AERITH_TTS_PITCH", "+0Hz")
        self.timeout = float(os.getenv("AERITH_SPEECH_TIMEOUT", "90"))
        self.enabled = os.getenv("AERITH_VOICE_ENABLED", "1").lower() not in {"0", "false", "no", "off"}

    async def synthesize(self, text: str) -> SpeechResult:
        text = str(text or "").strip()
        if not text:
            raise AerithSpeechError("Cannot synthesise empty text")
        if not self.enabled:
            raise AerithSpeechError("Aerith voice is disabled")

        base_wav = await asyncio.to_thread(self._edge_tts, text)
        try:
            converted = await asyncio.to_thread(self._rvc_convert, base_wav)
        finally:
            try:
                Path(base_wav).unlink(missing_ok=True)
            except OSError:
                pass
        return SpeechResult(audio=converted)

    def _edge_tts(self, text: str) -> str:
        """Create a temporary WAV using the installed edge-tts package."""
        try:
            import edge_tts  # type: ignore
        except ImportError as exc:
            raise AerithSpeechError(
                "edge-tts is not installed; install it in the Odysseus runtime"
            ) from exc

        fd, path = tempfile.mkstemp(prefix="aerith_tts_", suffix=".mp3")
        os.close(fd)
        try:
            communicate = edge_tts.Communicate(
                text,
                self.edge_voice,
                rate=self.edge_rate,
                pitch=self.edge_pitch,
            )
            asyncio.run(communicate.save(path))
            return path
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise

    def _rvc_convert(self, input_path: str) -> bytes:
        """Call the configured RVC service and normalise its common responses."""
        url = f"{self.rvc_url}/{self.rvc_endpoint.lstrip('/')}"
        with open(input_path, "rb") as audio:
            files = {"audio_file": (Path(input_path).name, audio, "audio/mpeg")}
            data = {"speaker_name": self.rvc_speaker}
            try:
                response = httpx.post(url, files=files, data=data, timeout=self.timeout)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise AerithSpeechError(f"RVC request failed: {exc}") from exc

        content_type = response.headers.get("content-type", "")
        if content_type.startswith("audio/"):
            return response.content

        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise AerithSpeechError("RVC returned neither audio nor JSON") from exc

        encoded = self._find_audio_value(payload)
        if not encoded:
            raise AerithSpeechError("RVC response did not contain audio data")
        try:
            return base64.b64decode(encoded)
        except Exception as exc:
            raise AerithSpeechError("RVC returned invalid base64 audio") from exc

    @classmethod
    def _find_audio_value(cls, payload: Any) -> str | None:
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            for key in ("base64_wav", "audio_base64", "wav", "audio", "data"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    if value.startswith("data:audio/") and "," in value:
                        return value.split(",", 1)[1]
                    return value
                found = cls._find_audio_value(value)
                if found:
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = cls._find_audio_value(value)
                if found:
                    return found
        return None
