# Local MCP quickstart

Use this guide to inspect the synthetic MCP server locally. For judge materials, start at [README](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/README.md). For the hosted voice experience, use the companion frontend's reviewer login.

## Reproduce the local release

Install Git, Python 3.12 and uv. Clone the repository and run these commands from its root.

```bash
git clone --branch main https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git
cd veteran-access-bridge
uv sync --locked --group dev
uv run --no-sync python scripts/list_local_mcp_tools.py
uv run --no-sync pytest -q tests/test_m6_2_primary_care_scenarios.py
```

The inventory starts a local server, connects over stdio, and prints its actual tool names and count. Hosted feature flags and the tools attached to Avery can produce different counts. The five Primary Care fixture checks cover new and established patients, appointment length, and unknown classification. All five should pass without service credentials.

Run `uv run --no-sync pytest -q` for the wider suite. Some integration tests require explicit service configuration. Use the dated acceptance reports for hosted calls and database receipts.

## Standard virtual environment alternative

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
veteran-access-mcp
```

This pip alternative resolves dependency ranges and is the tested installation route for the November 18 candidate. Pin the source with `git checkout --detach 5b6cd072f23b4d4edce2e19c4f75faa774c87988` after cloning. The review used Python 3.12.9 and uv’s equivalent editable installer. The stale lock remains follow-up; do not claim identical dependency reconstruction. No credentials are needed for ordinary fixture tests. Some database/live checks are explicitly gated and skipped without their approved configuration.

## HTTP and voice are separate entry points

The deployed service uses the ASGI application, exposed by `veteran-access-demo`, to serve authenticated `/mcp` over streamable HTTP. Remote MCP requires a non-empty `VAB_MCP_API_KEY`, with authorization and case-scope checks enforced separately. The standalone `veteran-access-mcp` entry point always runs stdio; changing its transport setting alone does not turn it into the deployed HTTP host.

See [current architecture](docs/architecture/current-system.md) and the [operator runbook](docs/operations/avery-m64-codespace-ibm-cli-relogin-deploy.md) before configuring a remote service. Local setup does not provision IBM, LiveKit or database writes. Preserve disabled live/write defaults in `.env.example`; never commit `.env` or use production records.

## Next inspection steps

- [Tool definitions](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/src/veteran_access_bridge/mcp/tools) show names, schemas and handlers.
- [Tests](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/tests) demonstrate fixture behavior and denial paths.
- [Evaluation guide](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/eval/README.md) gives local contract/argument probe commands and evidence limitations.
- [Current results](docs/evaluation/release-closeout-20261115.md) and [security follow-up](docs/evaluation/security-followup-20261115.md) distinguish measured outcomes from remaining work.

## Review results and next steps

The fresh Windows full suite returned 1,624 passed, 19 skipped and one Linux-specific private-key permission failure (`os.O_NOFOLLOW`). No protection was changed. The [reconciliation](docs/submission/documentation-reconciliation-20261118.md) and [wiki reproduction guide](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/developer-guide/clean-room-reproducibility/) retain command status, fixture checks and limitations.
