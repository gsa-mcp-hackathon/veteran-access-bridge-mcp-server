# Evaluate the scheduling server and agent

| Question | Evidence or action |
| --- | --- |
| Does the MCP server return the expected scheduling facts? | [Run the 16 Primary Care gold questions](primary-care/README.md). |
| What protects identity, consent and appointment writes? | [Run backend tests](../tests/README.md) or inspect the [recorded per-check results](../release/evidence/control-results.csv). |
| Which agent behavior was observed during verification? | [November 18 browser verification record](../release/evidence/browser-identity-mcp-20261118.json) and [attachment inventory](../release/evidence/guidelines-and-tool-inventory-20261118.md). |
| Which caller scenarios were proposed? | [Scenario matrix](../release/evidence/Primary-Care-Caller-Scenarios.csv). Read the Status column before attributing a result. |
| Which tools and evaluators were used historically? | [IBM assets](watsonx/README.md), [DeepEval](deepeval/README.md) and [Phoenix](phoenix/README.md). Their setup and results are specific to the release and environment named in each record. |

[Judge-facing evaluation and results](../docs/evaluation/index.md) · [Pinned development evaluation archive](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/eval)
