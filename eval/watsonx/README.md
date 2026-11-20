> **Checkpoint scope:** This document retains dated evidence/instructions. Read the [November 18 reconciliation](../../docs/submission/documentation-reconciliation-20261118.md) before interpreting “current”, tool counts, deployment state or remaining work. End-to-end synthetic scheduling passed on November 16; later identity/configuration checks have separate scopes. Original results below are preserved.

# watsonx Orchestrate M6.3 CLI Evaluation

The Issue #19 checkpoint is complete. The repository keeps the direct JSON evaluation assets and focused regression suite for repeatable verification.

## Why direct JSON tests

IBM's evaluation runner accepts existing JSON datasets through `--test-paths`. Veteran Access Bridge versions its scenarios directly instead of depending on the UI recorder or `orchestrate evaluations generate`.

Directories:

- full ten-case suite: `eval\watsonx\direct_tests`
- focused regression suite: `eval\watsonx\regression_tests`
- local generated results: `eval\watsonx\results`

## Full evaluation

From the repository root with the project virtual environment activated:

```powershell
.\deploy\ibm\orchestrate\run-m63-evaluation.ps1
```

The full runner executes the ten direct JSON scenarios and persists the evaluation output.

## Focused regression

Use the six-case regression after agent-routing changes:

```powershell
.\deploy\ibm\orchestrate\run-m63-regression.ps1
```

Focused cases:

- 01 Cardiology unified encounter
- 02 Cardiology preference vs comparator
- 05 Cardiology no-booking guardrail
- 08 Primary Care access standard
- 09 Primary Care no-inference
- 10 unknown case / no fabrication

## Updating the agent only

When only `agents/veteran-access-agent.yaml` changes, use:

```powershell
.\deploy\ibm\orchestrate\update-m63-agent.ps1
```

This imports the updated agent draft without rebuilding the MCP toolkit.

## Current access-only contract

For an access-standard-only question, the required authoritative tool is:

```text
assess_access_standard(case_id)
```

It returns the deterministic access-standard evidence, including the canonical Patient Indicated Date, comparator wait, policy threshold, and whether the wait standard is exceeded.

A separate `determine_workflow_state` call is not required for this intent. That tool remains available for explicit workflow-state questions.

## Acceptance metrics

Review at minimum:

- agent routing accuracy
- required/expected tool calls
- correct tool calls
- missed tool calls
- tool-call recall
- tool-call precision
- tool-match success
- tool-parameter F1
- semantic match
- average response time

Do not use `is_success` or `text_match` alone as the acceptance decision.

## Known IBM evaluator behavior

During M6.3:

1. Standard analysis could fail after successful evaluation because persisted numeric `text_match` values did not match the analyzer's expected string enum.
2. Some safe/correct cases produced `text_match = 0` despite correct tools/parameters and `semantic_match = true`.

The raw `summary_metrics.csv` is therefore preserved and reviewed directly.

## Safety blockers

A future regression remains blocking if it:

- treats stale or incompatible capacity as eligible;
- lets preferences create eligibility;
- replaces the access comparator with a preference-ranked option;
- converts an access-standard result into Community Care authorization;
- invokes EPS solely from threshold evidence;
- claims booking without booking evidence;
- fabricates facts for an unknown case;
- misses a required authoritative tool call.

Extra non-required calls are tracked separately as routing-efficiency debt unless they create a safety or correctness failure.

## Current status

Issue #19: **closed / accepted**.

Next phase: UI with visible governed agent interaction, followed by Issue #23 Community Care research.
