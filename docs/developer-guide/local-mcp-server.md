# Run your first MCP request

Start with one question an appointment scheduler has to answer: **which openings can this established Primary Care patient use?** You will start the submitted server, send a request through MCP and see why it excludes a new-patient slot. This path uses bundled records and requires no service accounts.

## Open the project

**GitHub Codespaces.** On the [submission repository](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server), select **Code → Codespaces → Create codespace on main**. Wait for setup, then open **Terminal → New Terminal**. You are already in the repository.

**VS Code or your terminal.** Install Git, Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/). Run the following, then open the resulting folder in your editor.

```bash
git clone https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git
cd veteran-access-bridge-mcp-server
```

## Install and discover

```bash
git rev-parse HEAD
uv sync --locked --group dev --python 3.12
uv run --no-sync python scripts/list_local_mcp_tools.py
```

Save the commit ID with your results. The default configuration advertises **21 tools**. The client starts the server as a child process and exchanges MCP messages over standard input and output.

**Using pip instead?** In Python 3.12, run `python -m venv .venv`. Activate it with `source .venv/bin/activate` in Bash or `.\.venv\Scripts\Activate.ps1` in Windows PowerShell. Run `python -m pip install -r requirements.txt` followed by `python -m pip install --no-deps -e .`. For the remaining commands, omit `uv run --no-sync`. The requirements file is exported from `uv.lock`.

## Ask for a scheduling encounter

```bash
uv run --no-sync python scripts/read_scheduling_encounter.py DEMO-PC-5000999-001
```

The client calls `get_scheduling_encounter` with the case ID. Look for `ESTABLISHED`, then find `VISTA-SLOT-PC-5000999-002` in `slot_eligibility`. Its eligibility is false. The reasons identify a mismatch in appointment intent, patient classification and scheduling template. The final fields should say `read_only: true` and `booking_created: false`.

```bash
uv run --no-sync python scripts/read_scheduling_encounter.py UNKNOWN-CASE
```

Expect a nonzero exit and **Unknown synthetic case_id**. This tests what happens when the server has no record for the supplied case.

## Follow the answer through the code

| Open in the submission | What to look for |
|---|---|
| [Tool definition](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/tools/get_scheduling_encounter.py) | The MCP entry point for the case ID |
| [Case](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/mcp/fixtures/primary-care-established-case.json) and [slot data](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/adapters/fixtures/vista-slots-primary-care.json) | The request and the available inventory |
| [Slot matching](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/services/slot_matching.py) | Eligibility rules that produce the exclusion reasons |
| [Primary Care scenarios](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/tests/test_m6_2_primary_care_scenarios.py) | Assertions you can inspect and run |

## Compare with the answer key

```bash
uv run --no-sync python eval/primary-care/run_gold.py
uv run --no-sync pytest -q tests/test_m6_2_primary_care_scenarios.py
```

The first command makes fresh calls and grades **16 questions**. A mismatch prints the expected and observed values. To check the broader suite, run `uv run --no-sync pytest -q tests`. Compare your run with the [recorded evidence](../evaluation/reviewer-index.md).

Continue to [Run over HTTP and connect services](connected-product.md).
