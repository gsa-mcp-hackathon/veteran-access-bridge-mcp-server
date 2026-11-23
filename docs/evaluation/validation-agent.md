# Validation & Agent Evidence

Backend validation, agent runs and the end-to-end trial. Backend authorization correctness is assessed separately from agent behavior.

## MCP server validation

**Nov 15–16 checkpoint.** Deterministic assertions with no model: tool contracts, scoped inputs, explicit denials and backend reliability, run in local fixture mode.

<div class="ev2-flow">
<div><b>1 · Design</b><span>21, 25 and 29 tool configurations; valid and invalid inputs</span></div>
<i>→</i>
<div><b>2 · Execute</b><span>Python tests, MCP contract probes, negative arguments</span></div>
<i>→</i>
<div><b>3 · Analyze</b><span>Scope denial, schema assertions, platform limits</span></div>
</div>

| Run | Result | Boundary |
|---|---:|---|
| Nov 15 backend regression | 1,337 passed; 19 skipped | Earlier release |
| Nov 16 Linux regression | 1,380 passed; 19 skipped | Separate Linux run |
| Nov 16 contract probes | 108/108 | Recorded 25-tool configuration |
| Nov 16 hostile-argument probes | 76/76 | Input checks, not a prompt-injection certification |
| Nov 16 scope and schema | 261/261 | Overlapping assertions; do not sum with probes |
| Nov 18 local Windows review | 1,624 passed; 19 skipped; <span class="ev2-badge warn">1 failed</span> | Linux-only `os.O_NOFOLLOW` is unsupported on Windows |

The sample fixture is read-only, and an unknown case returns a denial instead of invented scheduling facts:

```json
{"name":"get_scheduling_encounter","arguments":{"case_id":"DEMO-PC-5000999-001"}}
```

**Evidence:** [Nov 16 tool-wide report](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/server-wide-evaluation-20261116.md) · [Per-tool coverage](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/server-wide-tool-coverage-20261116.md) · [Contract probe source](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/eval/probe_mcp_contracts.py) · [Argument probe source](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/eval/probe_mcp_adversarial.py)

## IBM watsonx Orchestrate and DeepEval

Assesses agent behavior, MCP tool selection and spoken interaction using historical M6.3 and M6.4 configurations. Model metadata is disclosed only from the exact run artifact.

| Source | Recorded result | Interpretation |
|---|---|---|
| Historical M6.3 saved-agent run | 7/7 | Historical configuration only |
| Nov 15 DeepEval rerun | 0.95 MCP-use reading | **One** conversation: two tasks, three calls |
| Nov 16 controlled voice call | Five IBM-selected tool types observed | Synthetic booking path; backend authority enforced separately |
| Nov 18 spoken identity check | <span class="ev2-badge ok">PASS</span> identity only | No appointment requested; not a booking rerun |

!!! note "Evaluator metadata"
    The reviewer summary does not establish a single reusable DeepEval judge-model ID, temperature, rubric, prompt or threshold for every run. Do not insert a guessed model name. An invalid earlier zero-score adapter run is not evidence that Avery failed every task.

??? example "IBM CLI commands (historical runners)"

    Use an **authorized** IBM environment and inspect the selected toolkit first.

    ```powershell
    orchestrate --version
    orchestrate env list
    $EnvironmentName = 'YOUR_AUTHORIZED_ENVIRONMENT'
    orchestrate env activate $EnvironmentName
    orchestrate agents list
    orchestrate toolkits list
    pwsh ./deploy/ibm/orchestrate/run-m63-evaluation.ps1 -EnvironmentName $EnvironmentName
    pwsh ./deploy/ibm/orchestrate/run-m64-evaluation.ps1 -EnvironmentName $EnvironmentName
    ```

    These scripts target historical agent and toolkit names and do not evaluate the newer consolidated Avery configuration.

**Evidence:** [IBM CLI setup](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-m64-codespace-ibm-cli-relogin-deploy.md) · [Historical release evaluation](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/release-closeout-20261115.md) · [Evaluation assets](https://github.com/wbgreen0405/veteran-access-bridge/tree/5b6cd072f23b4d4edce2e19c4f75faa774c87988/eval)

## End-to-end voice trial

<span class="ev2-badge ok">BOOKED_SIMULATED</span> **Nov 16, 2026**, at a pinned revision. Generated caller audio exercised IBM-selected patient retrieval, knowledge search, appointment search, option selection and booking request tools. Trusted services independently checked scope and current confirmation. Database reads confirmed **one appointment and one host-written CRM note**, with no production VA writes. This is not a new Nov 19 booking trial.

**Added by later reviews**

- Nov 18: spoken identity and caption-masking acceptance (identity only; no booking).
- Nov 19: **16/16** gold answers and **135/135** deterministic control checks.
- Nov 19: voice and database reconciliation found gaps in before/after snapshots for earlier attack sessions.

## Latest M6.4 configuration and focused regression tests

In the reviewed November 18 enabled configuration, **29 tools** were registered, **21** attached to Avery and **8** left server-only. These are inventory observations, not deployment-wide behavioral acceptance. The historical November 16 **108/108** contract probes belong to an earlier **25-tool** configuration.

The catalog-integrity fix at [PR #215](https://github.com/wbgreen0405/veteran-access-bridge/pull/215) passed **48/48 focused checks** locally and in CI at commit `a5bcf827`. This validates the local verifier, **not** IBM pre-dispatch enforcement. [Per-tool scorecard](per-tool.md) · [Security outcomes](security-adversarial.md).

## What remains open

!!! danger "Open evidence areas"
    | Area | Required evidence |
    |---|---|
    | Later revision acceptance | A separately authorized run on fresh synthetic cases if the release changes |
    | Security | Expanded attack coverage, paired DB checks, distinct-session isolation, dependency triage |
    | Reliability | Hosted multi-writer concurrency and uncertain-write recovery checks |
    | Delivery | Final recorded browser presentation; visual check of receipt and letter flow |
    | Reproduction | Pinned final release and locked dependency freshness |

**Evidence:** [Accepted booking proof](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/agent-led-voice-20261116.json) · [Accepted call report](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-agent-led-scheduling-20261116.md) · [Nov 19 reviewer record](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/README.md)

**Next:** [Security & adversarial](security-adversarial.md)
