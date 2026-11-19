# Demonstration

**One Veteran. One Conversation. Connected Care.** This is a **synthetic** scheduling demonstration, not a live VA appointment service.

## Recorded demonstration

<div class="video-pending"><strong>Demonstration recording</strong><p>A final public video URL has not been supplied. This section intentionally does not imply that a recording is hosted or that a new call was run.</p><p>See the independently verified historical call below while final recording and visual acceptance are completed.</p></div>

## A verified scheduling journey · November 16, 2026

| Step | What happened | Enforcement / evidence |
|---|---|---|
| **01 · Greet** | Synthetic caller describes a Primary Care request | LiveKit/voice application |
| **02 · Verify** | Caller identity and session/case binding verified | Trusted host; not model-provided authority |
| **03 · Retrieve** | IBM selected patient summary and call knowledge tools | Scoped structured MCP reads |
| **04 · Search & select** | IBM selected `search_call_appointments` and `select_call_appointment`; two verified options returned | Selected option is **not** yet a booking |
| **05 · Confirm** | Host read back exact option; caller confirmed in a later turn | Current consent and policy checked independently |
| **06 · Book & wrap up** | IBM selected `book_call_appointment`; protected synthetic commit and host CRM write | Independently verified **one appointment**, **one CRM note**; receipt `BOOKED_SIMULATED` |

<small>Five distinct IBM-selected tool types are evidenced. Automatic host-written CRM work should not be falsely attributed to a separate agent tool call.</small>

## Proof beyond a spoken answer

The acceptance report for CASE-047 records a successful real-time generated-audio call using backend revision 00037 and frontend revision 00022. Independent persisted-record reads confirmed the synthetic appointment and CRM interaction. CASE-047 is **consumed historical evidence**; do not replay the write to re-demonstrate it.

[Read RTC acceptance and retained failures](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-agent-led-scheduling-20261116.md) · [Machine-readable proof JSON](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/agent-led-voice-20261116.json)

## Reproduce safe local behavior

```json
{"name":"get_scheduling_encounter","arguments":{"case_id":"DEMO-CARD-5000335-001"}}
```

Use the synthetic Cardiology and Primary Care fixture IDs listed in [Developer Guide](developer-guide.md), then try `UNKNOWN-CASE`. These read-only tests establish deterministic MCP behavior, **not** a new voice booking.

## What to show judges in five minutes

1. One-sentence problem and solution.
2. The MCP server and host authority boundaries.
3. The accepted tool sequence and the persisted synthetic booking receipt.
4. A real local MCP fixture read and unknown-case denial.
5. Evidence, limitations and source/reproduction references.

**No production VHA write access or clinical decision authority is claimed.**
