# Aerith voice pipeline

Aerith voice is intentionally split into two processes:

```text
Aerith interaction → TTS-RVC-API → WAV
```

Odysseus owns the text response and companion voice API. The GPU-heavy Coqui +
RVC runtime stays in the existing `TTS-RVC-API` virtualenv/service.

## Model assets

The Aerith RVC model is stored separately in the private `90TP/aerith-assets`
repository using Git LFS:

- `aerith_e100_s8800.pth`
- `added_IVF3778_Flat_nprobe_1_aerith_v2.index`

Do not copy those large files into the Odysseus repository.

The TTS-RVC service dynamically discovers RVC models under its configured
`RVC_MODEL_DIR`. Put the two files in one speaker directory, for example:

```text
TTS-RVC-API/models/aerith/
├── aerith_e100_s8800.pth
└── added_IVF3778_Flat_nprobe_1_aerith_v2.index
```

The directory name becomes the `speaker_name`, so `aerith` is the API voice ID.

`scripts/setup_aerith_voice.sh` creates these links automatically from the
separate LFS checkout.

## Runtime configuration

Set these environment variables on the Odysseus server:

```text
AERITH_VOICE_ENABLED=1
AERITH_RVC_URL=http://127.0.0.1:8001
AERITH_RVC_ENDPOINT=/generate/
AERITH_RVC_SPEAKER=aerith
AERITH_RVC_EMOTION=
AERITH_RVC_SPEED=1.0
AERITH_SPEECH_TIMEOUT=120
```

The default endpoint matches the existing `TTS-RVC-API`: it accepts JSON with
`speaker_name`, `input_text`, optional `emotion`, and `speed`, and returns a WAV
stream.

## Companion API

Existing text interaction remains compatible:

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

## First-run checklist

1. Run `git lfs pull` in the `aerith-assets` checkout.
2. Run `scripts/setup_aerith_voice.sh` from Odysseus (or set its environment
   variables if the checkouts are elsewhere).
3. Ensure `RVC_MODEL_DIR` points at the TTS-RVC-API `models` directory.
4. Start the existing TTS-RVC API on port 8001.
5. Set the Odysseus environment variables above.
6. Verify `/api/companion/info` reports `aerith_voice: true`.
7. Call `/api/companion/aerith/interact` with `voice:true`.
8. Play the returned base64 bytes as the advertised media type in the 3D client.
