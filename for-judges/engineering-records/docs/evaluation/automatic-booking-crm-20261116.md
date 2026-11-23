# Automatic CRM booking notes — November 16, 2026

The existing trusted browser booking workflow now saves an automatic CRM summary
after an independently verified synthetic booking. This is a host-triggered side
effect, not an IBM-selected MCP write. The MCP inventory remains 25 with CRM
enabled; the original agent-selected CRM flow remains unchanged.

## Authority and failure behavior

The private host checks the active canonical call, verified identity, case and
voice binding. It independently recovers the appointment using its existing signed
recovery assertion. The recovered receipt must equal the verified booking receipt.
Only then can the private CRM writer generate a fixed summary containing the
appointment reference and verified start/end times. No caller transcript or model
text is used. It repeats the verification before CRM commit.

The note and audit record share one transaction under the existing restricted
Supabase role and forced RLS. An appointment-derived idempotency key and advisory
lock prevent duplicate notes on retries within the bound interaction. Conflicting
content fails. Audit payload and receipt record `invoked_by=host` and
`trigger=verified_booking`; the existing `AVERY` actor represents the application,
not a claim of independent model selection. Notes remain untrusted content for
future agent reads and confer no consent or booking authority.

A CRM failure never rolls back or resubmits a confirmed appointment. The caller
and Wrap Up show the note as pending. A later authenticated turn retries only the
note under the same key. A successful save is retained in call state and is not
written again. There is no background outbox or automatic restart recovery in
this slice; unresolved pending notes need operator reconciliation. Do not claim
exactly-once delivery across process loss.

## Validation

- Focused booking, CRM and projection checks: 99 passed.
- Backend CI 43891547252 on `a531d48`: 1,380 passed, 19 skipped; lint, format,
  package, installed-wheel and web build checks passed.
- Frontend CI 43891685350 on `cf95b1f`: 162 tests, lint, typecheck and build passed.
- Frontend package/runtime verification 43891690999 passed.
- Live acceptance passed on attempt 4. The previously approved CASE-041 booking
  is now consumed; do not reuse it for another booking.

Only receipt ID and SAVED/PENDING state pass to the browser, nested inside the
validated current-call booking proof. Raw note text is not forwarded. The UI
labels the origin as the trusted booking service, separately from MCP receipts.

## Retained rehearsal findings

The first attempt rejected a fragmented spoken name before booking. The second
verified identity but stopped before consent because the slot's November 15
verification exceeded the existing 15-minute freshness limit. Read-back confirmed
zero CASE-041 appointments and 35 total appointments. The same existing slot was
then rechecked with `verify_synthetic_voice_slot.py`, including case, patient,
channel, clinic, time and fixture provenance; its verification timestamp and audit
event were refreshed without changing the freshness rule or creating another slot.

A third attempt again rejected a fragmented name. The acceptance runner now caps
quiet caller-audio runs and waits conservatively for prompt playback, matching the
earlier CRM test. These are controlled test-audio conditions, not runtime identity
relaxations or evidence of general speech robustness. Failed calls were ended;
the case was confirmed unbooked before retries. Sanitized evidence is retained in
`evidence/automatic-crm-20261116/`; raw voice evidence remains private.

## Verified live result

Machine-readable evidence
records one controlled RTC call through reviewer login and the existing browser
API. The existing canary is revision `00032` (`a531d48`); frontend revision `00021`
(`cf95b1f`). Only images changed; configuration values and secret references were
compared and preserved. The voice worker and IBM agent configuration were unchanged.

| Check | Fresh database read-back |
|---|---|
| CASE-041 appointment | Exactly one; `d2fa9d7a-080d-534d-9ca7-2ba94da91ab9` |
| Automatic CRM note | Exactly one; `6af3b00c-8696-43be-bbee-ad892492e470` |
| CRM audit | Exactly one; matching host trigger, appointment, interaction and voice |
| Booking evidence | Identity and explicit confirmation linked to the same voice call |
| Repeated status question | No duplicate appointment or CRM note |
| Existing records | Total appointments increased from 35 to 36, exactly as approved |
| Frontend API | Verified booking proof included SAVED status, note ID and host origin |
| Call end | Confirmed |

Interaction: `int-01151f928b074df5`. Controlled call duration was 155.11 seconds,
including conservative playback waits; this is not a latency benchmark.
Actual browser rendering remains unverified, despite passing component tests and
live authenticated API delivery. General speech robustness, full CRM adversarial
coverage and durable background reconciliation are not established by this trial.
