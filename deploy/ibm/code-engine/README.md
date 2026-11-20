# IBM Cloud Code Engine — Deployment Guide

This guide documents the **validated hackathon deployment path** for Veteran Access Bridge on IBM Cloud Code Engine.

> Synthetic data only. No real VA systems are connected, no PHI is used, and production booking writes remain disabled.

**Latest Avery M6.4 sandbox procedure:** [Codespace CLI re-login and pinned canary + frontend deployment](../../../docs/operations/avery-m64-codespace-ibm-cli-relogin-deploy.md). This document also covers older M6.3 and main-backend history; follow the linked runbook for the current M6.4 sandbox instead of updating the main `veteran-access-bridge` application.

## Validated environment — 2026-10-24

- IBM Cloud region: `ca-tor`
- Resource group: `eid-6ac41f127818aff458d82ac8`
- Code Engine project: `ce-550000w6t0`
- Application: `veteran-access-bridge`
- Last remotely validated container image: `ghcr.io/wbgreen0405/veteran-access-bridge:0.4.1`
- GHCR registry secret: `ghcr-veteran-access`
- MCP secret: `veteran-access-mcp-key`
- Remote MCP transport: `streamable-http`
- Public application URL:
  `https://veteran-access-bridge.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud`

The earlier `hackathon-vdb*` / IBM Container Registry path was not used for the final deployment.
The hackathon-provisioned Toronto project was used instead.

## Architecture

```text
GitHub Actions
      ↓
private GHCR image
      ↓
IBM Code Engine — ce-550000w6t0
      ↓
Veteran Access Bridge
  /health
  /api/*
  /mcp/
      ↓
governed deterministic scheduling services
      ↓
synthetic VistA / Federal EHR / HSRM / EPS adapters
```

## Prerequisites

```powershell
ibmcloud login --sso
ibmcloud target -g eid-6ac41f127818aff458d82ac8 -r ca-tor

ibmcloud plugin install code-engine
ibmcloud plugin install container-registry

ibmcloud ce project select --name ce-550000w6t0
ibmcloud ce project current
```

## Container publication

The repository publishes the validated Dockerfile with GitHub Actions:

`.github/workflows/publish-container.yml`

It builds:

`deploy/ibm/Dockerfile`

The current M6.3 publication has completed successfully and publishes:

```text
ghcr.io/wbgreen0405/veteran-access-bridge:0.4.1
ghcr.io/wbgreen0405/veteran-access-bridge:latest
```

The repository is private, so Code Engine needs a read-only GHCR pull credential.

## GHCR registry secret

Create a GitHub PAT with only `read:packages` and a short appropriate expiration.

Do not commit or paste the token into source control.

```powershell
$GhcrToken = Read-Host "Paste GHCR read token"

ibmcloud ce registry create `
  --name ghcr-veteran-access `
  --server ghcr.io `
  --username wbgreen0405 `
  --password $GhcrToken
```

Verify:

```powershell
ibmcloud ce registry list
```

## MCP bearer secret

Generate a 32-byte random secret:

```powershell
$McpKey = python -c "import secrets; print(secrets.token_hex(32))"
$McpKey.Length
```

Expected length: `64`.

Create the Code Engine secret:

```powershell
ibmcloud ce secret create `
  --name veteran-access-mcp-key `
  --from-literal VAB_MCP_API_KEY=$McpKey
```

If rotating the key later:

```powershell
ibmcloud ce secret update `
  --name veteran-access-mcp-key `
  --from-literal VAB_MCP_API_KEY=$McpKey
```

The same value must be configured as the bearer credential in watsonx Orchestrate.

## Deploy the application

```powershell
ibmcloud ce application create `
  --name veteran-access-bridge `
  --image ghcr.io/wbgreen0405/veteran-access-bridge:0.4.1 `
  --registry-secret ghcr-veteran-access `
  --port 8080 `
  --env VAB_MCP_TRANSPORT=streamable-http `
  --env VAB_DEMO_HOST=0.0.0.0 `
  --env-from-secret veteran-access-mcp-key `
  --wait
```

Retrieve status and URL:

```powershell
ibmcloud ce application get -n veteran-access-bridge
```

## Health validation

```powershell
$AppUrl = "https://veteran-access-bridge.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"
Invoke-RestMethod "$AppUrl/health"
```

Validated result:

- `status = ok`
- `synthetic = true`
- `production_writes_enabled = false`
- milestones M3–M6

## Remote MCP validation

```powershell
$body = @{
  jsonrpc = "2.0"
  id      = 1
  method  = "initialize"
  params  = @{
    protocolVersion = "2025-03-26"
    capabilities    = @{}
    clientInfo      = @{
      name    = "vab-code-engine-smoke-test"
      version = "0.1.0"
    }
  }
} | ConvertTo-Json -Depth 10

$response = Invoke-WebRequest `
  -Uri "$AppUrl/mcp/" `
  -Method Post `
  -Headers @{
    "Authorization" = "Bearer $McpKey"
    "Accept"        = "application/json, text/event-stream"
  } `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing
```

Validated result:

- HTTP `200`
- `mcp-session-id` returned
- protocol `2025-03-26`
- server name `Veteran Access MCP`

## Update / redeploy

Publish a new image tag first, then update Code Engine:

```powershell
ibmcloud ce application update `
  --name veteran-access-bridge `
  --image ghcr.io/wbgreen0405/veteran-access-bridge:<new-version>
```

## Inspect logs

```powershell
ibmcloud ce application logs --name veteran-access-bridge --follow
```

## Rollback

List revisions:

```powershell
ibmcloud ce revision list --application veteran-access-bridge
```

The local Docker and stdio MCP paths remain available for development and rollback testing.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PORT` | Set by Code Engine | `8080` | Listening port |
| `VAB_DEMO_HOST` | No | `0.0.0.0` | Bind address |
| `VAB_MCP_TRANSPORT` | No | `stdio` | `stdio` or `streamable-http` |
| `VAB_MCP_API_KEY` | If remote MCP | — | Demo bearer service-auth secret |

## Security posture

- Synthetic data only; no PHI.
- Production VA interfaces are not connected.
- Production writes are disabled.
- `X-Demo-Role`, `X-Demo-Actor`, and `X-Demo-Case` are demo-only controls, not production authentication.
- TLS is provided by Code Engine ingress.
- `VAB_MCP_API_KEY` is demo service authentication, not production VA identity.
- GHCR and MCP credentials are stored outside the repository.
- Production use requires approved VA interfaces, identity/session enforcement, durable persistence, audit retention, secrets rotation, reconciliation, monitoring, rollback, and VA security review.


## M6.3 remote acceptance — PASSED

Validated against Code Engine image `0.4.1`:

1. `/health` returns healthy synthetic-only service state.
2. `/mcp/version` returns `0.4.1`.
3. Bearer-authenticated MCP initialize returns HTTP 200.
4. `tools/list` includes:
   - `determine_workflow_state`
   - `search_availability`
   - `assess_access_standard`
   - `get_scheduling_encounter`
5. `get_scheduling_encounter` for `DEMO-CARD-5000335-001` returns:
   - NEW clinic classification
   - 5 internal scheduling slots evaluated
   - 4 M6.2-eligible internal options
   - canonical PID 2026-10-01
   - 28-day Specialty standard
   - earliest eligible VA comparator on 2026-11-05 / 35 days
   - wait standard exceeded
   - Community Care review recommendation only
   - authorization `NOT_EVALUATED`
   - preference ranking that does not replace the access-standard comparator
   - no EPS invocation
   - no booking creation


Primary Care acceptance also passed through the same remote MCP path:

- case `DEMO-PC-5000999-001`
- classification `ESTABLISHED`
- PID `2026-11-01`
- 3 raw slots / 2 eligible options
- incompatible 7-day NEW-patient slot excluded deterministically
- comparator `OPT-VISTA-SLOT-PC-5000999-001`
- 14-day wait under the 20-day Primary Care standard
- no Community Care review recommendation
- authorization `NOT_EVALUATED`
- no EPS invocation
- no booking creation

### Automated M6.3 validation

With the Code Engine bearer secret loaded into the local process as
`VAB_MCP_API_KEY`:

```powershell
.\deploy\ibm\code-engine\validate-m63.ps1
```

The script is read-only and validates health, version, MCP initialization,
tool discovery, the canonical Cardiology encounter, and the established Primary
Care encounter through the same `get_scheduling_encounter` tool.


## watsonx Orchestrate application runtime

The MSA application backend can run with the same container image in two modes:

- `ORCHESTRATE_RUNTIME_MODE=fake` for local/offline development.
- `ORCHESTRATE_RUNTIME_MODE=remote` for the IBM Code Engine deployment.

The browser never receives Orchestrate credentials. The backend is the only component that reads them.

### Durable IBM IAM authentication

The validated deployed authentication mode stores the API key generated from
the watsonx Orchestrate instance **Settings → API details** in the Code Engine
secret and exchanges it server-side for short-lived IAM access tokens. The
runtime caches the access token and refreshes it before expiry.

A generic IBM Cloud service-ID API key was tested with watsonx Orchestrate IAM
roles but the chat endpoint returned `ORCHESTRATE_AUTHENTICATION`. Do not
substitute a generic service-ID API key for the validated Orchestrate instance
API key unless IBM changes the endpoint authorization contract and the live
smoke test is rerun successfully.

Preferred secret content:

```powershell
$OrchestrateApiKey = Read-Host "Paste watsonx Orchestrate instance API key"

ibmcloud ce secret create `
  --name veteran-access-orchestrate-auth `
  --from-literal ORCHESTRATE_API_KEY=$OrchestrateApiKey
```

For rotation:

```powershell
ibmcloud ce secret update `
  --name veteran-access-orchestrate-auth `
  --from-literal ORCHESTRATE_API_KEY=$OrchestrateApiKey
```

`ORCHESTRATE_BEARER_TOKEN` remains supported only as a temporary compatibility
path. Do not store an expiring IAM access token as the permanent deployment
credential.

The current live acceptance evidence is tied to the Orchestrate instance API
key. Revisit service-ID authorization only as a separate hardening experiment;
do not change the production-like demo credential path without a passing remote
smoke test.

Do not put the API key or access token in `.env.example`, PowerShell source,
GitHub Actions variables, browser JavaScript, telemetry, SSE, or API responses.

### Canonical live runtime configuration

The live IBM acceptance test established this runtime contract:

| Variable | Code Engine value | Secret? | Purpose |
|---|---|---:|---|
| `APP_ENV` | `code-engine` | No | Deployment environment label |
| `ORCHESTRATE_RUNTIME_MODE` | `remote` | No | Enable server-side IBM runtime |
| `ORCHESTRATE_BASE_URL` | watsonx Orchestrate service instance URL | No | Runtime endpoint base |
| `ORCHESTRATE_AGENT_ID` | `89801bbc-fa87-41f9-b9d7-d2a9b4cbf0c3` | No | Runtime UUID for `veteran_access_agent` |
| `ORCHESTRATE_CHAT_PATH` | `/v2/orchestrate/{agent_id}/chat/completions` | No | Validated chat-completions path |
| `ORCHESTRATE_IAM_TOKEN_URL` | `https://iam.cloud.ibm.com/identity/token` | No | IBM IAM token exchange endpoint |
| `ORCHESTRATE_TOKEN_REFRESH_SKEW_SECONDS` | `300` | No | Refresh access token before expiry |
| `ORCHESTRATE_TIMEOUT_SECONDS` | `30` | No | Backend runtime timeout |
| `ORCHESTRATE_MAX_RETRIES` | `1` | No | Bounded retry count |
| `EVENT_STREAM_HEARTBEAT_SECONDS` | `15` | No | Application SSE keep-alive cadence |
| `EVENT_STREAM_IDLE_TIMEOUT_SECONDS` | `300` | No | Idle SSE reconnect boundary |
| `MSA_UI_ALLOWED_ORIGINS` | comma-separated UI origin(s), when needed | No | Deployment-edge/UI origin contract |
| `REMOTE_MCP_URL` | only if the app backend directly calls remote MCP | No | Optional backend MCP location |

The existing `veteran-access-mcp-key` secret remains separate and supplies
`VAB_MCP_API_KEY` for remote MCP service authentication.

### Secure embedded Orchestrate chat

The embedded Avery channel uses IBM watsonx Orchestrate embed security with
RS256 JWT identity tokens. The public key is registered in
**watsonx Orchestrate → Settings → Embed Security**. The matching private key
must remain server-side and must never be committed or exposed in browser
JavaScript.

For the current synthetic demo, no OBO/SSO `user_payload` is required. The
Bridge issues a short-lived token containing only the synthetic case-scoped
`sub`, `iat`, and `exp` claims.

Encode the existing local private PEM without printing it:

```powershell
$EmbedPrivateKeyB64 = [Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("local\keys\wxo_embed_private.pem")
)
```

Create the Code Engine secret:

```powershell
ibmcloud ce secret create `
  --name veteran-access-orchestrate-embed `
  --from-literal ORCHESTRATE_EMBED_PRIVATE_KEY_B64=$EmbedPrivateKeyB64
```

If it already exists, rotate/update it instead:

```powershell
ibmcloud ce secret update `
  --name veteran-access-orchestrate-embed `
  --from-literal ORCHESTRATE_EMBED_PRIVATE_KEY_B64=$EmbedPrivateKeyB64
```

The deployment helper injects this secret and sets
`ORCHESTRATE_EMBED_TOKEN_TTL_SECONDS=3600`. IBM documents a maximum token
lifetime of 7100 seconds.

The browser obtains tokens only through:

```text
GET /api/orchestrate/embed-token
```

The endpoint requires the existing synthetic demo case scope. The private key
never leaves Code Engine. The embedded client sends the initial JWT as
`identityToken` and refreshes it when IBM emits `identityTokenExpired`.

### Deploy or update

The repository helper remains dry-run by default:

```powershell
.\deploy\ibm\code-engine\deploy.ps1 `
  -OrchestrateBaseUrl "https://<your-orchestrate-runtime-base>"
```

For a live update:

```powershell
.\deploy\ibm\code-engine\deploy.ps1 `
  -DryRun $false `
  -Version latest `
  -OrchestrateBaseUrl "https://<your-orchestrate-runtime-base>" `
  -AllowedUiOrigins "https://<msa-ui-origin>"
```

The helper applies both server-side secrets:

- `veteran-access-mcp-key`
- `veteran-access-orchestrate-auth`

and configures the validated agent UUID and v2 chat path without changing
application code.

### Health and readiness

`/health` remains the basic process/synthetic-safety check.

`/readiness` returns safe deployment metadata including:

- application environment
- runtime mode
- agent ID
- whether the base URL is configured
- authentication mode (`iam_api_key`, `bearer_token`, or `none`)
- whether an API key or temporary bearer token is configured
- number of configured MSA UI origins
- SSE heartbeat/idle settings
- Code Engine revision/application metadata

It never returns the Orchestrate API key, IAM access token, bearer token, or
configured base URL.

Expected deployed readiness characteristics for the durable path:

- `ready = true`
- `orchestrate_runtime_mode = remote`
- `orchestrate_base_url_configured = true`
- `orchestrate_auth_mode = iam_api_key`
- `orchestrate_api_key_configured = true`
- `production_writes_enabled = false`

### Deployed synthetic runtime smoke test

Run:

```powershell
python .\deploy\ibm\code-engine\smoke_runtime.py `
  --url "https://<veteran-access-bridge-code-engine-url>" `
  --timeout 120
```

Acceptance requires:

- `passed = true`
- `runtime_mode = remote`
- real Orchestrate run ID
- governed Primary Care encounter
- deterministic calendar projection
- SSE correlation preserved
- no credential leakage
- `production_write_attempted = false`

For local contract validation only:

```powershell
python .\deploy\ibm\code-engine\smoke_runtime.py `
  --url "http://127.0.0.1:8000" `
  --allow-fake
```

`--allow-fake` must not be used as IBM deployment acceptance evidence.
