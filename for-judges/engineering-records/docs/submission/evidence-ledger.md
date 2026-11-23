> **Checkpoint scope:** This document retains dated evidence/instructions. Read the [November 18 reconciliation](documentation-reconciliation-20261118.md) before interpreting “current”, tool counts, deployment state or remaining work. End-to-end synthetic scheduling passed on November 16; later identity/configuration checks have separate scopes. Original results below are preserved.

# Veteran Access Bridge — Evidence Ledger

Record only evidence that actually exists. Add screenshots, trace IDs, run URLs, or exact results as they are produced.

| Date | Milestone | Evidence | Status / Result |
|---|---|---|---|
| 2026-10-20 | MCP foundation | PR #17 | Merged via squash |
| 2026-10-20 | MCP foundation CI | GitHub Actions | Passed before merge |
| 2026-10-20 | MCP security review | Codex review on PR #17 | FastMCP version, transport, and unauthenticated remote-listener issues corrected |
| 2026-10-20 | Remote transport boundary | `validate_transport` + regression tests | Current MVP stdio-only at that milestone; non-stdio failed closed |
| 2026-10-20 | Evaluation foundation | PR #18 | Merged via squash |
| 2026-10-20 | Evaluation CI | GitHub Actions run #34 | Passed |
| 2026-10-20 | Gold dataset | `veteran-access-eval-0` | 10 questions committed |
| 2026-10-20 | Evaluation review | Codex review on PR #18 | Evaluator payload, event-loop, stable clock, and OTLP trace issues addressed |
| 2026-10-21 | MCP Inspector | `docs/evidence/issue-20/01-mcp-inspector-tools-discovered.png` | Tools discovered; local MCP connection validated |
| 2026-10-21 | MCP Inspector — workflow state | `docs/evidence/issue-20/02-determine-workflow-state-success.png` | `determine_workflow_state` → `READY_TO_SEARCH` for `DEMO-CARD-5000335-001` |
| 2026-10-21 | MCP Inspector — availability | `docs/evidence/issue-20/03-search-availability-success.png` | `search_availability` returned synthetic sources with provenance |
| 2026-10-21 | watsonx Orchestrate — toolkit import | `docs/evidence/issue-20/06-veteran-access-agent-end-to-end-test.png` | Veteran Access MCP toolkit registered and discovered by Orchestrate |
| 2026-10-21 | watsonx Orchestrate — evaluation baseline | `docs/evidence/issue-20/07-orchestrate-evaluation-results.png`, `evaluation.csv` | 7/7 tests passed; Guardrail Compliance, routing, and tool-call metrics at 1.00 |
| 2026-10-24 | M6.3 evaluation strategy | watsonx Orchestrate Evaluate + pytest/CI | watsonx Evaluate selected as primary agent/runtime acceptance gate; Phoenix retained as optional independent harness |
| 2026-10-24 | M6.3 direct CLI suite | PR #60, direct JSON tests | 10-case direct evaluation path added; generator/recorder bypassed |
| 2026-10-24 | M6.3 full evaluation execution | `eval/watsonx/results/2026-10-24_08-21-40` (local evidence) | 10/10 cases executed; persisted `summary_metrics.csv`; analyzer later failed on IBM `text_match` enum incompatibility |
| 2026-10-24 | Routing fix — #02/#08 | PR #61 | Deterministic case-bearing prompts, stronger routing rules, six-case regression suite; CI passed |
| 2026-10-24 | Routing fix — #08/#09 | PR #62 | Access-only precedence + deterministic #09 prompt; CI passed |
| 2026-10-24 | Access sequence hardening | PR #63 | Exact two-step access sequence attempted; CI passed |
| 2026-10-24 | Access contract simplification | PR #64, merge `18e5383` | `assess_access_standard` made the single authoritative tool for access-standard-only questions; CI passed |
| 2026-10-24 | M6.3 focused regression closeout | #01/#02/#05/#08/#09/#10 regression runs | Required access call matched with correct parameters and no missed required call; #05/#10 retained known IBM text-match false negatives; #08 extra calls recorded as efficiency debt |
| 2026-10-24 | M6.3 evaluation checkpoint | Issue #19 | Accepted and closed; deterministic pytest/CI remains authoritative for business/safety rules |
| 2026-10-24 | Phoenix M6.3 harness | `eval/phoenix/datasets/veteran-access-eval-1/`, prompt v3, correctness/scope/governance judges | Optional harness prepared; no measured Phoenix result claimed |
| NEXT | UI with agent interaction | Veteran Assistant + Scheduler Workspace | Next implementation phase |
| NEXT | Community Care semantics | Issue #23 | Authoritative HSRM/referral/authorization research before CC lifecycle implementation |

## Current accepted M6.3 behavior

- shared Scheduling Encounter for current scheduling/status/preference questions;
- deterministic slot eligibility before preferences;
- preference-ranked option and access comparator may differ;
- access-standard-only questions use `assess_access_standard(case_id)`;
- threshold breach is a review signal only;
- Community Care authorization remains independent;
- EPS is not invoked from threshold evidence alone;
- booking requires booking evidence;
- unknown cases fail closed;
- synthetic/demo boundary remains explicit.

## Known non-blocking evaluation limitations

- IBM standard analysis can reject numeric `text_match` values even after successful evaluation execution.
- IBM text-goal matching can return false negatives despite correct tool routing, parameters, semantic match, and safe behavior.
- #08 showed extra non-required tool calls in the final focused run; track tool-call precision as routing-efficiency debt.

## Evidence capture checklist

For each major issue or PR capture, when applicable:

- PR number and merge SHA
- CI run and outcome
- review findings and resolutions
- deterministic test result
- MCP/agent tool trace
- measured latency and tool-call count
- watsonx evaluation result directory/export
- demo screenshot/video timestamp
- limitation or unresolved risk
