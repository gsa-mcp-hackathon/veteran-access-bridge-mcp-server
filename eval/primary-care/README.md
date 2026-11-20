# Reproduce the Primary Care gold evaluation

From the repository root, run:

```bash
uv sync --locked --group dev
uv run --no-sync python eval/primary-care/run_gold.py
```

Pick a row in [the original question set](questions.csv) and predict its answer. The runner starts a local MCP server, calls the named tool for each row, and compares the returned fields or denial with the saved expectation. For Q6 it compares the eligibility flag and all three reasons the slot was excluded. A mismatch prints both values and produces a failing exit status.

The sixteen questions exercise four MCP tools using synthetic fixtures. This run requires no cloud account. Voice recognition, IBM tool selection and hosted database writes have separate evaluations.

[Recorded results for comparison](../../docs/evaluation/evidence/primary-care-mcp-gold.csv)
