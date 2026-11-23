> **Checkpoint scope:** This document retains dated evidence/instructions. Read the [November 18 reconciliation](../submission/documentation-reconciliation-20261118.md) before interpreting “current”, tool counts, deployment state or remaining work. End-to-end synthetic scheduling passed on November 16; later identity/configuration checks have separate scopes. Original results below are preserved.

# Avery current Codespace and IBM runbook

Verified November 15, 2026. Synthetic data only. Reuse the existing Codespace and IBM applications. **Call in Browser uses LiveKit with IBM watsonx Orchestrate**. The optional native IBM embed is a separate historical interface.

## Existing resources

| Item | Current value |
|---|---|
| IBM Cloud region and project | `ca-tor`, `ce-550000w6t0` |
| Orchestrate management environment | `veteran-access-dev` (not renamed) |
| Agent | `veteran_access_agent_m64` |
| Agent ID | `b38da637-92e4-4c5c-9c7e-d4f8dce28160` |
| Toolkit | `veteran-access-mcp-consolidated` |
| Backend canary | `veteran-access-bridge-m64-canary` |
| Frontend | `vab-avery-callcenter` |
| Worker | `vab-avery-voice-worker` |

The server registers 21 tools; Avery has 13 reviewed attachments. Do not recreate or duplicate the toolkit to reconcile these counts.

## Login and inspect

Use a private terminal in the existing Codespace. Never paste a key into chat or commit it.

```bash
ibmcloud login --sso
ibmcloud target -r ca-tor -g eid-6ac41f127818aff458d82ac8
ibmcloud ce project select --name ce-550000w6t0
ibmcloud target
ibmcloud ce project current
orchestrate env list
orchestrate env activate veteran-access-dev
orchestrate agents list
```

When prompted, privately enter the existing working Orchestrate key. A disabled key cannot be repaired by repeatedly activating the environment. IBM Cloud login, Orchestrate management login, Codespaces secrets and Code Engine runtime secrets are separate. Updating one does not update the others.

Before changes, inspect `git status --short` and `git rev-parse HEAD` in each checkout. Do not blindly switch to main. The current evaluation checkout is `/workspaces/vab-eval-20261114`; application imports must use its `src` through `PYTHONPATH` if an interpreter is editable-installed to another checkout.

## Pinned deployment checkpoint

- Backend image: `ghcr.io/wbgreen0405/veteran-access-bridge:sha-1e4b26c24643bfbe9ba57c4b1d367b468c58144f`.
- Frontend image: `ghcr.io/wbgreen0405/veteran-appointment-bridge@sha256:9bd7ed3ca09d5bae5111554c85736786566475591173739fc64dcb69682c725c`.
- Worker remains revision `00003`, source `0165196`; no worker rollout in this checkpoint.
- Backend tests used revision `00028`; selecting the separately approved CASE-041 produced `00029` with the same image and exactly one environment change. Frontend reviewer rollout is now `00019`; backend and worker specifications were unchanged.
- Agent instruction v11 is active in the existing default runtime. This does not claim a separate live-environment publication.

Only deploy an accepted image to the existing canary after its CI and acceptance gates pass. Capture a private configuration backup first; compare the image and every environment/secret reference afterward. Do not update the main backend or KB application. Dependency findings remain open, so this checkpoint is not authorization for a broader launch.

## Endpoints and checks

| Purpose | Existing endpoint |
|---|---|
| Call in Browser | https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/ |
| Frontend gateway | Same origin `/api/demo-call` |
| Authenticated MCP | https://veteran-access-bridge-m64-canary.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/mcp/ |

Expect 401 for unauthenticated MCP requests and 21 tools after authorized discovery. A page loading is not voice or booking acceptance. Confirm the actual RTC greeting, matching case-scoped evidence, same-call consent and a verified receipt before claiming a booking. Never reuse a consumed case. The five-minute guest session does not renew when activity is polled.

Use the current release evaluation report in the backend repository for evidence and limitations. The existing guest-access deployment must be reconciled with GSA's non-public-deployment requirement before submission. Keep all credentials server-side; `.env.example` documents names only.

## Key revocation boundary

Rotate `VAB_MCP_API_KEY` through the existing protected secret workflow, update its authorized Orchestrate connection, and verify the old key receives 401 while the new key discovers 21 tools. Do not print either value. Key rotation revokes MCP bearer access; stopping Avery or rotating the MCP key does not revoke already-issued worker assertions or undo completed appointments. Stop the relevant worker/booking entry point and let short-lived assertions expire when containing that separate path. Record the scope and time of every action.
