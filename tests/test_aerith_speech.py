import httpx

from src.aerith_speech import AerithSpeech


def test_speech_configuration_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AERITH_VOICE_ENABLED", "0")
    speech = AerithSpeech()
    assert speech.enabled is False


def test_speech_configuration_defaults_to_generate_endpoint(monkeypatch):
    monkeypatch.delenv("AERITH_RVC_ENDPOINT", raising=False)
    monkeypatch.delenv("AERITH_RVC_SPEAKER", raising=False)
    speech = AerithSpeech()
    assert speech.rvc_endpoint == "/generate/"
    assert speech.rvc_speaker == "aerith"


def test_generate_accepts_audio_response(monkeypatch):
    speech = AerithSpeech()
    captured = {}

    class FakeResponse:
        headers = {"content-type": "audio/wav"}
        content = b"RIFF-aerith"

        def raise_for_status(self):
            return None

    def fake_post(url, json, timeout):
        captured.update({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    result = speech._generate("Hello Tom")

    assert result.audio == b"RIFF-aerith"
    assert result.media_type == "audio/wav"
    assert captured["url"].endswith("/generate/")
    assert captured["json"]["speaker_name"] == "aerith"
    assert captured["json"]["input_text"] == "Hello Tom"
    assert captured["json"]["speed"] == 1.0
