# DeepEval MCP-use pilot — November 14, 2026

**Three recorded IBM agent cases scored 1.0/1.0 for MCP use.** This narrow pilot measures tool choice and argument correctness within the ten-tool canary toolkit. It is not a security certification, booking acceptance test, or complete agent evaluation.

| Case | Recorded behavior | MCP-use score | Threshold | Estimated judge cost (USD) |
|---|---|---:|---:|---:|
| A02 | Verify synthetic identity only | 1.0 | 0.8 | 0.0027896 |
| A03 | Reject incorrect identity without appointment disclosure | 1.0 | 0.8 | 0.0027912 |
| A11 | Verify identity, read encounter, read lifecycle | 1.0 | 0.8 | 0.0042696 |

Total reported evaluation cost: **$0.0098504**, approximately one cent. This is DeepEval's estimate, not an independently checked billing statement. Each case was scored once; five recorded MCP calls were evaluated. No new Avery conversation, appointment, database write, deployment or IBM agent change was initiated by this scoring run.

## Interpretation alongside IBM

IBM's original overall results remain unchanged: A02 passed; A03 and A11 failed. DeepEval found their tool selections and arguments appropriate. For A03, IBM penalized an omitted honorific and exact response wording. DeepEval accepted the supplied identity arguments. For A11, the three tools and verified case ID were appropriate, but the response still needs improvement: absent lifecycle data was described as confirmed workflow history, and no-booking status was not explicit. A high MCP-use score does not resolve those issues.

The model's rationale called synthetic name/date-of-birth matching authentication. That terminology is not adopted as a security conclusion: these are synthetic fixture checks, not production identity proofing.

## Method and provenance

- DeepEval 4.3.4, MCP SDK 1.30.0, `MCPUseMetric`, LLM mode, synchronous execution, threshold 0.8.
- Judge: `gpt-4.1-mini` through the OpenAI API, using the user-authorized Codespaces secret `MCP_SERVER_EVAL`, mapped to `OPENAI_API_KEY` only in the scoring process environment. The key was never printed or stored in repository files.
- Avery remains the existing IBM Orchestrate agent. OpenAI was used only as an evaluator of recorded synthetic traces.
- Telemetry disabled; Confident API key removed from scoring environment. Synthetic input/output, tool schemas and recorded calls were transmitted to OpenAI for scoring.
- Import/scoring code: `8b768c9`. Captured schema registry SHA-256: `b89cf3e2801f6e3c075393b030a1052b665cc0aa05b507fe87c64fff22f5ce84`.
- Source run: `ibm-fixture-smoke/2026-11-14_15-55-50`; source trace hashes are in [IBM smoke results](IBM-SMOKE-20261114.md).
- Only the ten tools assigned from the canary toolkit were exposed to the metric. Other IBM toolkits and built-in skill loads are outside this pilot. These three traces contain exactly one user turn each.
- Importer matches tool response IDs and names, retains literal text/structured results, rejects missing results and nonliteral executable representations. It does not execute serialized Python content.
- Importer and existing adapter validation: **10 tests passed, 8 subtests passed**; lint passed. These are harness checks, not additional agent performance cases.
- Current deployed image digest remains unverified. Encounter availability is a frozen demonstration fixture, not current operational availability.

Codespace evidence under `/workspaces/vab-eval-20261114/eval/results/`:

| File | SHA-256 |
|---|---|
| deepeval-pilot-input.jsonl | 6eb49c0aba8398010cb51ca8b8469698c61e759f1422885ff7b03e98da947135 |
| deepeval-pilot-scores.json | 68ec6950f108addf70349159a60c7e1812c5a60591fa480ff008bfd1cd7c108c |

The scores file retains the judge's full explanations and per-case cost estimates. The input file retains source trace hashes, arguments, results and schemas. Do not overwrite these artifacts when extending the suite.

## Remaining evaluation

Next: version semantic task-completion and safety assertions, correct response wording, and expand to repeated adversarial and benign-control cases. Multi-turn refusal traces need a conversational metric rather than flattening them into this single-turn importer. Direct server denial tests, authorization/replay tests and live database acceptance remain separate evidence lanes. Preserve failures and report untested challenges explicitly.
