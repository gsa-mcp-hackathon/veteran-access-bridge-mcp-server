# CRM rollout — November 16, 2026

Synthetic data only. Backend PR #207 and frontend PR #28 are draft branches;
neither main branch was overwritten.

## Verified deployment

| Component | Accepted source / revision | Evidence |
|---|---|---|
| Backend canary | `890166cc72bf3f272eb06a3e09324ca319240e51` / `00031` | CI 43886168756: 1,367 passed, 19 skipped; lint, format, package and installed-wheel checks passed |
| Frontend | `a0dca04` / `00020` | CI 43881282750: 159 tests, lint, typecheck and build passed; package/runtime verification 43880783130 passed |
| MCP catalog | 25 registered tools | Authenticated deployed discovery; all four CRM schemas include session scope; unscoped CRM read denied |
| Avery | 17 tool attachments | Original 13 plus four CRM tools; instructions and tool names export-verified |
| Supabase | Existing project, `vab_test` | 13 prior hosted acceptance checks passed; forced RLS, idempotency, version conflicts and cross-case rejection |

Backend deployment changed only the image and `VAB_ENABLE_CRM=true`. Frontend
deployment changed only the image; environment ordering differed, but values and
secret references were unchanged. Worker deployment was not changed. Reviewer
login remains enabled. Private configuration backups stay in the existing Codespace.

The installed IBM CLI does not refresh an existing MCP toolkit. A metadata PATCH
updated the selected names but did not register new schemas. The generic tools API
rejected MCP tool creation. The backed-up consolidated toolkit was therefore
re-imported under the same name, endpoint and connection, then Avery was rebound.
Only Avery consumed that toolkit. No second MCP server or duplicate active toolkit
was created. Other toolkit imports were left intact.

## CRM-only voice fixture

The existing voice persona `DEMO-PC-P114-001` had no persisted scheduling-case link.
Its exact synthetic name and birth date match the existing patient behind
`VAB-DEMO-20261113-CASE-005`. `prepare_crm_voice_fixture.py` creates one idempotent,
closed `CRM_ONLY_NO_BOOKING` request and case link for this persona. It does not
create a patient, slot, consent, authorization or appointment. The appointment
count remained 35. Existing cases and appointments were preserved.

## Retained voice failures and correction

Attempts 1 and 2 verified the synthetic caller and independently selected
`get_crm_case`, but the subsequent note request triggered another identity call.
The server rejected it. Each ended cleanly with zero CRM writes for its interaction
and 35 appointments unchanged. See `voice-attempt-01.json` and
`voice-attempt-02.json` in the linked evidence directory.

IBM trace `24bc42733156ba31ccd77e25624a4368` confirmed revision 12 received
`vab_identity_verified=true` and the correct authorized case. The repeat identity
call used the current scope, so this was not an expired capability or lost flag.
The per-turn user wrapper still carried the historical intake case. Commit
`890166c` removes that stale case and makes the opening defer to current registered
context. The server authorization rules remain unchanged. Thirty-three focused
voice tests and full CI (1,367 passed, 19 skipped) passed before canary revision
`00031` was deployed. The test harness now stops on a repeated identity call.

Raw IBM traces remain private because they include short-lived capabilities.
Public evidence includes only identifiers, outcomes and boolean comparisons.

## Receipt and rollout boundaries

The new Wrap Up panel accepts only call-bound server CRM receipts joined to a
unique IBM tool selection. The gateway strips notes and task descriptions. A saved
task is not evidence that staff were notified, completed work, or booked anything.

## Live CRM read/write acceptance passed

Attempt 3 completed a controlled
synthetic LiveKit voice call through the existing reviewer login and frontend API.
IBM independently selected one identity verification, two CRM reads, a note write,
a follow-up creation and a cancellation. All three write receipts matched unique
IBM tool-call IDs, the verified case, interaction and voice session. A fresh
read-only Supabase connection confirmed:

| Check | Observed result |
|---|---|
| Saved note | One note containing the requested morning-callback preference |
| Follow-up | One MSA task, due November 17 at 10:00 CST |
| Cancellation | Persisted `CANCELLED`, version 2 |
| Audit | Three matching transactional audit receipts |
| Appointment preservation | 35 before and after; no booking requested or created |
| Call termination | End request confirmed |

Interaction: `int-5d5ab16ba5c24135`. The measured call lasted 289.76 seconds,
including deliberate playback waits; it is not a latency benchmark. Caller audio
was synthetic TTS with quiet runs capped at 120 ms. This demonstrates one controlled
CRM conversation, not arbitrary speech robustness or a general success rate.
Both preceding failures are retained above.

Receipt delivery through the authenticated frontend API passed. Actual browser
rendering remains unverified because desktop browser automation could not start.
Component tests passed, but they do not substitute for visual acceptance.
This is not a full CRM adversarial evaluation. Production identity, retention policy, staff
workflow and external CRM/EHR integration remain outside this prototype.
