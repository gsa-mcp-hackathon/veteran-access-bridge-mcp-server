# 03 · Demonstration

[**Watch the recorded call (MP4, 3:39)**](../../docs/assets/avery-demo.mp4) · [Interactive walkthrough](../../docs/demonstration.md) · Same call as presentation slides 10–11

## The call at a glance

| | |
|---|---|
| Caller | Synthetic Veteran, case `DEMO-PC-VOICE-INTAKE-001` |
| Request | Schedule a Primary Care appointment |
| Agent | Avery, IBM watsonx Orchestrate, Claude Sonnet 4.6 |
| Outcome | Primary Care, **Friday, December 4, 2026, 9:00 AM CST**, Colmery-O'Neil VA Medical Center |
| Proof | Synthetic confirmation `51976dfb-30da-5f04-a628-e9ca1ec31fd9`, confirmed by independent database readback |
| Tool calls | 7 in total; IBM selected 4 MCP tools |

## Step by step

| # | Stage | What happens | Who decides |
|---|---|---|---|
| 1 | Greet | The caller asks to schedule Primary Care. This starts the conversation but grants nothing. | n/a |
| 2 | Verify | The trusted voice service verifies the caller and binds the call to one case. The model cannot assert identity. | Trusted voice host |
| 3 | Retrieve (~2:00) | Avery calls `get_va_patient_health_sandbox_summary` and receives only the permitted, case-scoped summary. | MCP server scope check |
| 4 | Search and select | Avery calls `search_call_appointments` and offers two verified openings: **Thu, Dec 3 at 10 AM** and **Fri, Dec 4 at 9 AM CST**. The caller picks Friday; `select_call_appointment` records the choice. Selecting is not booking. | Deterministic slot services |
| 5 | Confirm | The selected time is read back and the caller gives a separate, current confirmation. | Trusted voice host |
| 6 | Book (~3:12) | Avery calls `book_call_appointment`. Trusted services check identity, consent, slot and policy, commit the booking once, and read it back from the database before reporting success. | Deterministic booking service |
| 7 | Wrap up (~3:36) | After hang-up, the trusted booking service saves a CRM note and generates a confirmation letter (not sent). | Trusted booking service |

## What to watch for

- **Verification happens before any patient data is read.** The health-summary read comes after the trusted host binds the caller to the case.
- **Two options, then a readback.** The agent offers choices it received from the server; it does not invent times.
- **"Booked" is only said after readback.** The confirmation number comes from the database record, not from the model.
- **The after-call work is done by the trusted service, not the agent.** The CRM note and letter are written after the call ends.

## What this demonstration does not show

- It is one synthetic call, not a load or repeatability test.
- It does not show an attack. Adversarial results are in [Section 04](../04-evaluation/README.md) and [Section 05](../05-security/README.md).
- The confirmation letter is generated but not sent, and no production VA system is touched.
- Do not replay this booking: the synthetic slot and case are consumed.

## Earlier accepted trial

A separate controlled call on **November 16** (case `CASE-047`, backend revision 00037) reached one independently verified synthetic appointment and one host-written CRM note, with five IBM-selected tool types and a `BOOKED_SIMULATED` receipt. It is documented as its own record and does not validate later releases.

**Evidence:** [Nov 16 acceptance record](../engineering-records/docs/operations/avery-agent-led-scheduling-20261116.md) · [Nov 16 machine-readable evidence](../engineering-records/docs/evaluation/agent-led-voice-20261116.json) · [Evidence boundaries](../../docs/evaluation/validation-agent.md#end-to-end-voice-trial)

## Try it without a voice setup

You can call the same server locally with a read-only synthetic case in a few minutes; no IBM or voice credentials are needed. See [Section 06](../06-reproducibility/README.md).
