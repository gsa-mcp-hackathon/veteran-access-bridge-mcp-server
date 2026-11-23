# Screen A next milestone: live, expandable Avery execution evidence

**State recorded:** November 10, 2026 (America/Chicago); source worker registration 2026-11-11 UTC.  
**Current deployment:** `vab-avery-callcenter`, using the existing backend M6.4 canary and `vab-avery` LiveKit worker.  
**Voice checkpoint:** LiveKit registered worker + browser media connection and mic publication observed; user reported call worked. **MCP/DB real-time activity not accepted yet**.  
**Companion canonical checkpoint:** backend `veteran-access-bridge/docs/checkpoints/2026-11-10-avery-voice-live-activity-checkpoint.md`.

## The user story

As the Veteran or authorized scheduler interacts with Avery, the **Scheduling Encounter**, **Agent Activity**, and **Timeline** must advance from the *same verified backend event source*, in real or near-real time. Avery's actual MCP calls, approved data-source reads, and governed state changes must be **visible as expandable tool-operation cards**, in the familiar style of ChatGPT or Claude's tool activity view, with no fabricated events or disclosure of model-private reasoning.

The UI must remain useful when the tools are unavailable: preserve the call, show a specific operational-feed warning, and do not invent a tool invocation, slot or booking.

## Observed defect / source-verified flow

User browser log contains `POST /api/msa-monitor → 403` while LiveKit goes `connecting → connected` and publishes microphone track.

Current implementation:
- `src/components/msa/autonomous-screen-a.tsx`: `onSession` invokes `monitor.connect` with optional access code; no code is supplied by the hosted public guest call.
- `src/components/msa/use-live-monitor.ts`: observer token request goes to the separate same-origin `/api/msa-monitor` route; without code it omits bearer authorization.
- `src/routes/api/msa-monitor.ts` and `src/lib/one-click-gate.ts`: this route requires operator-code authorization on hosted Code Engine (the one-click bypass is strictly private Codespace/loopback). Hence 403.
- `src/lib/public-guest-gate.ts`: public guest capability deliberately authorizes only `/api/demo-call`, **not** staff monitor access. Do not broaden it.
- Backend monitor must also be explicitly enabled with a private service key; deployed value has not been verified.
- `use-live-monitor.ts` polls in a serialized loop every `2500` ms after successful authorization; current event feed is not truly pushed.
- `src/lib/live-monitor.ts` sanitizes and correlates events, while `src/lib/mcp-execution.ts` derives MCP tool steps from `mcp_tool_called` and `mcp_tool_result`.
- `src/components/msa/screen-a-evidence.ts` correctly refuses to infer booking from voice; `SchedulingEncounter` in `autonomous-screen-a.tsx` still has static care-type, slot, booking and calendar placeholders pending actual backend evidence.
- **Typed-event mismatch:** `screen-a-evidence.ts` checks `intent_identified` and `intake_completed`/`structured_intake_completed`, but the backend's `live_interactions.py` currently emits `intent_captured` for recognized Primary Care intent and does not emit those intake-complete event types in that path. Even after fixing monitor authorization, the workflow stages cannot advance reliably until event taxonomy and criteria are reconciled with the canonical backend.

**Do not fix 403 by turning the guest call into an anonymous privileged monitor.**

## Proposed Screen A display

### Live Conversation tabs (same UI region)

**Transcript** — authenticated LiveKit speech captions while available; separate interim from final. Do not replace with fabricated or inferred speech. Label absence transparently.

**Agent Activity** — each observed operation is an expandable item. The summary row shows actual name, class/source, live status, elapsed duration and timestamp. Expanded panel shows allowlisted structured metadata and outcome evidence, not hidden thoughts, raw SQL or identifiers.

**Timeline** — all call-scoped canonical events in chronological order: caller joined, intent observed, verified identity, MCP tool requested/completed/failed, approved sandbox data source read, option selected, confirmation, approval, simulated write, durable read-back, notifications, call ended. Do not assert any event absent its explicit backend receipt.

### Scheduling Encounter (right rail)

Keep **Intake → Verify → Search → Select → Confirm → Book**. Each stage becomes `pending`, `running`, `complete`, or `blocked` only from a domain event or a supported verified operational result. Display the data source for calendar/availability where authorized. Show a distinct consult/eligibility/authorization gate for specialty/Community Care. Show `Booked` and after-call artifacts only after governed simulated commit and persisted read-back/receipt.

### Example of a safe expandable tool-activity row

```text
[✓] Avery → MCP: verify_synthetic_identity       Succeeded  11:26:03
    Tool call: call_… (opaque scoped ID)
    Source: governed VAB MCP
    Outcome: verified synthetic case [only if verified by tool result]
    Correlation: current interaction only

[⋯] Avery → MCP: search_availability            Running    11:26:08
    Source: governed availability adapter
    Outcome: awaiting authoritative result

[!] Database write: record_option_selection   Not observed
    No verified database write event / commit acknowledgement
```

These are **illustrative labels only**, not records from the completed call. Never render an example as live activity.

## Event contract and integration steps

1. **Authorized feed:** establish either explicit, actor-bound operator authentication or a new reviewed short-lived, per-call, read-only activity capability. Retain the existing separate guest-call and staff-monitor gates. Never grant a guest LiveKit observer audio, external MCP tools or scheduling write access.
2. **Canonical correlation:** project events only when case ID, interaction ID, voice session ID, correlation ID and source match the active call. Deduplicate by event ID and tool call ID. Handle reconnect, ordering, expired capability and backend restart.
3. **MCP instrumentation:** consume *observed* watsonx tool executions and canonical VAB MCP events. Show `called`, `running` (only with true start event), `succeeded`, `failed`, `unknown`; distinguish returned tool results from claimed actions in speech.
4. **Database/source operations:** show `Read`, `Query`, `Write requested`, `Approved`, `Persisted`, `Read-back verified` only with corresponding source-audit events. Do not label a remote HTTP API read, in-memory fixture lookup or `record_option_selection` as a database commit unless verified.
5. **Transport:** keep a fail-closed, cursor-based non-overlapping poller initially; move to authorized SSE/server push only if it improves actual latency and retains safe reconnection. Set a visible feed status: `Live`, `Reconnecting`, `Delayed`, `Unauthorized`, `Unavailable`.
6. **One projection:** all three panels and after-call work derive from the same canonical event model and receipts. No duplicate frontend scheduling state or independent inferred MCP stream.
7. **Sandbox data connection:** read-only use of *approved synthetic* VA API sandbox patient after backend case mapping and source authorization are reviewed. Existing current call-launch intake case is `DEMO-PC-VOICE-INTAKE-001`; do not silently swap it for arbitrary patient IDs. Do not infer live slots from facility directory or eligibility responses.

## Acceptance tests (must pass before declaring this milestone complete)

- Hosted authorized call can connect and remain live while the operator/call-scoped event feed receives actual events without 403.
- Unauthorized hosted observer, expired session, altered case ID, wrong origin, cross-case, and wrong correlation still reject.
- A real call invokes one approved MCP tool and produces a matching called/result pair with source, timestamps, tool call ID and truthful outcome; expandable row visible in Agent Activity and the same evidence in Timeline.
- A second independently observed MCP read appears and advances **Search** only if successful authorized availability evidence exists; static/fixture values are not blended in.
- Separate DB/read/write source events display only when an auditable adapter or database operation occurred; no claims of durable state without read-back.
- Reconnect does not duplicate rows or regress completed stages, and stale event streams are explicitly labeled.
- Authorized VA API sandbox read-only case mapping uses the approved synthetic patient; no arbitrary identities or protected content in browser/telemetry.
- Inspect mobile and desktop: expand/collapse with keyboard, distinct status and error badges, accessible timestamps, and bounded scroll.
- Existing LiveKit audio, mute, hang-up and worker dispatch remain functional.
- Synthetic-only booking and all staff approvals remain governed; no change to main VAB backend, production VA data sources or Code Engine voice resources.

## Implementation boundaries / sequence

This is a **design + defect-triage document only**. No frontend code, deployment configuration or authorization was changed by this checkpoint.

Recommended small implementation sequence:
1. Investigate/prove monitor auth + backend readiness with tests, without disabling any protection.
2. Implement the reviewed session/actor-bound **read-only** events API and normalize MCP/source event metadata.
3. Wire Screen A's authorized event source to the three panels; add expandable activity details.
4. Add real source-operation adapters/audit and receipt-controlled scheduling evidence; test read-only VA API sandbox case.
5. Run end-to-end verified voice → MCP tool → source read → UI event acceptance with real logs, then consider governed synthetic write flow.

Keep implementation in small reviewed PRs across these two repositories. Do not disturb active local `docs/sprint6-combined-integration-gates` development or re-deploy the healthy voice worker for a documentation update.
