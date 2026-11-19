# Evaluation & Results

Our evaluation combines **deterministic MCP checks, gold questions, backend regression, adversarial scenarios and separately scoped agent/voice evidence**. Results retain their original dates and denominators; they are **not** a single overall pass rate.

<div class="ev-wrap" id="vab-eval-new">
 <div class="ev-kicker">ENGINEERING ASSURANCE / EVIDENCE LEDGER</div>
 <div class="ev-heading"><div><h2>How we evaluated the MCP server</h2><p>Design a controlled scenario, inspect what the system actually did, then compare the outcome against a recorded expectation.</p></div><div class="ev-tag">Versioned findings · November 2026</div></div>
 <div class="ev-process" aria-label="Three stages of evaluation methodology">
  <div class="ev-stage"><span class="ev-num">01</span><div class="ev-ico">▤</div><h3>Evaluation Design</h3><p>Gold questions, synthetic fixtures, tool contracts and refusal cases.</p><div class="ev-chips"><span>Questions</span><span>Reference answers</span><span>Expected controls</span></div></div>
  <div class="ev-arrow">→</div>
  <div class="ev-stage"><span class="ev-num">02</span><div class="ev-ico">⌁</div><h3>Execution &amp; Traces</h3><p>Run MCP fixtures, capture tool results, and preserve agent or voice traces when available.</p><div class="ev-chips"><span>FastMCP</span><span>IBM</span><span>DeepEval</span></div></div>
  <div class="ev-arrow">→</div>
  <div class="ev-stage"><span class="ev-num">03</span><div class="ev-ico">◉</div><h3>Results &amp; Analysis</h3><p>Compare expected and observed behavior; document failures and evidence limits.</p><div class="ev-chips"><span>Pass / fail</span><span>Scope</span><span>Artifacts</span></div></div>
 </div>
 <div class="ev-process-note"><span class="ev-node"></span> Input and expected result <span class="ev-line"></span> <span class="ev-node blue"></span> Tool / backend execution <span class="ev-line"></span> <span class="ev-node gold"></span> Outcome &amp; evidence</div>
 <div class="ev-report-top"><div><div class="ev-kicker gold">INTERACTIVE REPORT</div><h2>Verification Record</h2><p>Flip through six bounded evidence views. Each page cites its original checkpoint; results are not combined into a single score.</p></div><div class="ev-cover-mark">VAB<span> / </span>MCP</div></div>
 <div class="ev-book" role="region" aria-label="Interactive evaluation report">
  <nav class="ev-chapters" aria-label="Report chapters"><button type="button" data-ev-page="0" class="active">01 Summary</button><button type="button" data-ev-page="1">02 Contracts</button><button type="button" data-ev-page="2">03 Gold questions</button><button type="button" data-ev-page="3">04 Regression</button><button type="button" data-ev-page="4">05 Agent &amp; voice</button><button type="button" data-ev-page="5">06 Open findings</button></nav>
  <div class="ev-paper"><div class="ev-paper-head"><span>VETERAN ACCESS BRIDGE <b>· EVALUATION REPORT</b></span><span class="ev-index">01 / 06</span></div><div class="ev-paper-body" id="ev-paper-body" aria-live="polite"></div><div class="ev-paper-footer"><button class="ev-prev" type="button">← Previous</button><div class="ev-progress" aria-label="Report progress"></div><button class="ev-next" type="button">Next →</button></div></div>
 </div>
 <div class="ev-footnote"><b>Scope:</b> Synthetic data only. A tool being registered is not proof that every operation was exercised. Links to private evidence repositories may require reviewer access.</div>
</div>


<div class="ev-timeline" aria-label="Evaluation progress from baseline through November review">
  <a href="baseline/" class="ev-time"><small>OCT 2026</small><b>Baseline</b><span>Original MCP fixtures and evaluations</span></a>
  <a href="mcp-validation/" class="ev-time"><small>NOV 15–16</small><b>Server validation</b><span>Contracts, scope and regressions</span></a>
  <a href="gold-phoenix/" class="ev-time"><small>NOV 19</small><b>Phoenix review</b><span>16 gold answers / 135 control checks</span></a>
  <a href="final-review/" class="ev-time"><small>RECORDED</small><b>End-to-end + gaps</b><span>Verified booking, open gates</span></a>
</div>

<div class="ev-reading-guide"><strong>Six evaluation chapters:</strong> <a href="baseline/">Baseline</a> · <a href="mcp-validation/">MCP Validation</a> · <a href="gold-phoenix/">Phoenix &amp; Gold</a> · <a href="agent-deepeval/">IBM &amp; DeepEval</a> · <a href="security-adversarial/">Adversarial</a> · <a href="final-review/">End-to-End Review</a></div>

## Evaluation methodology in practice

The November 19 reviewer dataset records **16/16 matched answers** in the local Primary Care fixture. Question #6 tested whether an ineligible slot was rejected for the correct reasons. It is a direct tool evaluation, not an agent-led call. [Review the gold dataset](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/primary-care-gold-questions.csv) · [View scored answers](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/primary-care-mcp-gold.csv).

The report's six sections link to versioned evidence, including unfavorable results and known gaps. Phoenix can display instrumented traces, while IBM evaluation and DeepEval assess agent behavior when evidence exists. **No unverified Phoenix score is presented.**

## Reproduce the evidence

Use the [Developer Guide](../developer-guide.md) for the local server, MCP Inspector, IBM CLI, DeepEval and optional Phoenix setup. For a safe read-only check:

```json
{"name":"get_scheduling_encounter","arguments":{"case_id":"DEMO-PC-5000999-001"}}
```

This fixture produces structured scheduling evidence; it does **not** book an appointment. The accepted `BOOKED_SIMULATED` receipt belongs to a distinct, dated end-to-end voice trial.

**Detailed security evidence:** [Security controls and findings](../security-governance.md) · [Adversarial evaluation](security-adversarial.md).

**Next:** [Demonstration](../demonstration.md) · [Developer Guide](../developer-guide.md)
