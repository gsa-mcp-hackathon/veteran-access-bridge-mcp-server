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
require_env ORCHESTRATE_BASE_URL
require_env ORCHESTRATE_AGENT_ID

if [[ "$LIVEKIT_URL" != wss://* ]]; then
  echo "LIVEKIT_URL must start with wss:// and use your LiveKit Cloud project URL." >&2
  echo "Current value begins with: ${LIVEKIT_URL%%://*}://" >&2
  exit 1
fi
if [[ "$LIVEKIT_URL" == *"127.0.0.1"* || "$LIVEKIT_URL" == *"localhost"* ]]; then
  echo "LIVEKIT_URL cannot point to localhost/127.0.0.1 in Codespaces." >&2
  exit 1
fi

if [[ -z "${ORCHESTRATE_API_KEY:-}" && -z "${ORCHESTRATE_BEARER_TOKEN:-}" ]]; then
  echo "Missing ORCHESTRATE_API_KEY or ORCHESTRATE_BEARER_TOKEN." >&2
  exit 1
fi

export VAB_DEMO_HOST="${VAB_DEMO_HOST:-0.0.0.0}"
export PORT="${PORT:-8080}"
export VAB_WEBRTC_GATEWAY="LIVEKIT"
export VAB_WEBRTC_GATEWAY_CONFIGURED="true"
export VAB_WEBRTC_SIGNALING_URL="$LIVEKIT_URL"
export VAB_WEBRTC_TOKEN_TTL_SECONDS="${VAB_WEBRTC_TOKEN_TTL_SECONDS:-300}"
export VAB_WEBRTC_SOFTPHONE_ENABLED="true"
export ORCHESTRATE_RUNTIME_MODE="remote"

echo "Starting Veteran Access Bridge in GitHub Codespaces"
echo "  Bind            : $VAB_DEMO_HOST:$PORT"
echo "  LiveKit         : $LIVEKIT_URL"
echo "  Orchestrate     : remote"
echo
echo "Open the forwarded port 8080 from the Codespaces Ports panel."

exec uv run veteran-access-demo
