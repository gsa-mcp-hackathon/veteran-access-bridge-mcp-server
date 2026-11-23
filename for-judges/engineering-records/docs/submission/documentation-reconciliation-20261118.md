# Documentation reconciliation — November 18, 2026

The current documentation must state that **end-to-end synthetic scheduling was proven** in the November 16 agent-led RTC trial. Later configuration and identity checks have narrower scopes; they do not erase the successful booking evidence.

## Review basis

Backend source/evidence snapshot: `5b6cd072f23b4d4edce2e19c4f75faa774c87988`. Frontend snapshot: `3b3557731679d5ae481788115c07d3f9e29d8165`. These are candidate snapshots, not a merged/tagged submission. Backend main was observed at `fc95dcd4bd1481884b820968d946e41fadc1ec82`.

Reviewed sources include both repository READMEs and documentation indexes, backend QUICKSTART, Inspector guide, submission architecture/demo/evaluation/evidence/decision records, current-system architecture, scheduling-policy scenario matrix, release/security/booking/identity/configuration reports, Orchestrate README/configuration/evaluation scripts, both agent YAML definitions, eval READMEs, source registration/contracts, relevant tests and CI workflow. Frontend review includes current README, deployment inventory, voice/call implementation descriptions and preserved screenshot assets.

## Reconciliation decisions

| Claim or conflict | Evidence / accurate interpretation | Correction |
|---|---|---|
| No end-to-end agent-selected booking | [November 16 RTC acceptance](../operations/avery-agent-led-scheduling-20261116.md) and [JSON](../evaluation/agent-led-voice-20261116.json): PASS; five IBM-selected tool types; one appointment and one host-written CRM note | Lead wiki with this demonstrated capability; retain November 15 read-only evidence as historical |
| Two tools and no remote transport | [Registration](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/__init__.py) plus ASGI host | Rewrite Inspector guide; distinguish local stdio from authenticated HTTP |
| 21 / 25 / 29 tools | Default 21; four optional CRM; four optional voice tools | State configuration and milestone for every count |
| 22 agent attachments / 21 tools | [November 18 configuration record](../evaluation/guidelines-and-tool-inventory-20261118.md): earlier 21 MCP plus one workflow; workflow later detached | Current recorded assignment: 21 MCP tools, eight guidelines, no paused workflow; no new voice regression claimed |
| M6.4 Draft-only | Original ten-tool bootstrap imports a draft; later consolidated runtime has explicit publication evidence | Mark old bootstrap and runbooks as dated, not a full latest-state reconstruction |
| Dry run verifies IBM setup | configure-m64 only prints commands when DryRun is true | Explicitly call it a preview; hosted verification requires actual authorized reads |
| Environment selected once | Evaluation runners activate EnvironmentName, default veteran-access-dev | Pass environment explicitly in wiki commands |
| CASE-041 unbooked | [Automatic booking/CRM report](../evaluation/automatic-booking-crm-20261116.md) confirms later persistence | Preserve historical report with supersession notice; do not rebook consumed case |
| All bookings require manual Scheduler approval | Routine internal Primary Care uses separately trusted policy grant; Community Care retains independent authorization requirements | Describe both paths; model cannot self-issue consent or grant |
| Latest README deployment numbers | README includes several earlier snapshots; spoken identity records backend 00056, worker 00009 and frontend 00030 | Mark earlier snapshots and link this index; never imply a new live inventory was performed |
| Fixed five-minute calls | Later frontend uses participant-bound renewal, retaining expiry on failed renewal | Correct frontend README; preserve historical expiry test |
| Locked setup reproducible | Fresh Python 3.12.9 uv sync --locked failed because uv.lock needs updating | Disclose failure; document editable-install alternative without changing lock/dependencies |
| Aggregate evaluation score | Historical 7/7, M6.3 ten executions, M6.4 thirteen assets, 25-tool checks and 29-tool inventory are distinct | Keep denominators, commits and execution scopes separate |
| Final review artifacts are current | Review-v2 deck/evaluation predate later acceptance | Preserve them as dated review editions; update remains a submission task |

## Current evidence map

- [End-to-end synthetic scheduling](../operations/avery-agent-led-scheduling-20261116.md): observed booking at backend 6aeee09 / revision 00037 and frontend 3e0f031 / revision 00022.
- After-call work: separate CASE-048 trial, saved wrap-up/letter and duplicate prevention; generated letter is not sent.
- Spoken identity: identity-only generated-audio call, masked captions and teardown; not a new booking trial.
- [Agent assignment](../evaluation/guidelines-and-tool-inventory-20261118.md): exported configuration and publication accepted; live behavior not rerun for that change.
- [Server-wide local checks](../evaluation/server-wide-evaluation-20261116.md): historical 25-tool contract/scope evaluation, not all current positive journeys.
- [Security follow-up](../evaluation/security-followup-20261115.md): fixes and residual risks, not certification.

## Fresh local verification

Windows, Python 3.12.9, editable installation at the source snapshot above. Full pytest: **1,624 passed, 19 skipped, one failed**. Failure is `test_host_key_configuration_requires_matching_owner_only_private_key`: Windows lacks `os.O_NOFOLLOW`. The protection was not weakened. Earlier sandbox collection errors were environmental and retained locally; the reported run was outside that sandbox.

The committed lock failed freshness validation. `uv --system-certs pip install --python .venv/Scripts/python.exe -e '.[dev]'` succeeded using dependency ranges. This is not bit-for-bit reconstruction of a deployed image. Exact local packages and bounded MCP results accompany the wiki verification record. No hosted setup, booking, IBM evaluation, migration or application deployment was executed for this review.

## Follow-up, not closure

Review the existing PR stack for ancestry and overlap before merge or closure; do not equate open status with absent implementation. Resolve the stale lock in a separately tested change, retain the Windows permission limitation, confirm final browser presentation/visual acceptance, update dated submission artifacts, and reconcile residual security and organizer access requirements. No issue or PR was closed by these documentation changes.

Additional fresh checks: 89/89 baseline contract checks, 69/69 argument checks, both fixture reads and the specific unknown-case denial passed. Discovery returned 21 baseline and 29 enabled schemas (inventory only). Focused lint retained one existing E501 at `tests/test_search_availability.py:305`. Browser rendering remains pending because Chrome is signed out of the private repositories.

UI correction: the current root route uses the Autonomous Scheduling Command Center with unified stepper, voice controls, live conversation/MCP feed, call-bound scheduling summary and Wrap Up. Old `final-*.png` replay screenshots do not depict this current UI and are excluded from the wiki’s current-interface explanation.
