# Autonomous Scheduling Command Center

Sandbox-only frontend for the approved three-column concept. It doesn't publish anything, connect to production or VA systems, or write to any backend.

## Layout (desktop ~34 / 35 / 31)
- **Header:** "Veteran Access Bridge / Autonomous Scheduling Command Center", "Primary Care · MCP-Powered", the SANDBOX badge and the truthful connection state. No seal or endorsement.
- **Left:** a navy Live Voice Session panel with the cyan Veteran orb and the violet Avery LiveKit Agents UI Aura. Audio comes from the tracks `useLiveMonitor` subscribes to. There are no Mute/Monitor/Join/Hold/End controls. Below the voice panel is the white **Live Conversation**, which interleaves turns with inline MCP cards. There is no text entry and no staff chat.
- **Center:** the **MCP Execution Inspector**, with Execution Timeline / Tool Details / Evidence / Audit tabs and three-category coverage (Observed / Implemented · not run / Planned · not run).
- **Right:** Scheduling Encounter, then Avery's Work · Autonomous Workflow (Verify → Search → Select → Book), then artifact rows.
- **Demo controls (collapsed):** scenario replay, Connect sandbox… / Disconnect observer, and optional local observer playback.

## One execution pipeline
`src/lib/mcp-execution.ts` is pure. `stepsFromReplay` takes replay `ActivityEvent`s and `stepsFromMonitor` takes authoritative `mcp_tool_called` / `mcp_tool_result` events (grouped by `tool_call_id`). Both return `ExecutionStep[]`, which the conversation cards and the inspector both read.
- An allowlisted `TOOL_REGISTRY` decides the category:
  - **Read:** get_scheduling_encounter, search_availability, validate_booking_preconditions, assess_access_standard.
  - **Write:** record_option_selection, record_veteran_confirmation. There is no booking MCP tool.
  - **Unknown tools:** shown as "Other MCP operation".
- No dataset tool is registered yet, so the Dataset Access Server category shows *Planned · not run* and never shows a completed call.
- Duration is shown only when a called/result pair is measured. Server ID, policy outcome and idempotency show "Unavailable".
- `parseVerifiedAvailability` is a strict adapter for future evidence. It needs a `verified_availability_summary` that is verified and synthetic and matches the case and correlation. It isn't wired to anything yet.

## API contract (unchanged)
- BFF: `POST /api/msa-monitor` with actions `token` and `events`. It's fail-closed, uses server-only env, and is disabled by default.
- Canonical endpoints (draft PR181): `POST /api/voice-sessions/{id}/msa-monitor-token` and `GET /api/interactions/{id}/msa-monitor-events?cursor`.
- Event shape: `{event_id,event_type,interaction_id,case_id,scheduling_encounter_id,correlation_id,source,occurred_at,synthetic,payload:{tool_name?,tool_call_id?,status?,error_code?}}`.

## Modes
- **Scripted replay (default):** everything is badged "Scripted replay".
  - A five-business-day mini calendar appears only after the synthetic availability step succeeds. It uses `slotsFor()` on a rolling window from today.
  - A recorded selection is not a booking.
  - On an identity mismatch, slots and the provider are hidden.
- **Authoritative observer:** shows "Voice transcript unavailable from authoritative source", the MCP event cards, and "Awaiting authorized availability evidence". It shows no booking, documents or fixture data.

## Three capabilities shown
1. Observing an autonomous voice session (LiveKit subscribe-only, with real audio tracks bound to the orbs).
2. MCP execution transparency (one shared timeline, category coverage, evidence and audit).
3. A routine scheduling workflow with no MSA approval gate, where selection and booking are kept separate.

## Explicitly missing
- Dataset Access Server connector (to be added to the canonical MCP server).
- A verified live transcript source.
- Durable backend booking evidence (PR159).
- Slot evidence in `/msa-monitor-events`.

## Later test steps
1. Enable the sandbox BFF env on local servers. Start the synthetic Veteran call first so LiveKit creates the room and dispatches Avery; only then connect the observer. Confirm the Aura and waveform respond to actual remote tracks.
2. Emit `mcp_tool_called` / `mcp_tool_result` events and confirm the inspector's statuses and measured durations.
3. Once the backend exposes a verified availability summary, wire it through `parseVerifiedAvailability`.
4. Run screen-reader and keyboard passes on the calendar chips and inspector tabs.

## Cross-repo contract reference
- Canonical backend: `wbgreen0405/veteran-access-bridge`, draft PR181, branch `feat/msa-authoritative-livekit-monitor-20261109`. Contract doc: `docs/contracts/command-center-frontend-backend-integration.md`.
- Intended frontend repository: `wbgreen0405/veteran-appointment-bridge`. A Lovable commit does not prove that GitHub repository is in sync. GitHub access has since been granted and `main` was verified equal to Lovable revision `8cb35f51` before this separate draft integration branch. This branch remains unmerged; the Lovable preview is not assumed to include it.
- BFF → backend (fixed, same-origin `POST /api/msa-monitor` only):
  - `token` → `POST {VAB_API_BASE_URL}/api/voice-sessions/{voice_session_id}/msa-monitor-token`
  - `events` → `GET {VAB_API_BASE_URL}/api/interactions/{interaction_id}/msa-monitor-events?cursor=`
- Gates:
  - Backend: `VAB_MSA_MONITOR_ENABLED=false` by default.
  - Frontend server-only env: `VAB_MSA_LIVE_MONITOR_ENABLED=false` by default, plus `VAB_API_BASE_URL`, `VAB_MSA_MONITOR_SERVICE_KEY` and a distinct `VAB_MSA_OPERATOR_ACCESS_CODE`.
  - No secrets are hardcoded or exposed to the browser, and there is no public URL or deployment change.
- MCP status semantics:
  - Only an explicit success status shows Succeeded.
  - Explicit blocked/failed/retry statuses are shown as given.
  - A `mcp_tool_result` with no status or error_code shows "Result received · outcome unverified".
  - Results without a `tool_call_id` stay unlinked under their own `event_id`, with no inferred duration.
- The canonical MCP registry has no `book_appointment` tool. The replay's simulated booking appears only in Scheduling Encounter as a fixture and is not projected as an MCP step. The dataset category stays Planned · not run.

## Observer-first readiness contract (draft integration)
- Canonical PR181 requires an **existing** room, matching connected Veteran and registered `vab-avery` dispatch before issuing an observer JWT. A monitor must never create the room or dispatch Avery.
- `POST /api/msa-monitor` forwards **only** known, non-sensitive error codes: upstream 409 `voice_room_not_ready` → same-origin 409; upstream 503 `voice_room_readiness_unavailable` → same-origin 503. Unknown errors remain opaque 502 responses.
- The Command Center explains how to start the synthetic Veteran call first and permits retry. It does not auto-retry, retain the operator access code or pretend an observer connected.
- Remaining **live synthetic test**: exercise a room disappearing between readiness check and monitor connection, Veteran reconnect, and Avery worker restart. CI with mocked LiveKit does not prove provider uptime or race-free real media.
- This integration change is staged in a **separate draft frontend PR**. Do not deploy or enable the public monitor while backend PR181 and the identity authorization gates are pending.

## Private one-click demo call

Start Demo Call on the Command Center opens the real browser microphone and joins the backend-created LiveKit room through `/api/demo-call`, using `DEMO-PC-VOICE-INTAKE-001`. The browser gets only the short-lived participant token. The backend's case, interaction and voice session IDs go straight to the read-only observer. The observer retries only `409 voice_room_not_ready`, every 3 s for up to 20 attempts, until Avery is dispatched. Observer audio stays off by default to avoid echo. Hang Up ends the session and leaves the button ready to use again.

Neither BFF needs a typed operator code when all of the following are true. Otherwise it falls back to the existing operator-code path or stays disabled:
- `VAB_MSA_ONE_CLICK_DEMO_ENABLED=true`.
- The existing monitor gate and distinct secrets are set.
- `VAB_API_BASE_URL` is loopback.
- Both Host and Origin are localhost, or the current `$CODESPACE_NAME-<port>.app.github.dev` host over HTTPS.
- `Sec-Fetch-Site`, when sent, is same-origin.

The hosted preview shows "Live demo backend not configured". The manual connect sheet and separate caller page remain available under Advanced connection. Scripted replay is available under Advanced developer replay.

Untested here: two-sided LiveKit audio and real MCP calls. Both need the Codespace backend and the Avery worker running.
