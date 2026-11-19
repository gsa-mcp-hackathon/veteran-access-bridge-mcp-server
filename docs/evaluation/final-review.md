# End-to-End & Final Review

**Status:** successful historical synthetic end-to-end scheduling **at a pinned revision**; final presentation and broader evaluation gates are separate.

<div class="ev-meta"><span>Voice RTC trial: November 16, 2026</span><span>Receipt: BOOKED_SIMULATED</span><span>Persistence: one appointment + one host CRM note</span><span>Production VA writes: none</span></div>

## What passed

A controlled real-time test using generated caller audio exercised IBM-selected patient retrieval, knowledge search, appointment search, option selection and booking request tools. Trusted services independently checked scope and current confirmation and recorded the synthetic booking. Database reads confirmed **one appointment and one host-written CRM note**. This was a proven journey **at that specific revision**, not a new November 19 booking trial.

## What subsequent reviews added

- November 18 spoken identity and caption-masking acceptance (identity-only; no booking).
- November 19 **16/16** matched local Primary Care gold-question answers.
- November 19 **135/135** deterministic protected booking / consent / CRM control checks, grouped for Phoenix review.
- November 19 voice–database evidence reconciliation identified gaps in independent before/after snapshots for earlier attack sessions.

## What remains open

| Area | Required evidence |
|---|---|
| Later revision acceptance | A separately authorized run on fresh synthetic cases if the release changes |
| Security | Expanded attack coverage, paired DB checks, distinct-session isolation, dependency triage |
| Reliability | Hosted multi-writer concurrency and uncertain-write recovery checks |
| Delivery | Final recorded browser presentation and visual verification of receipt/letter flow |
| Reproduction | Pinned final release and locked dependency freshness |

## Evidence archive

[Accepted booking proof](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/agent-led-voice-20261116.json) · [Accepted real-time call report](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-agent-led-scheduling-20261116.md) · [November 19 reviewer record](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/README.md)

**Read next:** [Evaluation Overview](index.md) · [Developer Guide](../developer-guide.md)
