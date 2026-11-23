# Agent-led scheduling work — 16 November 2026

Feature branch: `feat/avery-agent-led-scheduling`. One real RTC acceptance call
passed on canary revision 00037, using VA sandbox reads and one Supabase test
appointment. This does not establish a production VA booking.

## Intended call

Call in Browser → trusted caller/session verification → patient-confirmed time
zone → IBM-selected VA sandbox patient read → appointment preferences → IBM-selected
appointment search → in-chat appointment cards → IBM-selected option → exact host
readback → caller confirmation → IBM-requested, policy-checked booking → independent
receipt → automatic CRM note. Relevant KB and CRM reads remain agent-selected.

The LLM supplies preferences and option choice. It never supplies identity,
consent, signing credentials, policy grants or booking receipt evidence. Changed
or ambiguous answers invalidate the previous readback. Selection and confirmation
cannot share a turn. A repeated booking call cannot create another appointment.

## Sources and limitations

- Patient: existing VA Patient Health sandbox credentials, explicit approved
  case-to-ICN mapping and per-API allowlist. Live returned name and birth date must
  independently match the verified test case. Demographics do not establish PACT
  assignment or a doctor relationship.
- Availability and booking: existing Supabase `vab_test` inventory. A fresh,
  locked read of the test slot is audited before updating its verification time;
  existing 15-minute consent/commit freshness gates remain. This is not a VA
  production availability check.
- Provider/clinic: source clinic name and explicit provider-name metadata only.
  Missing names remain unavailable; no generated doctor or PACT assignment.
- Knowledge: existing least-privilege KB reader. Read-only inspection found 58
  draft/unreviewed revisions, all publication-disabled. These are project drafts,
  not official VA policy. Retrieval cannot authorize a booking.
- CRM: existing scoped tools and separate automatic post-booking note. Booking
  success and CRM persistence are separate outcomes.

## Rollout requirements

1. Pass Linux backend CI, frontend tests/typecheck/lint/build, and source adapters.
2. Independently test the new inventory-recheck SQL using the existing restricted
   test role; verify rollback, wrong-case, unavailable-slot and expiry denials.
3. Back up current existing canary, toolkit and Avery configuration privately.
4. Bind existing VA and KB configuration to the canary. Correct the known VA
   client-ID mismatch using existing working protected configuration; do not
   print keys or change other services. Explicitly map the rehearsal case.
5. Publish/deploy only the existing canary and frontend. Enable
   `VAB_ENABLE_AGENT_SCHEDULING=true` only after the prerequisites pass.
6. Refresh the existing consolidated toolkit and attach the four new guarded
   voice tools. Server counts: baseline 21, CRM-enabled 25, CRM plus this workflow
   29. Tool aliases in the frontend are presentation labels, not inventory proof.
7. Apply revision-13 instructions and register `vab_workflow_stage`,
   `vab_patient_time_zone` and `vab_scheduling_instruction` alongside the existing
   three context variables.
8. Prove native IBM tool selection and server receipts for access/read/write.
   A host call or application event alone cannot establish agent selection.
9. Run one authorized voice booking, inspect in-chat cards and patient-local
   readback, independently verify appointment and CRM, and measure latency.

Rollback: disable the new feature flag, restore the saved agent/toolkit
configuration and previous frontend/canary image. Existing appointments remain.

## Initial local evidence (not live acceptance)

- Frontend: 169 tests passed, TypeScript passed, production build passed.
- Backend before the final new tests: 1,404 passed, 17 skipped, one Windows
  file-permission test failed. Linux verification is required; no security gate
  is being removed to accommodate Windows.
- Focused VA adapters, identity matching, MCP scope and voice checks: 113 passed.
- Changed Python files passed Ruff. The repository-wide lint command also reports
  pre-existing issues outside the CI lint scope; this change does not claim to
  resolve them.

## Verified rollout and rehearsal findings

- CI for `6aeee09198abbcc1d5348637b2d08357099747de`: **1,440 passed,
  19 skipped**; lint, formatting, packaging and installed-wheel smoke checks passed.
  [CI evidence](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/ci/ci-run-43971279885.md).
- Focused Linux conversation, MCP scope and trusted voice regressions: **118 passed**.
- Frontend revision `vab-avery-callcenter-00022`, image commit `3e0f031`, is deployed.
  An authenticated headless Edge inspection found Call in Browser and no page
  errors. This initial-page check does not by itself prove live calendar rendering.
- The deployed MCP endpoint returned **29 tools**. IBM contains exactly one
  consolidated toolkit with **29 registered tools**; Avery has **21 attached tools**.
  The existing IBM agent, model and security plugin were preserved.
- Unauthenticated MCP access returned **401**; the frontend protected root
  redirected to login (**303**). A bearer-authenticated booking request without
  a trusted voice scope was denied.
- The VA sandbox Patient response for the approved Judy fixture matched the
  stored identity. Neither `generalPractitioner` nor `managingOrganization` was
  supplied. Doctor and PACT assignment are therefore unavailable, not inferred.
- CASE-047 uses two existing, explicitly bound test slots. Previous bookings
  remain intact. Each retry requires an independent check that CASE-047 has zero
  appointments; the authorization permits at most one new appointment.

Rehearsal failures are retained privately rather than counted as passes:

1. IBM selected the KB tool before the required VA patient read. The server denied
   it with `Verified VA patient read required first`. Instructions were clarified;
   the prerequisite was not removed.
2. IBM independently selected and completed both the VA patient read and KB read,
   with native call events matched to server execution receipts. The KB query
   returned no matching guidance, so the scripted draft-guidance expectation
   timed out. Instructions now describe the literal keyword search behavior.
3. IBM restarted intake despite the current verified scope. Host-handled identity
   and timezone turns were absent from IBM dialogue history. Commit `6aeee09`
   adds a current host handoff summary only inside an active verified scope.
   Caller claims cannot trigger that summary; it grants no consent or receipt.

All three attempts stopped before appointment selection or booking. No successful
end-to-end booking is claimed by these intermediate findings. Raw private
configuration backups, transcripts and capabilities are not published to GitHub.

## Final RTC acceptance — passed

The fourth attempt passed after the handoff correction. The existing live voice
worker carried generated caller speech over real LiveKit RTC; the existing IBM
agent selected the tools. No direct booking request or fabricated identity
assertion was substituted for the voice flow.

| Capability | Verified evidence |
| --- | --- |
| Access | IBM-selected `get_va_patient_health_sandbox_summary`, matched to server receipt |
| Knowledge read | IBM-selected `search_call_knowledge`; Avery explicitly described the results as unapproved drafts |
| Availability read | IBM-selected `search_call_appointments`; two case-bound options projected to the authorized activity feed |
| Selection | IBM-selected `select_call_appointment`; exact host readback in Central time |
| Guarded write | IBM-selected `book_call_appointment` after the caller said “Yes, please” on a later turn |
| Persistence | Independent scoped SQL read found exactly one CASE-047 appointment; total appointments increased from 37 to 38 |
| CRM | Independent scoped SQL read found one matching automatic booking note and event, linked to the same appointment and voice session |
| Duplicate prevention | “Is my appointment already booked?” returned the existing confirmation; appointment count remained one |

The appointment is November 26, 2026 at **9 AM CST**, in test inventory. The
automatic CRM note is **host-invoked**, not an independently selected IBM CRM
write. This distinction is retained in the evidence.

[Machine-readable acceptance summary](../evaluation/agent-led-voice-20261116.json).

Observed response-to-first-audio delays across nine turns were **1.167–13.720
seconds**, median **4.879 seconds**. The run lasted 298.86 seconds including
deliberate test pacing; that is not a real-user call-duration benchmark. Generated
caller audio had quiet runs capped at 120 ms. Human speech, interruptions, accents
and noisy microphones still need separate evaluation.

Latency remains a follow-up: the successful run repeated the VA patient read three
times and availability search twice. Preserve verified source/option context
across IBM turns before considering caching; retain freshness, scope and consent
gates. Do not claim the latency problem is solved.

Calendar rendering has component-level tests for local time, source-only provider
information and cross-call rejection. The live RTC acceptance verified the actual
two-option projection. The separate browser inspection verified the authenticated
initial page, not a screenshot of the populated calendar during this call.

CASE-047 is now consumed. Do not run the booking harness against it again or reset
its records. A future booking rehearsal needs a separately approved unused fixture.
