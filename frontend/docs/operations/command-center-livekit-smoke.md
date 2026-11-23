# Command Center ↔ VAB local synthetic LiveKit acceptance runbook

**Status:** Manual local-only integration gate. CI checks are mocked; real LiveKit tracks, Avery speech, MCP events and reconnect behavior are **not yet certified**.

## Ownership and safety

The authoritative FastAPI backend, Avery and LiveKit worker live in VAB draft PR #181. The Command Center and its server-side BFF live in frontend draft PR #1. Do not merge, deploy, enable public access, use actual patient data or run production scheduling writes for this test.

Test **both projects in the same local machine/network namespace**. A hosted Lovable preview or a different Codespace cannot reach the other machine's localhost. Before switching branches, check for uncommitted local work and preserve it.

Keep LiveKit, Deepgram, Orchestrate, monitor service key and operator code in ignored local configuration or secret injection. Never use VITE_* or public JavaScript for service credentials.

## GitHub Codespaces + existing LiveKit Cloud (preferred for this project)

Codespaces is a supported **application and worker host**. Do **not** start a second self-hosted LiveKit server in Codespaces. Its forwarded web ports cover TCP/HTTPS, not the separate WebRTC media ports; use the existing LiveKit Cloud project for remote audio. Codespaces Secrets already provisioned for the VAB worker should be reused, not copied into git or pasted into chat.

This section supersedes the local LiveKit server instructions in section 1 when testing in Codespaces. Open the **existing VAB Codespace** and use its terminals, rather than trying to reach it from the ChatGPT GitHub connector (which can edit repositories but cannot execute Codespace shell commands).

Before changing branches, run git status --short and preserve local work. Keep the frontend checkout in the **same Codespace** so its server-side BFF can call 127.0.0.1:8080 directly. If a port is occupied, identify the process first; don't kill all Python/Node processes.

~~~bash
cd /workspaces/veteran-access-bridge
git status --short
git fetch origin
git switch feat/msa-authoritative-livekit-monitor-20261109
uv sync --group dev --extra voice
# No secret values are printed by this check:
for name in LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET DEEPGRAM_API_KEY ORCHESTRATE_BASE_URL ORCHESTRATE_AGENT_ID VAB_MSA_MONITOR_SERVICE_KEY VAB_MSA_OPERATOR_ACCESS_CODE; do
  if printenv "$name" >/dev/null; then echo "$name=SET"; else echo "$name=MISSING"; fi
done
ss -ltnp | grep -E ':(8080|5173)\b' || true
~~~

Private Codespaces Secrets required by the new monitor (in addition to those previously configured for voice): VAB_MSA_MONITOR_SERVICE_KEY and VAB_MSA_OPERATOR_ACCESS_CODE, each 32+ random characters and **different**. Both backend and frontend receive the **same service key** in their server environment. Keep VAB_MSA_MONITOR_ENABLED and VAB_MSA_LIVE_MONITOR_ENABLED disabled except for the local test. Existing Codespaces Secrets are provided to terminal processes; after adding new secrets, the Codespace may need a restart.

Terminal A — canonical VAB backend (port 8080, internal service; do not expose publicly):

~~~bash
cd /workspaces/veteran-access-bridge
export VAB_MSA_MONITOR_ENABLED=true
bash scripts/run-vab-codespace.sh
~~~

Terminal B — existing Avery worker connected to LiveKit Cloud, with backend URL **forced to this same Codespace** (not an older deployed m64 canary):

~~~bash
cd /workspaces/veteran-access-bridge
export VAB_VOICE_BACKEND_URL=http://127.0.0.1:8080
bash scripts/run-voice-worker-codespace.sh
~~~

Terminal C — the existing frontend repository, in a sibling checkout. First-time clone only:

~~~bash
cd /workspaces
test -d veteran-appointment-bridge || git clone https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git
cd veteran-appointment-bridge
git status --short
git fetch origin
git switch feat/sandbox-monitor-readiness-contract-20261109
bun --version
bun install --frozen-lockfile
export VAB_API_BASE_URL=http://127.0.0.1:8080
export VAB_MSA_LIVE_MONITOR_ENABLED=true
bun run dev --host 0.0.0.0 --port 5173
~~~

The VAB Python devcontainer does not itself install Bun; if bun --version fails, install Bun once using the official Bun installation instructions and restart the terminal. Do not fall back to a different lockfile or package manager without reviewing it.

Use the Codespaces **Ports** panel to open forwarded HTTPS ports 8080 (existing Veteran browser/softphone) and 5173 (Command Center); retain **private** visibility for both. Forwarded HTTPS is a browser origin for microphone permissions. The existing LiveKit Cloud wss:// endpoint handles WebRTC media. The server-side frontend BFF uses http://127.0.0.1:8080 **inside the Codespace**, never the external forwarded port URL.

After the canonical synthetic session is created, use the previous read-only smoke procedure in this document. In terminal D, in the frontend repo:

~~~bash
export VAB_RUN_MSA_MONITOR_SMOKE=1
export VAB_MSA_FRONTEND_URL=http://127.0.0.1:5173
# Set VAB_MSA_TEST_CASE_ID and VAB_MSA_TEST_VOICE_SESSION_ID
# from the existing synthetic VAB session, without pasting any token.
node scripts/smoke-msa-monitor.mjs before
# After the Veteran really joins and Avery is dispatched:
node scripts/smoke-msa-monitor.mjs ready
~~~

For the documented earlier symptom "Avery greeting plays but does not respond to Veteran speech," use the Avery worker logs to distinguish:

- No final Deepgram STT event: investigate remote Veteran microphone track, LiveKit subscription, STT connection/authentication, Flux endpoint and end-of-turn conditions.
- Final STT event with nonzero character count but no reply: investigate the existing VAB /api/interactions/.../messages HTTP bridge and Orchestrate configuration.
- Reply ready but no audible Avery speech: inspect Deepgram TTS and LiveKit agent-published track.
- The observer can only join **after** the Veteran room and named Avery dispatch exist; a 409 before that is a correct protection, not a broken monitor.

No audio track, transcript, scheduling, durable booking, or MCP execution should be considered verified merely because the smoke script returns 200. The Command Center should be manually opened on port 5173 and both distinct LiveKit tracks witnessed.

After testing, stop only these local processes and return monitor enable flags to false. Do not merge, deploy or publish based solely on Codespaces connectivity.

## 1. Local startup

In the backend checkout at branch feat/msa-authoritative-livekit-monitor-20261109, with Python 3.12+ and uv available:

~~~powershell
uv sync --group dev --extra voice
# Terminal A on Windows: local LiveKit development server
.\scripts\run-livekit-local.ps1
# Terminal B: canonical FastAPI backend
uv run veteran-access-demo
# Terminal C: the existing Avery worker
uv run --extra voice veteran-access-voice-worker dev
~~~

On Linux with the binary installed, terminal A can use the local-only command livekit-server --dev --bind 127.0.0.1 instead. See the existing backend operations guide for audio and Deepgram prerequisites.

In the frontend checkout at branch feat/sandbox-monitor-readiness-contract-20261109:

~~~powershell
bun install --frozen-lockfile
bun run dev --host 127.0.0.1 --port 5173
~~~

Private backend process env: VAB_MSA_MONITOR_ENABLED=true, random VAB_MSA_MONITOR_SERVICE_KEY of at least 32 characters, VAB_WEBRTC_GATEWAY=LIVEKIT, VAB_WEBRTC_GATEWAY_CONFIGURED=true, local signaling URL ws://127.0.0.1:7880, matching LiveKit key/secret, and already-configured Deepgram and Orchestrate credentials. Start only trusted local development services.

Private frontend **server** env: VAB_MSA_LIVE_MONITOR_ENABLED=true, VAB_API_BASE_URL=http://127.0.0.1:8080, the same VAB_MSA_MONITOR_SERVICE_KEY, and a **different** 32+ character VAB_MSA_OPERATOR_ACCESS_CODE. Do not forward or publish either port beyond the local sandbox.

## 2. Create and identify a synthetic session

Prefer the existing VAB browser/softphone, which creates its own canonical interaction/session and connects the Veteran microphone. Capture the exact synthetic case ID and active voice session ID it uses; do not copy the JWT.

For the **before** negative check, first create a pre-call canonical VoiceSession with the existing VAB API. This example uses a synthetic fixture and the current sandbox demo headers:

~~~powershell
$base = "http://127.0.0.1:8080"
$case = "DEMO-PC-5000999-001"
$headers = @{
  "X-Demo-Role" = "SCHEDULER"
  "X-Demo-Actor" = "local-integration-check"
  "X-Demo-Case" = $case
}
$encounter = Invoke-RestMethod -Method Get -Uri "$base/api/scheduling-encounters/$case" -Headers $headers
$interactionBody = @{
  case_id = $case
  scheduling_encounter_id = $encounter.scheduling_encounter_id
  channel = "PHONE"
  agent_opening = $true
} | ConvertTo-Json
$interaction = Invoke-RestMethod -Method Post -Uri "$base/api/interactions" -Headers $headers -ContentType "application/json" -Body $interactionBody
$sessionBody = @{
  interaction_id = $interaction.interaction_id
  correlation_id = $interaction.correlation_id
  case_id = $case
  scheduling_encounter_id = $encounter.scheduling_encounter_id
  transport = "LIVEKIT"
} | ConvertTo-Json
$session = Invoke-RestMethod -Method Post -Uri "$base/api/voice-sessions" -Headers $headers -ContentType "application/json" -Body $sessionBody
$env:VAB_MSA_TEST_CASE_ID = $case
$env:VAB_MSA_TEST_VOICE_SESSION_ID = $session.voice_session_id
~~~

If the interaction fails because Avery/Orchestrate is unavailable, stop; do not substitute a mock and claim real speech. Creating a VoiceSession **does not** create a LiveKit room, begin speech or book an appointment. The frontend softphone might create a *different* session; update the ID for the ready phase.

## 3. Read-only observer handshake

From the frontend checkout in a local terminal with the same private operator code in the terminal environment:

~~~powershell
$env:VAB_RUN_MSA_MONITOR_SMOKE = "1"
$env:VAB_MSA_FRONTEND_URL = "http://127.0.0.1:5173"
# VAB_MSA_OPERATOR_ACCESS_CODE is set privately; never paste it in GitHub.
node scripts/smoke-msa-monitor.mjs before
~~~

**Before Veteran connects**, expect HTTP 409 voice_room_not_ready, no observer JWT and a passing summary of room_ready=false. If the room already exists, start a fresh synthetic session to test this negative gate.

After the Veteran browser actually connects and Avery is dispatched, set VAB_MSA_TEST_CASE_ID and VAB_MSA_TEST_VOICE_SESSION_ID to the **active call** (they may be different from the pre-call test) and run:

~~~powershell
node scripts/smoke-msa-monitor.mjs ready
~~~

The positive test verifies the BFF can obtain a case-scoped subscribe-only token and a sanitized authoritative event feed. It never prints tokens or raw event payloads. A zero MCP event count means **no MCP execution has been observed**. The summary deliberately says media_tracks_verified=false: this script does not join LiveKit or verify audio. JWT claims are inspected, not cryptographically independently verified.

## 4. Witness real LiveKit media and failure behavior

1. Start the existing VAB Veteran browser microphone; confirm real LiveKit connection and Avery's audible greeting through the worker, not browser speech synthesis.
2. Open the local Command Center, expand sandbox configuration, and connect to that **same** synthetic session. Verify the Veteran cyan waveform and Avery violet Aura each react to **their own** remote subscribed audio track. The Command Center has no routine Monitor/Mute/Join/Hold/End controls.
3. Use the real synthetic Orchestrate/Avery workflow to execute a read-only MCP call such as search_availability. Match tool call IDs and correlation across the conversation card and inspector. A returned event without success evidence must remain outcome-unverified. Do not imply a booking, letter or delivered notification.
4. Disconnect/reconnect the observer while the Veteran remains; verify a new scoped JWT, no published microphone, no duplicate event IDs, and uninterrupted Avery audio.
5. End the synthetic Veteran call or remove the LiveKit room, then retry observer authorization. It must remain disconnected, never recreate the room, and never start an unexpected Avery worker. Repeat with a worker restart or stale case.
6. Explicitly record if the room disappears between preflight and browser join; this **time-of-check/time-of-use** window is not eliminated by the existing preflight and needs real churn testing.
7. Return the backend and frontend monitor enabled flags to false when finished. Do not publish, merge or deploy based solely on successful handshake tests.

## Evidence and acceptance

Record date, exact tested PR commit SHAs, separate observed Veteran/Avery audio evidence, actual MCP event/correlation counts, reconnect outcome and any failures. No secrets, JWT, full transcript, raw MCP arguments/results, PII or PHI in screenshots or issue comments.

The acceptance gate is only **PASS** when: negative 409 check passes; positive subscribe-only JWT and event projection pass; live Veteran+agent tracks are confirmed independently; Avery keeps speaking with observer connected; MCP events actually correlate; reconnect/churn failures are tested. Until then the state is **PENDING LIVE LOCAL TEST**, regardless of mocked CI results.
