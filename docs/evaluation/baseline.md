# Baseline & Early Evaluation

**Checkpoint:** October–early November 2026 · **Purpose:** establish MCP test fixtures and the initial agent/tool evaluation baseline.

<div class="ev-meta"><span>Runner: local Python / MCP + IBM historical harness</span><span>Model: see pinned IBM run artifacts</span><span>Data: synthetic fixtures</span><span>Outcome: versioned baseline; not a release score</span></div>

## Evaluation design

The initial evaluation foundation used a **10-question gold dataset** (`veteran-access-eval-0` in the October 20 evidence ledger), synthetic encounter fixtures, MCP schema checks, and failure cases. The original IBM M6.3 results came from a different agent/toolkit than the later M6.4 configuration.

## What was measured

| Checkpoint | Recorded observation | Interpretation |
|---|---|---|
| Original October foundation | Ten-question gold dataset committed; MCP evaluation foundation merged | Historical provenance, not a 10/10 pass claim |
| M6.3 saved-agent evaluation | 7/7 historical score; approximately 7.97 s average | Not a current M6.4 result |
| M6.3 direct evaluation | Ten cases executed; focused six-case regression accepted with qualifications | Analyzer and text-match limitations retained |
| M6.4 dataset | Thirteen designed scenarios | Dataset size alone is not a pass result |

## Method and reproducibility

Early evaluations combined deterministic MCP tool contracts and IBM watsonx Orchestrate tests. Historical analyzer failures are retained rather than retroactively converted to passes.

**Evidence:** [Submission evidence ledger](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/submission/evidence-ledger.md) · [Historical evaluation](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/submission/evaluation.md) · [M6.4 evaluation assets](https://github.com/wbgreen0405/veteran-access-bridge/tree/5b6cd072f23b4d4edce2e19c4f75faa774c87988/eval/watsonx)

**Next:** [MCP Server Validation](mcp-validation.md)
