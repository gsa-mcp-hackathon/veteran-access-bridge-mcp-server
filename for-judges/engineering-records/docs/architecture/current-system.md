> **Checkpoint scope:** This document retains dated evidence/instructions. Read the [November 18 reconciliation](../submission/documentation-reconciliation-20261118.md) before interpreting “current”, tool counts, deployment state or remaining work. End-to-end synthetic scheduling passed on November 16; later identity/configuration checks have separate scopes. Original results below are preserved.

# Current demonstration architecture

November 15, 2026. The MCP server is the central competition component. This page describes the reviewed IBM/LiveKit demonstration; earlier product narratives remain design history.

| Component | Implemented responsibility | Source |
|---|---|---|
| Avery frontend | Reviewer login, browser audio, conversation/activity and verified receipt projection | [Companion repository](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/frontend/gsa-submission-alignment-20261114/README.md) |
| LiveKit worker | Audio interaction and signed worker assertions bound to the session | [Voice implementation](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/src/veteran_access_bridge/voice) |
| IBM watsonx Orchestrate | Avery intake and selection of permitted case-scoped MCP reads | [v11 read policy](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/agents/avery-scoped-reads-v11.md) |
| Veteran Access MCP | 21 registered tools over validated deterministic services | [MCP implementation](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/src/veteran_access_bridge/mcp) |
| Trusted voice host | Identity, current consent, case/room/participant binding and private booking authority | [Application](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/src/veteran_access_bridge/app), [services](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/src/veteran_access_bridge/services) |
| Synthetic storage | Governed scheduling records in the restricted test database | [Schema](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/db), [migrations](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/supabase) |

## Read path and booking path

IBM-native traces establish one identity call and two encounter reads independently selected by the agent. Their native IDs match server-authorized receipts. The earlier CASE-039 booking used a host-invoked lookup and the private signed booking path. These are separate trials, not one proven autonomous IBM-selected booking journey.

The model cannot create a signing grant, substitute an identity, infer Community Care authorization or turn a read into permission to write. The frontend only projects booking evidence returned for its call. A reviewer cookie permits UI access and does not replace caller identity or consent checks.

## Deployment boundary

Existing IBM Code Engine canary: backend `1e4b26c`, revision `00029`. Existing worker: revision `00003`. Frontend: `f5ae071`, revision `00019`, with reviewer login. See the [deployment inventory](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/frontend/gsa-submission-alignment-20261114/docs/deployment/current-sandbox.md) for exact images and endpoints.

The demonstration uses synthetic data. VA contract adapters default to unavailable and are not evidence of production VA integration. The hosted design has process-local state/quotas and open dependency and broader security findings. [Release results](../evaluation/release-closeout-20261115.md) and [later security work](../evaluation/security-followup-20261115.md) state the tested limits.

## Earlier surfaces

Backend `apps/web/` remains a local UI checked by CI. Frontend `/demo-call` is the separate legacy IBM embed. Historical SIP/Genesys and Phoenix materials remain available for provenance; none is the current judge demonstration route.
