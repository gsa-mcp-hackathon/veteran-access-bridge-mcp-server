#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required Codespaces secret/environment variable: $name" >&2
    exit 1
  fi
}

require_env LIVEKIT_URL
require_env LIVEKIT_API_KEY
require_env LIVEKIT_API_SECRET
require_env DEEPGRAM_API_KEY

export DEEPGRAM_STT_MODEL="${DEEPGRAM_STT_MODEL:-flux-general-en}"
export DEEPGRAM_TTS_MODEL="${DEEPGRAM_TTS_MODEL:-flux-alexis-en}"
export VAB_VOICE_BACKEND_URL="${VAB_VOICE_BACKEND_URL:-http://127.0.0.1:8080}"
export VAB_VOICE_BACKEND_TIMEOUT_SECONDS="${VAB_VOICE_BACKEND_TIMEOUT_SECONDS:-35}"

echo "Starting Avery voice worker in GitHub Codespaces"
echo "  LiveKit URL : $LIVEKIT_URL"
echo "  VAB backend : $VAB_VOICE_BACKEND_URL"
echo "  STT model   : $DEEPGRAM_STT_MODEL"
echo "  TTS model   : $DEEPGRAM_TTS_MODEL"
echo

exec uv run veteran-access-voice-worker dev
