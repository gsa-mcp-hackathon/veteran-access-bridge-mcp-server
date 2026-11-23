# Complete clickable handoff prototype

## Scope and state
This pass layers local UI simulation onto the Phase 1 VA-token operations shell. No backend, service, credential, real identity, production data, deployment or publication changes occurred. The canonical repository documents were not available in this checkout; the event contract below is a proposed future integration requirement, not a claim about existing APIs.

`src/lib/handoff.ts` owns independent media, ownership, verification and channel fields. `use-handoff.ts` stores one in-memory record per scenario. Scenario switches retain requests during this page session; Reset clears only the selected case. A refresh resets every fixture. No localStorage, database or actual audit persistence is used. The original appointment replay and approval guards remain separate.

## Clickable scenarios
Expand **Demo controls**, then use **Synthetic scenario replay** in Operations:
1. **Successful Primary Care**: routine verified script → eligibility → selection → slot verification → Veteran confirmation → autonomous simulated booking. No mandatory MSA approval. Avery's Work then progresses independent local artifact phases. Exception authorization remains separate from handoff ownership and cannot enable booking while identity is mismatched.
2. **Identity mismatch**: incoming → active → reviewing → mismatched → requested → pending. Open contextual Review → Accept handoff → Confirm acceptance. Ownership becomes accepted awaiting media join. Only **Simulate join call** creates the media-joined fixture and human handling. Avery becomes copilot. Choose a resolution and Close handoff.
3. **Rejected**: replay produces a fixture rejection with required reason and supervisor fallback. For manual rejection, use scenario 2, Reject handoff, enter a required safe reason and choose fallback, then confirm.
4. **Timeout**: pending → simulated timeout with supervisor fallback. Route safe fallback, retry while active, or close with resolution.
5. **Disconnect / reconnect**: pending request remains in the inbox after connection loss. Simulate reconnect restores active media but does not accept or join. Accept then join explicitly. Disconnect after joining clears media-joined and requires another join after reconnect.
6. **Race**: a fixture acknowledgement says another demo MSA accepted first. Acceptance again returns the existing owner; no second owner/join action. No live concurrency claim.

Play/pause/reset and Next fixture event are local controls. Silent monitor does not accept or join; Request takeover creates a requested record and requires a separate pending routing step. End clears media-joined but retains unresolved requests for fallback/closure. Alerts and priority queue labels project the same record; accepted-awaiting-join, rejected, timeout and disconnected requests remain actionable until resolved. Inbox filters support requested, pending, accepted, human, rejected, timeout and closed. Click any record to select its interaction and review it.

## Protected data
### UX acceptance recovery corrections
An ended or disconnected requested/pending case can use **Route safe fallback** to explicitly confirm the selected route locally, then choose a required non-booking resolution and **Close handoff**. This records synthetic fallback/closure only, never acceptance, matching, joining, transfer or booking. Active pending cases still require accept/reject/timeout; reconnect invalidates the terminal fallback shortcut. Duplicate route/close does not append audit entries. Historical MSA join transcript fixtures retain their first original event time across disconnect/reconnect; current joined status clears independently. The successful appointment queue projection retains its actual local completed/ended status, while unplayed handoff fixtures say Not replayed.

All handoff scenarios expose only identity status and self-reported safe request/preferences. Scheduling uses SafeHandoffContext instead of the Scheduling component on all A/B/C, desktop and drawer paths. No slots, appointments, providers, facility, approval or booking controls are rendered. Accept/join/close never marks identity matched. Review does not display raw DOB/last-four or private model reasoning. Handoff timeline events are explicitly synthetic UI projections, never fictional MCP speech or actual tool calls. The success scenario retains the original separately labeled synthetic MCP evidence.

## Proposed authoritative projection requirements (future integration gate)
The live system must confirm its actual event names/contracts before binding these UI projections. Every event requires `event_id`, monotonic `revision/sequence`, `occurred_at`, `session_id`, `case_id`, `request_id` where relevant, safe provenance and correlation. Duplicate/stale revisions must not alter state.

| Projection event | Required authoritative payload / behavior |
| --- | --- |
| `session.incoming`, `session.active` | Media transport lifecycle and channel; never infer connection from speech |
| `verification.reviewing`, `verification.matched`, `verification.mismatched` | Server verification status, access scope, safe reason code; no raw identity inputs in UI event |
| `handoff.requested` | Request ID, reason code, safe summary, captured-safe preferences, requesting actor/time |
| `handoff.pending` | Authorized destination/routing acknowledgement, deadline, eligible actor scope |
| `handoff.accepted` | Atomic compare-and-set acceptance acknowledgement, unique owner actor, acceptance revision, idempotency key/result; a client click is not authoritative |
| `handoff.rejected` | Authorized actor, reason, fallback route acknowledgement, request revision |
| `handoff.timeout` | Server deadline expiry, fallback acknowledgement; not a browser timer decision |
| `media.participant_joined` / UI projection `handoff.joined` | Transport-confirmed participant identity tied to the accepted owner/session; acceptance alone is insufficient |
| `session.disconnected`, `session.reconnected`, `session.ended`, `media.participant_left` | Transport status, reconnect generation, participant roster; clear joined state on loss/leave/end |
| `handoff.fallback_routed` | Authorized safe destination and routing acknowledgement |
| `handoff.closed` | Required resolution code, closing actor, audit reference, revision |
| `appointment.approval_recorded` and booking outcome | Existing governed scheduling lifecycle, separate from handoff ownership; only verified authorized access can expose protected scheduling |

Restart/refresh rehydration requires authenticated authorized reads of a consistent session/case/request snapshot with current revision, owner, verification access scope, media generation/roster, deadlines and durable audit reference, followed by replay/subscription from that revision. An unresolved request must survive disconnect; an ended session cannot retain a joined badge. Atomic acceptance/idempotency/race handling, role permissions, protected-data authorization, backend audit durability and real media acknowledgement are unresolved integration gates. This prototype implements none of those services.

## Validation
Current-encounter console checkpoint: 40 tests pass, zero lint errors/nine warnings, automatic build diagnostics OK. The unchanged handoff reducer retains 13 transition tests and two protected-boundary tests. Browser review exercised mismatch, rejected, timeout, disconnected/reconnected and other-owner race fixtures on mobile; no protected scheduling or artifact panels appeared, race exposed no second-owner join, and review Escape returned focus. Desktop acceptance and simulated join were distinct captures. Evidence is under `/tmp/browser/current-console/`. Routine autonomy is now separate from all exception ownership transitions; no acceptance, join or closure verifies identity or books an appointment.

November 9 acceptance polish: 30 tests pass; lint has zero errors/nine existing warnings; automatic build/TypeScript check reports build OK. Ended and disconnected pending/requested fallback closure, required outcome, idempotent fallback/closure, active-pending guard, retained historical join and closed mismatched data boundary have regression coverage. Chromium retested ended-pending recovery, focus trapping/return and mismatch across A/B/C at 1440×900, 768×1024 and 390×844; all six scenarios and original approval/decline were exercised at 390px. Screenshots are in `/tmp/browser/msa-polish/`. See the UI foundation guide for details. Durable fallback acknowledgement and cancellation/closure must still come from the authoritative system before any real integration; local fixture confirmation is not proof a callback or routing occurred.

Automated tests cover mismatch→requested/pending, accept≠join, required rejection reason/fallback, timeout fallback, disconnect request retention, reconnect owner retention/no automatic join, duplicate acceptance, race single owner, end/close and protected scheduling absence. Browser checks exercise all six scenarios, acceptance/join/duplicate result, resolution requirement, fallback fixtures, reconnect, race, mobile context protection, drawer Escape/focus return, original appointment approval and /design-system. No browser page errors were observed in that flow. Automatic build/typecheck and final test/lint results are recorded in the delivery summary.
