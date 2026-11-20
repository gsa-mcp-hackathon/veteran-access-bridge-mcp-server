> Current scoring correction and limits: [November 15 release report](../../docs/evaluation/release-closeout-20261115.md). Earlier pilot scores below require adapter revalidation before comparison.

# DeepEval integration

Pinned version: 4.3.4. Installed separately from the application environment.
MCPUseMetric, MultiTurnMCPUseMetric and MCPTaskCompletionMetric import successfully.
The first three-case OpenAI scoring pilot is complete; see
[pilot results](../DEEPEVAL-PILOT-20261114.md). This is limited MCP-use evidence,
not completion of the full evaluation or security gates.

`score_traces.py` validates newline-delimited records with the frozen tool schemas,
actual input/output, actual tool arguments/results, runtime and schema versions.
It rejects host-invoked calls as evidence of agent tool selection. Default mode
only validates data locally. `--score --model MODEL` opts into paid model calls
using separately configured credentials; the supported provider/model must first
be confirmed. The current CLI path supports DeepEval's named model integration;
an IBM judge would require a reviewed custom provider adapter.

Telemetry is disabled and CONFIDENT_API_KEY removed from the process environment.
Scoring still sends the provided synthetic/redacted trace to the chosen model
provider. Do not use raw credentials, production data or unredacted transcripts.

The historical IBM M6.3/M6.4 files remain historical evidence. Do not score them
with today's registry and call the result current-release evaluation.
