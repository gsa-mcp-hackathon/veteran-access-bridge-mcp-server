# Local MCP server

**Requirements:** Python 3.12, Git, `uv`, Windows PowerShell 7 (examples), a clean checkout. The pinned November 18 documentation review used Python 3.12.9.

```powershell
# Backend source (historical evidence pin; private repository access required)
git clone https://github.com/wbgreen0405/veteran-access-bridge.git
cd veteran-access-bridge
git checkout --detach 5b6cd072f23b4d4edce2e19c4f75faa774c87988
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -e '.[dev]'
.\.venv\Scripts\Activate.ps1
python --version
```

!!! warning "Lockfile finding"
    This reviewed candidate did **not** pass `uv sync --locked --group dev --python 3.12` because its `uv.lock` required updating. The editable install shown above passed in the documented environment; it does **not** establish lock reproducibility. Review `Reproducibility.md` in the repository before final judging.

```powershell
# Run server-side checks in local/synthetic fixture configuration
python -m pytest -q
python eval/probe_mcp_contracts.py --output-dir eval/results/reviewer-contracts-new
python eval/probe_mcp_adversarial.py --output-dir eval/results/reviewer-arguments-new

# MCP stdio mode: starts a process waiting for an MCP client
veteran-access-mcp
```

In another terminal (Node.js/npm required), the *source-derived Inspector command* is:

```powershell
npx @modelcontextprotocol/inspector veteran-access-mcp
```

The Inspector GUI command was **not run** during the documentation review; follow the locally printed address/token. Avoid storing sensitive tokens in Git. The default **21-tool** in-process discovery and two fixture reads *were* verified separately.

**Safe test inputs:** `DEMO-CARD-5000335-001` (35/28 synthetic specialty comparator), `DEMO-PC-5000999-001` (14/20 primary comparator), `UNKNOWN-CASE` (must deny). Do not reuse consumed booking cases.

---

**Developer Guide:** [Overview](index.md) · [VHA Lighthouse sandbox →](vha-sandbox.md)
