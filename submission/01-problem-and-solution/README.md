# 01 · Problem and solution

**Use case:** Veteran Access Bridge is a secured MCP server that gives any SI agent 29 validated tools to look up VA health summaries, search open slots and book appointments for Veterans. The IBM watsonx Orchestrate voice agent Avery uses those tools to complete a booking on a single call.

**Track:** Service: Write.

---

## The problem

Scheduling a VA appointment by phone is a sequence of checks that a Medical Support Assistant (MSA) performs by hand: confirm who is calling, find the right case, read the patient's context, decide which clinic and appointment type apply, find an opening that matches, read it back, get the Veteran's agreement, book it and record what happened. Each step depends on the one before it, and getting one wrong produces a wrong booking or a disclosure to the wrong person.

An SI agent can run that conversation, but it introduces a new risk. A language model can be talked into things: a caller can claim to be someone else, a document can contain instructions, and the model can say "you're booked" without a booking existing. The question this project answers is:

> **How do you let an SI agent act on a Veteran's behalf, including writing records, without trusting the model with identity, consent or booking authority?**

## The solution

Veteran Access Bridge puts a **governed MCP server** between the agent and the scheduling systems. The agent can only act through typed MCP tools, and every protected action is decided by deterministic backend services, not by the model.

| The agent can… | Only the server and trusted services can… |
|---|---|
| Choose which MCP tool to call | Verify the caller's identity and bind the call to one case |
| Supply allowed arguments | Decide whether the caller may see that case |
| Read back the options it was given | Check eligibility, appointment type and slot freshness |
| Request a booking | Confirm current, explicit Veteran consent |
| Summarize results to the caller | Commit the booking, write the receipt and confirm it by database readback |

**Core rule:** the SI agent requests; the server decides. A successful tool call, a case ID supplied by the model or a spoken "you're all set" is never treated as authorization or as proof of a booking.

## Why this is a Service: Write entry

The server's core job is completing actions safely. **10 of its 29 tools change records:**

| Write tool | What it changes |
|---|---|
| `select_call_appointment` | Records which offered slot the caller chose (not a booking) |
| `book_call_appointment` | Requests a protected synthetic booking, subject to identity, consent, slot and policy checks |
| `record_option_selection` | Records a scheduler's selection in the restricted handoff path |
| `prepare_scheduling_handoff` | Creates a handoff artifact for human review |
| `prepare_veteran_confirmation_request` | Prepares a confirmation request for the Veteran |
| `record_veteran_confirmation` | Records the Veteran's confirmation response |
| `record_lifecycle_event` | Records a governed case lifecycle transition |
| `record_crm_interaction` | Writes a CRM interaction note |
| `create_crm_follow_up` | Creates a CRM follow-up item |
| `update_crm_follow_up` | Updates a CRM follow-up item |

The other 19 tools are read-only: identity verification, workflow state, availability, access standards, VA sandbox facility and health summaries, CRM case reads and call-scoped knowledge search. Every write tool was probed with forged authority on November 21, and none succeeded (86/86 hostile-argument checks; see [Section 04](../04-evaluation/README.md)).

## What it looks like in practice

In the [final demonstration call](../03-demonstration/README.md) (3:39), a synthetic Veteran calls to schedule Primary Care:

1. A trusted voice service verifies the caller before any patient data is read.
2. Avery reads the permitted health summary (`get_va_patient_health_sandbox_summary`).
3. Avery offers two verified openings, Thursday, Dec 3 at 10 AM and Friday, Dec 4 at 9 AM CST (`search_call_appointments`), and the caller picks Friday (`select_call_appointment`).
4. The selected time is read back and the caller confirms.
5. Avery requests the booking (`book_call_appointment`). Trusted services check identity, consent, slot and policy, commit the booking and confirm it by independent database readback: synthetic confirmation `51976dfb-30da-5f04-a628-e9ca1ec31fd9`.
6. After hang-up, the trusted booking service saves a CRM note and generates a confirmation letter (not sent).

## Who benefits

- **Veterans:** one conversation from request to confirmed appointment, with a readback before anything is booked.
- **Schedulers and MSAs:** routine Primary Care bookings handled end to end, with Community Care and exception cases routed to human review through the restricted handoff tools rather than decided by the agent.
- **Agencies building SI agents:** a reusable pattern in which any MCP-capable agent, not just Avery, can be given useful write tools without being given authority.

## Scope and boundaries

- All data is synthetic. VA interfaces are read-only government sandbox adapters; appointments and CRM records live in a synthetic Supabase PostgreSQL database, not in VistA, HSRM or any production VA system.
- No production VA booking, operational time-savings or security-certification claim is made.
- Known open items are listed in the [submission index](../README.md#known-limitations-not-claimed) and [Section 05](../05-security/README.md).

**Read more:** [Solution overview](../../docs/index.md) · [Architecture](../../docs/solution-architecture.md) · [MCP implementation](../../docs/mcp-implementation.md) · [Engineering decisions](../../docs/developer-guide/engineering-decisions.md)
