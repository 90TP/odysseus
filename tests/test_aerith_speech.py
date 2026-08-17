from src.aerith_speech import AerithSpeech


def test_find_audio_value_from_common_rvc_response_shapes():
    assert AerithSpeech._find_audio_value({"base64_wav": "abc"}) == "abc"
    assert AerithSpeech._find_audio_value({"audio_base64": "def"}) == "def"
    assert AerithSpeech._find_audio_value({"data": {"wav": "ghi"}}) == "ghi"
    assert AerithSpeech._find_audio_value([{"audio": "jkl"}]) == "jkl"


def test_find_audio_value_strips_data_uri_prefix():
    assert AerithSpeech._find_audio_value({"audio": "data:audio/wav;base64,abc"}) == "abc"


def test_speech_configuration_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AERITH_VOICE_ENABLED", "0")
    speech = AerithSpeech()
    assert speech.enabled is False
