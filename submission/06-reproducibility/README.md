# 06 · Reproducibility

You can run the MCP server and reproduce the headline evaluation numbers on your own machine in about 10 minutes. **No IBM Cloud, voice or database credentials are needed**: the local path uses bundled synthetic fixtures.

## 1 · Get the code

**Option A: GitHub Codespaces.** On the repository page select **Code → Codespaces → Create codespace on main**, then open a terminal.

**Option B: local machine.** Install Git, Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git
cd veteran-access-bridge-mcp-server
git rev-parse HEAD          # record the commit with your results
uv sync --locked --group dev --python 3.12
```

Using pip instead: `python -m venv .venv`, activate it, then `python -m pip install -r requirements.txt` and `python -m pip install --no-deps -e .`. Drop `uv run --no-sync` from the commands below.

## 2 · Discover the tools

```bash
uv run --no-sync python scripts/list_local_mcp_tools.py
```

**Expect 21 tools.** The client starts the server as a child process and talks MCP over standard input and output. The optional CRM and agent-scheduling groups are off by default; step 5 turns them on to reach 29.

## 3 · Make a real MCP request

```bash
uv run --no-sync python scripts/read_scheduling_encounter.py DEMO-PC-5000999-001
```

This calls `get_scheduling_encounter` for an established Primary Care patient. **Expect** `ESTABLISHED`, and in `slot_eligibility` the slot `VISTA-SLOT-PC-5000999-002` marked ineligible, with reasons naming the appointment-intent, patient-classification and scheduling-template mismatch.

```bash
uv run --no-sync python scripts/read_scheduling_encounter.py UNKNOWN-CASE
```

**Expect** a nonzero exit and `Unknown synthetic case_id`. This shows the server refuses a case it has no record for.

## 4 · Check the answers

```bash
uv run --no-sync python eval/primary-care/run_gold.py
```

**Expect** `16/16 gold answers matched`. Each run makes fresh calls; a mismatch prints the expected and observed values.

## 5 · Reproduce the Nov 21 probes on all 29 tools

```bash
export VAB_ENABLE_CRM=true VAB_ENABLE_AGENT_SCHEDULING=true
uv run --no-sync python eval/probe_mcp_contracts.py   --output-dir out/contracts
uv run --no-sync python eval/probe_mcp_adversarial.py --output-dir out/adversarial
```

**Expect** `{"probes": 126, "passed": 126, "failed": []}` and `{"executed": 86, "passed": 86, "failed": []}`. Per-check results are written to the output directories as JSON. Use a new output directory for each run.

## 6 · Run the full test suite

```bash
uv run --no-sync pytest -q tests
```

**Expect** `1630 passed, 20 skipped`.

All of the expected results above were re-run against the public repository on November 23, 2026.

## Where to look in the code

| File | What it shows |
|---|---|
| [`mcp/tools/get_scheduling_encounter.py`](../../src/veteran_access_bridge/mcp/tools/get_scheduling_encounter.py) | The MCP entry point used in step 3 |
| [`services/slot_matching.py`](../../src/veteran_access_bridge/services/slot_matching.py) | The eligibility rules behind the exclusion reasons |
| [`mcp/session_scope.py`](../../src/veteran_access_bridge/mcp/session_scope.py) | Case binding, turn capabilities and tool allowlists |
| [`tests/test_m6_2_primary_care_scenarios.py`](../../tests/test_m6_2_primary_care_scenarios.py) | Primary Care scenario assertions |
| [`tests/test_mcp_scope_adversarial.py`](../../tests/test_mcp_scope_adversarial.py) | Adversarial scope tests |

## What needs credentials

The full Avery voice path (IBM watsonx Orchestrate, LiveKit, Deepgram, Supabase and IBM Code Engine) requires separately authorized accounts and is not needed to verify the server. Setup guides: [Connected services over HTTP](../../docs/developer-guide/connected-product.md) · [IBM watsonx Orchestrate](../../docs/developer-guide/avery-ibm-start.md) · [Configuration and secrets](../../docs/developer-guide/configuration-and-secrets.md).

## Rules for safe testing

- Use synthetic fixtures only; never place real Veteran data in any environment.
- Do not reuse consumed booking cases such as `DEMO-PC-VOICE-INTAKE-001`.
- Keep credentials in approved secret storage, never in Markdown or GitHub Pages.

**More:** [Local MCP server guide](../../docs/developer-guide/local-mcp-server.md) · [VS Code](../../docs/developer-guide/vs-code.md) · [Codespaces](../../docs/developer-guide/codespaces.md) · [Clean-room reproducibility](../../docs/developer-guide/clean-room-reproducibility.md) · [Troubleshooting](../../docs/developer-guide/troubleshooting.md) · [Release checklist](../../docs/developer-guide/release-checklist.md)
