# 04 · Final evaluation evidence

[Evaluation Command Center](../../docs/evaluation/index.md) · [29-tool inline scorecard](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/evaluation/#panel-tools) · [Evidence Library](../../docs/evaluation/reviewer-index.md)

| Evidence | Observed result | Exact boundary |
|---|---|---|
| Gold answers | 16/16 | Nov 19, synthetic Primary Care, field-level matches |
| Deterministic controls | 135/135 | Nov 19, six overlapping suites |
| MCP contracts | 108/108 | Nov 16, historical 25-tool configuration |
| Hostile arguments | 76/76 | Nov 16, local probes |
| Scope and schema | 261/261 | Nov 16, overlapping local assertions |
| Catalog verifier | 48/48 | PR #215 commit `a5bcf827`, local and GitHub CI |
| Current M6.4 inventory | 29 registered / 21 attached | Configuration only; not a current per-tool pass rate |

**Copied record:** [Nov 16 historical 25-tool CSV](evidence/historical-25-tool-coverage-20261116.csv). **Indexed catalog:** [29-tool evidence JSON](evidence/m64-per-tool-evidence.json). For deployed security limitations, see [Section 05](../05-security/README.md).

## Reading the scorecards

The interactive charts show **inventory distribution and historical test-row coverage**, not synthesized performance grades. The **25/29** bar counts tools that have November 16 local test rows, and its remaining four are *outside that earlier test inventory*. Each tool's contract, hostile-argument and scope-result denominators remain available by selecting its name in the inline table. **M6.4 IBM per-tool pass percentage, latency p95 and Pass³ are not established by this evidence.**

[Judge package status and still-missing final artifacts](../README.md#submission-artifact-status).
