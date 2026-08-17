#!/usr/bin/env bash
set -euo pipefail

# Link the private Git-LFS voice assets into the existing TTS-RVC-API model
# directory without copying the large files into the Odysseus repository.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

ASSETS_REPO="${AERITH_ASSETS_REPO:-$HOME/aerith-assets}"
TTS_RVC_DIR="${TTS_RVC_API_DIR:-$REPO_ROOT/TTS-RVC-API}"
MODEL_DIR="${RVC_MODEL_DIR:-$TTS_RVC_DIR/models}"
AERITH_DIR="$MODEL_DIR/aerith"

PTH="$ASSETS_REPO/assets/aerith/voice/aerith_e100_s8800.pth"
INDEX="$ASSETS_REPO/assets/aerith/voice/added_IVF3778_Flat_nprobe_1_aerith_v2.index"

if [[ ! -f "$PTH" || ! -f "$INDEX" ]]; then
    echo "Aerith voice assets are missing from: $ASSETS_REPO" >&2
    echo "Run git lfs pull in the aerith-assets checkout first." >&2
    exit 1
fi

mkdir -p "$AERITH_DIR"
ln -sfn "$PTH" "$AERITH_DIR/aerith_e100_s8800.pth"
ln -sfn "$INDEX" "$AERITH_DIR/added_IVF3778_Flat_nprobe_1_aerith_v2.index"

cat <<EOF
Aerith voice assets linked.

Model directory: $AERITH_DIR
Speaker name:    aerith

Start TTS-RVC-API with:
  RVC_MODEL_DIR="$MODEL_DIR" python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

Then configure Odysseus:
  AERITH_VOICE_ENABLED=1
  AERITH_RVC_URL=http://127.0.0.1:8001
  AERITH_RVC_ENDPOINT=/generate/
  AERITH_RVC_SPEAKER=aerith
EOF
