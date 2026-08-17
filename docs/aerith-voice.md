# Aerith voice pipeline

Aerith voice is intentionally split into two processes:

```text
Aerith interaction → Edge TTS → RVC HTTP service → audio
```

Odysseus owns the text response and voice API. The GPU-heavy RVC runtime stays in
its own virtualenv/service.

## Model assets

The Aerith RVC model is stored separately in the private `90TP/aerith-assets`
repository using Git LFS:

- `aerith_e100_s8800.pth`
- `added_IVF3778_Flat_nprobe_1_aerith_v2.index`

Do not copy those large files into the Odysseus repository.

## Runtime configuration

Set these environment variables on the Odysseus server:

```text
AERITH_VOICE_ENABLED=1
AERITH_RVC_URL=http://127.0.0.1:8001
AERITH_RVC_ENDPOINT=/clone/
AERITH_RVC_SPEAKER=aerith
AERITH_TTS_VOICE=en-GB-SoniaNeural
AERITH_TTS_RATE=+0%
AERITH_TTS_PITCH=+0Hz
AERITH_SPEECH_TIMEOUT=90
```

The RVC endpoint is configurable because the existing local RVC projects use
slightly different HTTP contracts. The adapter accepts either a direct audio
response or JSON containing base64 audio under `base64_wav`, `audio_base64`,
`wav`, `audio`, or `data`.

## Companion API

Existing text interaction remains unchanged:

```text
POST /api/companion/aerith/interact
{"message":"Hello"}
```

Voice chat requests audio in the same call:

```text
POST /api/companion/aerith/interact
{"message":"Hello", "voice":true}
```

Response:

```json
{
  "response": "Hello!",
  "voice": true,
  "audio_base64": "...",
  "audio_media_type": "audio/wav"
}
```

For clients that already have the text and only need speech:

```text
POST /api/companion/aerith/speak
{"text":"Hello!"}
```

For a native audio response:

```text
POST /api/companion/aerith/audio
{"text":"Hello!"}
```

All three endpoints use the existing companion authentication. The interaction
state's `speaking` flag is set for the duration of synthesis.

## RVC service contract

The default adapter calls:

```text
POST http://127.0.0.1:8001/clone/
Content-Type: multipart/form-data

speaker_name=aerith
audio_file=<base TTS audio>
```

If the local RVC service uses another route or field names, change
`AERITH_RVC_ENDPOINT` and adapt the small `_rvc_convert()` request in
`src/aerith_speech.py`; the rest of Aerith does not need changing.

## First-run checklist

1. Install the updated Odysseus requirements so `edge-tts` is available.
2. Ensure the RVC service is running and can load the Aerith `.pth` and `.index`.
3. Set the environment variables above.
4. Verify `/api/companion/info` reports `aerith_voice: true`.
5. Call `/api/companion/aerith/interact` with `voice:true`.
6. Play the returned base64 bytes as the advertised media type in the 3D client.
