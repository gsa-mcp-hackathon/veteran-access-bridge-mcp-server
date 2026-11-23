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

**Evidence:** [Nov 16 tool-wide report](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/docs/evaluation/server-wide-evaluation-20261116.md) · [Per-tool coverage](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/docs/evaluation/server-wide-tool-coverage-20261116.md) · [Contract probe source](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/eval/probe_mcp_contracts.py) · [Argument probe source](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/eval/probe_mcp_adversarial.py)

## IBM watsonx Orchestrate and DeepEval

Assesses agent behavior, MCP tool selection and spoken interaction using historical M6.3 and M6.4 configurations. Model metadata is disclosed only from the exact run artifact.

| Source | Recorded result | Interpretation |
|---|---|---|
| Historical M6.3 saved-agent run | 7/7 | Historical configuration only |
| Nov 15 DeepEval rerun | 0.95 MCP-use reading | **One** conversation: two tasks, three calls |
| Nov 16 controlled voice call | Five IBM-selected tool types observed | Synthetic booking path; backend authority enforced separately |
| Nov 18 spoken identity check | <span class="ev2-badge ok">PASS</span> identity only | No appointment requested; not a booking rerun |

!!! note "Evaluator metadata"
    The Nov 15 DeepEval run (0.95) used DeepEval 4.3.4, `MultiTurnMCPUseMetric`, threshold 0.80 and judge model OpenAI `gpt-4.1-mini`, as recorded in its evidence file. IBM watsonx Orchestrate Evaluate used OpenAI `gpt-oss-120b` as its evaluation model, as recorded in the saved IBM run configuration. Avery runs on Anthropic Claude Sonnet 4.6, so no model graded itself. Agent temperature was not recorded. An invalid earlier zero-score adapter run is not evidence that Avery failed every task.

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

**Evidence:** [IBM CLI setup](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/docs/operations/avery-m64-codespace-ibm-cli-relogin-deploy.md) · [Historical release evaluation](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/docs/evaluation/release-closeout-20261115.md) · [Evaluation assets](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/eval)

## End-to-end voice trial

<span class="ev2-badge ok">BOOKED_SIMULATED</span> **Nov 16, 2026**, at a pinned revision. Generated caller audio exercised IBM-selected patient retrieval, knowledge search, appointment search, option selection and booking request tools. Trusted services independently checked scope and current confirmation. Database reads confirmed **one appointment and one host-written CRM note**, with no production VA writes. This is not a new Nov 19 booking trial.

**Added by later reviews**

- Nov 18: spoken identity and caption-masking acceptance (identity only; no booking).
- Nov 19: **16/16** gold answers and **135/135** deterministic control checks.
- Nov 19: voice and database reconciliation found gaps in before/after snapshots for earlier attack sessions.

## Latest M6.4 configuration and focused regression tests

In the reviewed November 18 enabled configuration, **29 tools** were registered, **21** attached to Avery and **8** left server-only. These are inventory observations, not deployment-wide behavioral acceptance. The historical November 16 **108/108** contract probes belong to an earlier **25-tool** configuration.

The catalog-integrity fix at [PR #215](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/pr-215.md) passed **48/48 focused checks** locally and in CI at commit `a5bcf827`. This validates the local verifier, **not** IBM pre-dispatch enforcement. [Per-tool scorecard](per-tool.md) · [Security outcomes](security-adversarial.md).

## November 21–22 review and disposition

This section separates **completed evaluation activity** from **still-open deployed acceptance**. The reviewed November 22 remediation report recorded **27 passed, zero failed and zero skipped** for a targeted local suite. Subsequent focused local and GitHub Actions catalog-verifier regression evidence recorded **48/48 passing checks** at PR #215. These are different checkpoints, not 75 independent security scenarios or a full deployed assessment.

| Area | Completed evidence | Still required for deployed PASS |
|---|---|---|
| S14 · tool-description integrity | Corrected independent reference and local verifier checks; focused CI regression | Human-approved release manifest plus correlated IBM pre-dispatch denial |
| S13/A23 · injected CRM tool result | Two paired synthetic notes delivered to the local MCP client | Authorized write-isolated IBM paired replay, trace, answer and side-effect verification |
| S15 · MCP destination | Local endpoint binding drift rejected | IBM-managed paired outbound destination and credential-forwarding decisions |
| S03/A21 · caller isolation | Read-only fixture qualification and local session-scope checks | Two distinct approved synthetic callers, verified overlapping sessions, cross-case denial and correlated database snapshots |
| Primary Care acceptance | Nov 22 synthetic fixture preparation and fail-closed scope review | Fresh approved fixture and independently verified IBM/MCP acceptance; not a new completed booking |

**Completed measurements, November 19–22 (U.S. Central time).** The engineering records label some November 21 evening runs with their UTC date (November 22).

| Date | Result | Scope |
|---|---|---|
| Nov 19 | 1,630 passed, 20 skipped | GitHub Actions CI on released code `ea0880f` |
| Nov 21 | 126/126 contract checks | All 29 registered tools, local in-process ([script](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/eval/probe_mcp_contracts.py)) |
| Nov 21 | 86/86 hostile-argument checks | All 29 tools: 19 read-only tools × 4 hostile inputs, plus 10 write tools × forged authority ([script](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/eval/probe_mcp_adversarial.py)) |
| Nov 21 | 21 of 29 tools attached to Avery | Configuration from the IBM agent export; not an agent run |
| Nov 22 | 27 passed, 0 failed, 0 skipped | Targeted local security remediation |
| Nov 22 | 48/48 catalog-verifier checks | Local and GitHub CI ([PR #215 record](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/pr-215.md)) |

These are separate checkpoints and are not combined into one rate.

**Sources:** [Sanitized closeout](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/05-security/evidence/m64-security-closeout-summary.md) · [PR #215 focused CI](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/ci/ci-run-45101968969.md).

## What remains open

!!! danger "Open evidence areas"
    | Area | Required evidence |
    |---|---|
    | Later revision acceptance | A separately authorized run on fresh synthetic cases if the release changes |
    | Security | Expanded attack coverage, paired DB checks, distinct-session isolation, dependency triage |
    | Reliability | Hosted multi-writer concurrency and uncertain-write recovery checks |
    | Delivery | Final recorded browser presentation; visual check of receipt and letter flow |
    | Reproduction | Pinned final release and locked dependency freshness |

**Evidence:** [Accepted booking proof](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/docs/evaluation/agent-led-voice-20261116.json) · [Accepted call report](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/docs/operations/avery-agent-led-scheduling-20261116.md) · [Nov 19 reviewer record](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/docs/evaluation/judge-review/README.md)

**Next:** [Security & adversarial](security-adversarial.md)
