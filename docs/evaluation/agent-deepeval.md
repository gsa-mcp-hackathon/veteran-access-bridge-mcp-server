# IBM watsonx Orchestrate & DeepEval

**Goal:** assess SI agent behavior, MCP tool selection and spoken interaction separately from backend authorization correctness.

<div class="ev-meta"><span>Execution: IBM CLI / watsonx Orchestrate</span><span>Agent: Avery / historical M6.3 and M6.4 configurations</span><span>Model metadata: disclose from exact run artifact only</span><span>Scope: bounded recordings and agent evaluations</span></div>

## 01 · What was evaluated

| Source | Recorded result | Interpretation |
|---|---|---|
| Historical M6.3 saved-agent run | 7/7 | Historical configuration only |
| November 15 DeepEval rerun | 0.95 MCP-use reading | **One** conversation; two tasks, three calls |
| November 16 controlled voice call | Five IBM-selected tool types observed | Successful synthetic booking path; backend authority separately enforced |
| November 18 spoken identity check | PASS identity-only | No appointment requested; not a booking rerun |

**Evaluator model metadata:** The checked reviewer summary does not establish a single reusable DeepEval judge-model ID, temperature, rubric, prompt or scoring threshold for every run. We will display those only when confirmed against the corresponding raw execution artifact; do not insert a guessed model name.

## 02 · CLI commands (historical runners)

Use an **authorized** IBM environment and inspect the selected toolkit before executing.

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

Historical scripts target historical agent/toolkit names and do not automatically evaluate the newer consolidated Avery configuration. Keep raw run metadata and results side-by-side.

## 03 · Files and limitations

- [IBM CLI setup and verification](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-m64-codespace-ibm-cli-relogin-deploy.md)
- [Historical release evaluation](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/release-closeout-20261115.md)
- [November 16 booking acceptance](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-agent-led-scheduling-20261116.md)
- [Versioned evaluation asset directory](https://github.com/wbgreen0405/veteran-access-bridge/tree/5b6cd072f23b4d4edce2e19c4f75faa774c87988/eval)

**Note:** DeepEval scores model/tool behavior; they do not waive security gates. An invalid earlier zero-score adapter run is not evidence that Avery failed every task.

**Next:** [Security & Adversarial Evaluation](security-adversarial.md)
