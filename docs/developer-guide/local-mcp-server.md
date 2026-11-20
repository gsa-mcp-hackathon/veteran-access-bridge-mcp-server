# Run the local MCP server

Install Git, Python 3.12 and uv. From a new terminal, clone the submission repository and install the locked dependencies.

```bash
git clone https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git
cd veteran-access-bridge-mcp-server
git rev-parse HEAD
uv sync --locked --group dev
```

### Discover tools

```bash
uv run --no-sync python scripts/list_local_mcp_tools.py
```

The script starts a server, connects over standard input/output and lists the advertised tools. Expect 21 in the default local configuration.

### Check scheduling and booking controls

```bash
uv run --no-sync pytest -q tests/test_m6_2_primary_care_scenarios.py
uv run --no-sync pytest -q tests
```

These commands use local fixtures and need no cloud credentials. Save the commit printed above with the pass, fail and skip counts. For a guided comparison, open the [recorded Primary Care evidence](../evaluation/reviewer-index.md).

[Developer guide](index.md) · [VHA sandbox setup](vha-sandbox.md)
