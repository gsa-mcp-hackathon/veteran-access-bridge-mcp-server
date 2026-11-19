# Evaluation & Results

Separate checks, each with its **original date and denominator**. These results are **not combined into one pass rate**, and all data is synthetic.

<div class="ev2-cards">
<a class="ev2-card" href="method-gold/"><strong>16 / 16</strong><span>Gold answers matched</span><small>Nov 19 · Primary Care fixture</small></a>
<a class="ev2-card" href="method-gold/#phoenix-grouped-control-checks"><strong>135 / 135</strong><span>Local control checks passed</span><small>Nov 19 · six suites</small></a>
<a class="ev2-card" href="validation-agent/#mcp-server-validation"><strong>1,380</strong><span>Backend tests passed</span><small>Nov 16 · Linux run, 19 skipped</small></a>
<a class="ev2-card ev2-gap" href="validation-agent/#what-remains-open"><strong>5</strong><span>Open evidence areas</span><small>Security, reliability, delivery</small></a>
</div>

## How we evaluate

<div class="ev2-flow">
<div><b>1 · Design</b><span>Gold questions, synthetic fixtures, tool contracts, refusal cases</span></div>
<i>→</i>
<div><b>2 · Execute</b><span>FastMCP fixtures, IBM watsonx Orchestrate, DeepEval, voice trials</span></div>
<i>→</i>
<div><b>3 · Compare</b><span>Expected vs. observed, with failures and evidence limits kept</span></div>
</div>

## Results at a glance

| Area | Date | Scope | Result | Details |
|---|---|---|---|---|
| Gold questions | Nov 19 | Local Primary Care fixture | <span class="ev2-badge ok">16/16 matched</span> | [Method & gold](method-gold.md) |
| Control checks | Nov 19 | Six deterministic local suites | <span class="ev2-badge ok">135/135 passed</span> | [Method & gold](method-gold.md#phoenix-grouped-control-checks) |
| MCP contracts and regression | Nov 15–16 | Tool schemas, scope, backend tests | <span class="ev2-badge ok">passed</span> <span class="ev2-badge warn">1 Windows-only failure (Nov 18)</span> | [Validation](validation-agent.md#mcp-server-validation) |
| IBM and DeepEval | Oct–Nov | Bounded agent and voice runs | <span class="ev2-badge ok">recorded</span> <span class="ev2-badge warn">metadata gaps</span> | [Agent evidence](validation-agent.md#ibm-watsonx-orchestrate-and-deepeval) |
| End-to-end booking | Nov 16 | One synthetic voice trial at a pinned revision | <span class="ev2-badge ok">BOOKED_SIMULATED</span> | [End-to-end](validation-agent.md#end-to-end-voice-trial) |
| Security and adversarial | Nov 15–19 | Probes, voice sample, reconciliation | <span class="ev2-badge warn">bounded; gaps open</span> | [Security](security-adversarial.md) |

## Timeline

<div class="ev2-timeline">
<div><small>OCT 2026</small><b>Baseline</b><span>10-question gold set, M6.3 runs</span></div>
<div><small>NOV 15–16</small><b>Server validation</b><span>Contracts, probes, regression</span></div>
<div><small>NOV 16</small><b>Voice trial</b><span>Synthetic booking receipt</span></div>
<div><small>NOV 19</small><b>Judge review</b><span>16 gold answers, 135 checks</span></div>
</div>

??? note "Reproduce a read-only check"

    Use the [Developer Guide](../developer-guide.md) for the local server, MCP Inspector, IBM CLI, DeepEval and optional Phoenix setup.

    ```json
    {"name":"get_scheduling_encounter","arguments":{"case_id":"DEMO-PC-5000999-001"}}
    ```

    This fixture returns structured scheduling evidence and does **not** book an appointment. The `BOOKED_SIMULATED` receipt belongs to the separate, dated voice trial.

!!! info "Scope"
    A registered tool is not proof that every operation was exercised. No unverified Phoenix score is shown. Links to evidence repositories may require reviewer access.

**Next:** [Method & gold questions](method-gold.md) · [Demonstration](../demonstration.md)
