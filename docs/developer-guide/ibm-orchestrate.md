# IBM watsonx Orchestrate evaluation reference

For a new installation, follow [Connect Avery to your MCP server](avery-agent.md). This page covers the historical evaluation runners.

**Important:** Hosted evaluation commands require authorized IBM credentials and a known environment. Historical M6.3/M6.4 configurations are not equivalent to the later consolidated 29-tool server and 21-tool Avery attachment configuration.

```powershell
# Isolated IBM ADK environment (do not alter the backend Python environment)
python -m venv .venv-adk
.\.venv-adk\Scripts\Activate.ps1
python -m pip install --upgrade ibm-watsonx-orchestrate
orchestrate --version
orchestrate --help
orchestrate env --help
orchestrate env list

# Select an existing authorized environment
$EnvironmentName = 'YOUR_AUTHORIZED_ENVIRONMENT'
orchestrate env activate $EnvironmentName
orchestrate agents list
orchestrate toolkits list
orchestrate connections list
orchestrate evaluations --help
```

**Project-owned evaluation runners** (record the environment and output directory):

```powershell
pwsh ./deploy/ibm/orchestrate/run-m64-evaluation.ps1 -EnvironmentName $EnvironmentName
pwsh ./deploy/ibm/orchestrate/run-m63-evaluation.ps1 -EnvironmentName $EnvironmentName
pwsh ./deploy/ibm/orchestrate/run-m63-regression.ps1 -EnvironmentName $EnvironmentName
```

M6.4 historical runner uses **13 scenario JSON files**; that number does *not* imply 13/13 passed. M6.3 historical evaluation uses 10 direct cases and 6 focused regression cases. Inspect each newly written `summary_metrics.csv`, raw traces and run identity. The **November 2026** evidence is versioned and must not be merged across configurations.

A general current IBM ADK pattern is `orchestrate evaluations evaluate --help` and the [IBM evaluation guide](https://developer.ibm.com/learningpaths/watsonx-orchestrate-agentops/agent-evaluation-workflows/). Consult that command's output for your installed ADK version **before** supplying flags. Do **not** rerun original `configure-m64.ps1` against the accepted later Avery deployment; it may replace its earlier candidate toolkit. [Project IBM CLI runbook](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-m64-codespace-ibm-cli-relogin-deploy.md).

---

**Developer Guide:** [Overview](index.md) · [← Supabase](supabase.md) · [DeepEval →](deepeval.md)
