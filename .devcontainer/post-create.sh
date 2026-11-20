#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

uv sync --group dev --extra voice

echo
echo "Veteran Access Bridge Codespace is ready."
echo "Required Codespaces secrets for live voice:"
echo "  LIVEKIT_URL"
echo "  LIVEKIT_API_KEY"
echo "  LIVEKIT_API_SECRET"
echo "  DEEPGRAM_API_KEY"
echo "  ORCHESTRATE_BASE_URL"
echo "  ORCHESTRATE_AGENT_ID"
echo "  ORCHESTRATE_API_KEY or ORCHESTRATE_BEARER_TOKEN"
echo
echo "Start VAB:          bash scripts/run-vab-codespace.sh"
echo "Start Avery worker: bash scripts/run-voice-worker-codespace.sh"
