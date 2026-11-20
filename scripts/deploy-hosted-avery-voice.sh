#!/usr/bin/env bash
# Deploy ONLY the synthetic M6.4 LiveKit voice slice in the existing IBM project.
# Prerequisites: authenticated IBM Cloud CLI, published GHCR image and a
# pre-existing private Code Engine worker secret holding LIVEKIT_* and DEEPGRAM_API_KEY.
# Never run with real patient data or against the main VAB backend.
set -Eeuo pipefail

MODE="${1:---check}"
if [[ "$MODE" != "--check" && "$MODE" != "--apply" ]]; then
  echo "Usage: bash scripts/deploy-hosted-avery-voice.sh [--check|--apply]" >&2
  exit 2
fi

for cmd in ibmcloud curl python grep; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing executable: $cmd" >&2; exit 1; }
done

PROJECT="ce-550000w6t0"
RESOURCE_GROUP="eid-6ac41f127818aff458d82ac8"
WORKER_APP="vab-avery-voice-worker"
BACKEND_APP="veteran-access-bridge-m64-canary"
FRONTEND_APP="vab-avery-callcenter"
WORKER_SECRET="${VAB_AVERY_WORKER_SECRET_NAME:-vab-avery-worker-runtime}"
CANARY_URL="https://veteran-access-bridge-m64-canary.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"
FRONTEND_URL="https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"
WORKER_IMAGE="ghcr.io/wbgreen0405/veteran-access-bridge:avery-worker-d63b26d32f4dcfe5917197aea828bd42cfcc1dcd"
FRONTEND_IMAGE="ghcr.io/wbgreen0405/veteran-appointment-bridge:avery-callcenter-a606955cd7e6ea56701e9996d5b1dfee0341602e"

echo "Using EXISTING IBM Cloud project $PROJECT (region ca-tor)"
ibmcloud target -r ca-tor -g "$RESOURCE_GROUP" >/dev/null
ibmcloud ce project select --name "$PROJECT" >/dev/null

# Check only: never modifies app settings or cloud resources.
if [[ "$MODE" == "--check" ]]; then
  echo "Checking deployment inventory and safe voice status (no writes)..."
  ibmcloud ce application list
  echo
  echo "M6.4 canary voice status:"
  curl --fail --silent --show-error "$CANARY_URL/api/voice/status" | python -m json.tool
  echo
  echo "Frontend HTTP status:"
  curl --silent --output /dev/null --write-out '%{http_code}\n' "$FRONTEND_URL/"
  exit 0
fi

if [[ "${VAB_CONFIRM_SYNTHETIC_VOICE_DEPLOY:-}" != "YES" ]]; then
  echo "To deploy, set VAB_CONFIRM_SYNTHETIC_VOICE_DEPLOY=YES after reviewing worker cost and synthetic-only scope." >&2
  exit 2
fi
if [[ "${VAB_CONFIRM_MATCHING_LIVEKIT_PROJECT:-}" != "YES" ]]; then
  echo "Verify that worker secret, M6.4 token issuer, and LiveKit Cloud share the same URL/keypair." >&2
  echo "Then set VAB_CONFIRM_MATCHING_LIVEKIT_PROJECT=YES. No keys are printed." >&2
  exit 2
fi
if [[ -z "${LIVEKIT_URL:-}" || "${LIVEKIT_URL}" != wss://* ]]; then
  echo "Codespace LIVEKIT_URL must contain the same LiveKit Cloud wss:// project URL as the private Code Engine secret." >&2
  exit 2
fi

echo "Checking required existing IBM applications and private worker secret..."
ibmcloud ce application get --name "$BACKEND_APP" >/dev/null
ibmcloud ce application get --name "$FRONTEND_APP" >/dev/null
secret_inventory="$(ibmcloud ce secret list)"
if ! grep -Fq "$WORKER_SECRET" <<< "$secret_inventory"; then
  echo "Required Code Engine worker secret '$WORKER_SECRET' not found." >&2
  echo "Create it privately with LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET and DEEPGRAM_API_KEY before deploying." >&2
  exit 1
fi

# The worker is distinct from the VAB API container: no API/MCP changes.
if ibmcloud ce application get --name "$WORKER_APP" >/dev/null 2>&1; then
  echo "Updating existing Avery voice worker app (no duplicate created)..."
  ibmcloud ce application update \
    --name "$WORKER_APP" \
    --image "$WORKER_IMAGE" \
    --port 8081 \
    --min-scale 1 \
    --max-scale 1 \
    --env "VAB_VOICE_BACKEND_URL=$CANARY_URL" \
    --env-from-secret "$WORKER_SECRET" \
    --wait
else
  echo "Creating a single private Avery voice worker (min-scale 1 incurs ongoing cost)..."
  ibmcloud ce application create \
    --name "$WORKER_APP" \
    --image "$WORKER_IMAGE" \
    --registry-secret ghcr-veteran-access \
    --cluster-local \
    --port 8081 \
    --cpu 1 \
    --memory 2G \
    --min-scale 1 \
    --max-scale 1 \
    --env "VAB_VOICE_BACKEND_URL=$CANARY_URL" \
    --env-from-secret "$WORKER_SECRET" \
    --wait
fi

# Code Engine "Ready" is an HTTP-probe/readiness indicator, not proof of speech.
worker_state="$(ibmcloud ce application get --name "$WORKER_APP")"
if ! grep -Eiq 'Ready' <<< "$worker_state"; then
  echo "Worker has not reported Ready. Check its revision and logs; canary voice has NOT been enabled." >&2
  exit 1
fi
# The real LiveKit registration message is required before enabling caller tokens.
worker_logs="$(ibmcloud ce application logs --name "$WORKER_APP" 2>&1)" || {
  echo "Could not inspect worker logs; canary voice has NOT been enabled." >&2
  exit 1
}
if ! grep -Eiq 'registered worker|registered agent' <<< "$worker_logs"; then
  echo "No LiveKit 'registered worker' evidence was found; canary voice has NOT been enabled." >&2
  echo "Review IBM Code Engine logs privately (do not post transcripts, tokens or secrets)." >&2
  exit 1
fi

echo "Worker Ready and LiveKit registration observed. Enabling canary browser voice..."
ibmcloud ce application update \
  --name "$BACKEND_APP" \
  --env VAB_WEBRTC_GATEWAY=LIVEKIT \
  --env VAB_WEBRTC_GATEWAY_CONFIGURED=true \
  --env VAB_WEBRTC_SOFTPHONE_ENABLED=true \
  --env "VAB_WEBRTC_SIGNALING_URL=$LIVEKIT_URL" \
  --wait

# Validate actual backend readiness contract, not just the IBM CLI exit status.
curl --fail --silent --show-error "$CANARY_URL/api/voice/status" |
  python -c 'import json,sys; obj=json.load(sys.stdin); ok=obj.get("transport",{}).get("browser_softphone_enabled") is True; print("Canary browser voice configured:",ok); sys.exit(0 if ok else 1)'

echo "Updating existing Screen A frontend with published immutable image..."
ibmcloud ce application update --name "$FRONTEND_APP" --image "$FRONTEND_IMAGE" --wait

curl --fail --silent --show-error --output /dev/null "$FRONTEND_URL/"
echo
echo "Deployment command completed. Real two-way speech is NOT yet proven."
echo "Open $FRONTEND_URL, press Start Call, allow the mic and verify multiple"
echo "spoken turns: LiveKit → Deepgram STT → IBM Avery → Deepgram TTS → LiveKit."
echo "Do not enable autonomous synthetic booking until receipt and approval gates pass."
