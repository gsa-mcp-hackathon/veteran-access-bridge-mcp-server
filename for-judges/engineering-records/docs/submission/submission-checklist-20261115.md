# Submission checklist

Status reviewed November 15, 2026. GSA lists November 20 as the due date; the submission portal, exact cutoff and organizer access arrangement remain unconfirmed. Source: [GSA event requirements](https://www.gsa.gov/super-intelligence/si-community-of-practice/events-and-training/mcp-server-and-si-agent-government-hackathon), reviewed November 15.

## Completed

- [x] Preserve the MCP server as the central evaluated component: 21 registered tools and separately evidenced IBM-selected case reads.
- [x] Retain separate test denominators, original failures, DeepEval adapter correction and partial-coverage limitations.
- [x] Deploy restricted reviewer login and request limits; nine live access/session checks passed. The user independently confirmed login worked.
- [x] Archive only the approved obsolete toolkit directory; keep CI-used components.
- [x] Update and inspect all 12 slides and four evaluation pages in review v2.

## Remaining in order

1. Presenter reviews the v2 deck and evaluation document for agency wording and final claims. They remain review editions.
2. CASE-041 was booked on November 16: one appointment and one automatic CRM note passed database and frontend API verification. Visual receipt acceptance remains open. Do not rebook this consumed case; a new recorded booking requires an explicitly approved unused fixture. See `docs/evaluation/automatic-booking-crm-20261116.md`.
3. Record the presenter-as-caller demonstration with synthetic data. Sign in privately before recording; never show the access code. Keep separate recorded IBM read evidence clearly labeled.
4. Review remaining backend advisories and the moderate frontend development dependency finding. Document accepted residual risks and incomplete concurrency/recovery/injection coverage. No certification or full-suite completion claim.
5. Confirm organizer acceptance of restricted internet-hosted reviewer access. Login is not evidence of organizer approval. Confirm the portal, exact cutoff, required uploads and reviewer credential delivery method privately.
6. Review and merge the applicable PR chain through normal checks, then pin the final repository commit and reconcile the artifact links. Do not rebuild or deploy an untested merged tree.
7. Upload the documented MCP repository, slide deck and evaluation document through the confirmed process. Verify receipt and retain submission evidence. This checklist does not authorize guessing a destination or making the prototype public.

## Criteria and evidence

| GSA criterion | Reviewer evidence |
|---|---|
| Technical quality: maintainability | Module boundaries, structured schemas and readable repository setup |
| Technical quality: performance and reliability | Explicit inputs, pass/fail counts, safe errors, retained failures and scope limitations |
| Technical quality: MCP design | Meaningful tools, validated arguments and IBM-native selections matched to server receipts |
| Innovation | Voice-session binding with separate deterministic booking authority |
| Mission alignment | Synthetic Veteran scheduling coordination; operational time savings remain a hypothesis |
| Presentation | Problem, solution, technical decisions, timed caller demo and testing evidence |

No combined security percentage, 48/48 scenario claim, live VA booking claim or independently selected-and-committed IBM booking claim is supported by the current evidence.
