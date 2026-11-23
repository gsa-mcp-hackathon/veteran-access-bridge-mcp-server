# Avery · IBM watsonx Orchestrate agent

The demo used the IBM agent `veteran_access_agent_m64`. Avery handled the conversation and could select authorized MCP tools. The backend checked identity, consent and booking authority before accepting an appointment write.

## Start with the demonstrated configuration

| Reviewer question | Release source |
| --- | --- |
| How was Avery instructed to handle a scheduling call? | [Revision 13 scheduling and CRM instructions](../deploy/ibm/orchestrate/avery-agent-scheduling-v13.md) |
| Which rules guided speech, tool use, handoffs and after-call work? | [Eight IBM guidelines](../deploy/ibm/orchestrate/avery-guidelines-v1.json) |
| How many tools were available to Avery? | The November 18 deployment record reports **21 attached MCP tools and eight guidelines** after the experimental workflow was detached. The canary server advertised **29 tools** with its optional features enabled. [Release inventory and deployment acceptance](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/docs/evaluation/guidelines-and-tool-inventory-20261118.md) |
| Which tool did Avery actually invoke? | The November 18 browser verification trace records a watsonx Orchestrate call to `verify_synthetic_identity`, alongside host events and one linked identity receipt. [Recorded browser verification](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/docs/evaluation/browser-identity-mcp-20261118.json) |

## Understand the source history

The [M6.4 YAML](veteran-access-agent-m64.yaml) identifies the demo agent but contains earlier toolkit bindings. Importing it alone would reproduce an earlier configuration. The [earlier agent YAML](veteran-access-agent.yaml) defines a separate agent.

The numbered Markdown files preserve the development sequence: response evidence (v2), case context (v3–v4), toolkit consolidation (v5–v6) and scoped reads (v7–v11). The [CRM candidate](avery-crm-candidate.md) records the call-management proposal. Read these individually when tracing a specific decision. For the later scheduling instructions and standalone guidelines, use the two release files linked above.

Hosted reproduction also requires an authorized IBM environment and a configured remote toolkit. This folder lets reviewers inspect the original definitions and compare them with recorded deployment evidence.
