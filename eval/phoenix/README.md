> Historical experiment. Current measured MCP and agent evaluation is indexed in [the evaluation guide](../README.md). Retain these files as provenance; no current Phoenix score is claimed.

# Veteran Access MCP — Optional Phoenix evaluation

This module follows the GSA-TTS `mcp-eval` skill pattern. Its dependencies are intentionally isolated in `eval/phoenix/pyproject.toml` so Phoenix's FastMCP transitive dependencies cannot change the product MCP runtime.

For the current submission, **watsonx Orchestrate Evaluate is the primary agent/runtime acceptance gate** because it evaluates the deployed `veteran_access_agent` in its actual runtime. Phoenix is retained as an optional independent MCP/trace experiment and is not required to complete Issue #19 or submission readiness.

## What it evaluates

The original `veteran-access-eval-0` dataset contains 10 stable, read-only
questions for the earlier Cardiology search slice.

The current `veteran-access-eval-1` dataset contains 12 stable M6.3 questions
covering Cardiology and Primary Care through the unified Scheduling Encounter,
deterministic slot exclusions, Veteran preference ranking, access-standard
comparators, Community Care guardrails, and unknown-case fail-closed behavior.

The agent launches Veteran Access MCP over stdio and uses the current four-tool
contract. For real-time scheduling encounter questions, `get_scheduling_encounter`
is the canonical first tool.

Deterministic safety/business rules remain covered by pytest. Phoenix measures
agent/tool usability and response quality.

## Optional configuration

Only configure this section if you choose to run the secondary Phoenix experiment.

From the repository root, create a local `.env` containing:

```text
USAI_API_KEY=...
USAI_BASE_URL=...
AGENT_MODEL=...
JUDGE_MODEL=...
```

Do not commit the file.

## Install evaluation dependencies

```powershell
uv sync --project eval/phoenix
```

## Start Phoenix

```powershell
uv run --project eval/phoenix arize-phoenix serve
```

Phoenix UI: http://localhost:6006

## Validate the dataset without uploading

```powershell
uv run --project eval/phoenix python eval/phoenix/create_dataset.py --dataset-name veteran-access-eval-1 --dry-run
```

Expected for the current dataset: 12 rows.

## Upload the dataset

```powershell
uv run --project eval/phoenix python eval/phoenix/create_dataset.py --dataset-name veteran-access-eval-1
```

## Run an experiment

```powershell
uv run --project eval/phoenix python eval/phoenix/run_experiment.py --dataset-name veteran-access-eval-1
```

Compare the prior v2 prompt with the current M6.3 v3 prompt:

```powershell
uv run --project eval/phoenix python eval/phoenix/run_experiment.py --dataset-name veteran-access-eval-1 --system-prompt-version v2
uv run --project eval/phoenix python eval/phoenix/run_experiment.py --dataset-name veteran-access-eval-1 --system-prompt-version v3
```

## Interpretation

The current experiment uses three evaluators:

- correctness against the stable gold answer;
- scope/adherence;
- M6.3 governance compliance.

A failure should be assigned to the smallest appropriate layer:

- deterministic rule failure → domain/service/test issue
- wrong tool selection → tool name/schema/docstring or agent prompt
- unsupported claim → prompt/tool output boundary
- formatting-only mismatch → judge tolerance or reference normalization

Do not use an LLM judge to override deterministic scheduling gates.
