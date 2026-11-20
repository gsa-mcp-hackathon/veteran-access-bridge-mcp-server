> **Checkpoint scope:** This document retains dated evidence/instructions. Read the [November 18 reconciliation](../../../docs/submission/documentation-reconciliation-20261118.md) before interpreting “current”, tool counts, deployment state or remaining work. End-to-end synthetic scheduling passed on November 16; later identity/configuration checks have separate scopes. Original results below are preserved.

# watsonx Orchestrate — Remote MCP Connection

This guide documents the validated connection between the existing **Veteran Access Agent**
and Veteran Access Bridge running in IBM Cloud Code Engine via Streamable HTTP MCP.

## Deployment tier distinction

| Tier | Transport | Where | Notes |
|---|---|---|---|
| **Local dev** | `stdio` | Developer workstation | Retained for local development / rollback |
| **Container demo** | HTTP | Local Docker | Demo UI + API + optional `/mcp` |
| **Remote agent** | `streamable_http` | IBM Cloud Code Engine | **Validated 2026-10-24** |
| **Production** | — | Not implemented | Requires VA security review |

## Validated remote path

```text
watsonx Orchestrate
        ↓
veteran_access_agent
        ↓
veteran-access-mcp-remote-m63
        ↓  bearer-authenticated streamable_http
Veteran Access Bridge on IBM Code Engine
        ↓
Veteran Access MCP
        ↓
governed deterministic scheduling services
        ↓
synthetic VistA / Federal EHR / HSRM / EPS adapters
```

No scheduling business logic moves into Orchestrate.
Orchestrate remains the agent/control plane.
Veteran Access Bridge remains the authoritative scheduling service.

## Current validated configuration — 2026-10-24

The validated watsonx Orchestrate draft now uses:

- Orchestrate environment: `veteran-access-dev`
- Agent: `veteran_access_agent`
- Connection ID: `veteran_access_mcp_connection`
- Active M6.3 toolkit: `veteran-access-mcp-remote-m63`
- Attached tools:
  - `get_scheduling_encounter`
  - `assess_access_standard`
  - `search_availability`
  - `determine_workflow_state`
- Transport: `streamable_http`
- Code Engine app: `veteran-access-bridge`
- Code Engine image: `ghcr.io/wbgreen0405/veteran-access-bridge:0.4.1`
- Remote MCP URL:
  `https://veteran-access-bridge.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/mcp/`

The connection bearer credential was rotated and the Draft credential refreshed
before M6.3 acceptance. The bearer token is demo service authentication only; it
is not production VA identity.

Validated Draft Preview behavior:

- Cardiology canonical prompt called `get_scheduling_encounter` first.
- Primary Care canonical prompt called `get_scheduling_encounter` first.
- deterministic eligibility remained upstream of preference ranking;
- access-standard comparator remained independent from preference ranking;
- Community Care authorization was never inferred;
- EPS was not invoked from an access-standard result alone;
- no booking was claimed without booking evidence.

## M6.4 autonomous scheduling candidate — 2026-10-28

The validated M6.3 baseline above remains unchanged. M6.4 is a separate Draft-only
candidate with its own toolkit and agent definition so the accepted M6.3 configuration
is never overwritten during autonomy testing.

M6.4 candidate toolset (`veteran-access-mcp-remote-m64`):

- `verify_synthetic_identity`
- `get_scheduling_encounter`
- `assess_access_standard`
- `search_availability`
- `determine_workflow_state`
- `get_case_lifecycle_state`
- `prepare_scheduling_handoff`
- `get_scheduling_handoff`
- `validate_option_selection`
- `prepare_veteran_confirmation_request`

The ten entries above are the M64 scheduling-toolkit subset, not the complete
cloud agent assignment. Read-only inventory of `veteran_access_agent_m64` in
the active `veteran-access-dev` environment on 2026-11-13 showed 21 assigned
tools total: these 10 scheduling read/preparation tools, 6 VA read-only tools,
4 knowledge-base read-only tools, and 1 Community Care read-only tool. No
decision or booking write tool was assigned. The existing M64 canary MCP
connection, `veteran_access_m64_canary_connection`, was listed for Draft and
Live. Listing is configuration evidence only, not proof both endpoints execute.
Preserve this inventory and connection; do not re-import or replace resources
to enable the private scheduling service.

Intentionally excluded from Avery:

- `record_option_selection` — Scheduler-owned decision;
- `record_veteran_confirmation` — Veteran-owned response;
- `validate_booking_preconditions` — Scheduler-context booking gate;
- `record_lifecycle_event` — generic outcome-write authority.

The simulated booking commit remains service-layer-only.

The Draft acceptance goal is not "Avery books autonomously." It is: Avery first
verifies the Veteran against approved synthetic identity evidence, then performs
routine read, validation, and preparatory work, and stops at a Veteran/MSA
authority boundary with context preserved. No protected scheduling detail is
disclosed before identity verification succeeds.

M6.4 candidate identities:

- agent: `veteran_access_agent_m64`
- toolkit: `veteran-access-mcp-remote-m64`
- connection reused: `veteran_access_mcp_connection`
- M6.3 agent/toolkit: preserved and untouched

Use `deploy/ibm/orchestrate/configure-m64.ps1` for M6.4. Do not use the M6.3
closeout helper to configure autonomy.

## ADK registration pattern

```powershell
orchestrate toolkits add `
  --kind mcp `
  --name veteran-access-mcp-remote-m63 `
  --description "Veteran Access Bridge governed remote MCP on IBM Code Engine" `
  --url "https://veteran-access-bridge.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/mcp/" `
  --transport streamable_http `
  --tools "get_scheduling_encounter,assess_access_standard,search_availability,determine_workflow_state" `
  --app-id veteran_access_mcp_connection
```

The associated Draft connection must contain the bearer credential before toolkit
creation. The token must match `VAB_MCP_API_KEY` in Code Engine.

## Acceptance evidence — 2026-10-24

### Code Engine health

`/health` returned:

- `status=ok`
- `synthetic=true`
- `production_writes_enabled=false`
- milestones M3–M6

### Remote MCP protocol

A bearer-authenticated MCP `initialize` request returned:

- HTTP `200`
- MCP session ID
- protocol `2025-03-26`
- server name `Veteran Access MCP`
- governance instructions prohibiting diagnosis, invented authorization, and real booking

### Orchestrate end-to-end run

Prompt:

```text
Search for available cardiology appointments for case DEMO-CARD-5000335-001.
```

Observed tool order:

```text
1. determine_workflow_state
   → workflow_state = READY_TO_SEARCH
   → synthetic = true

2. search_availability
   → synthetic scheduling options returned
```

Observed behavioral controls:

- VA, Federal EHR, and Community Care options remained distinct.
- Community Care authorization was not inferred.
- stale availability was identified and excluded from use.
- no appointment was claimed as booked.
- scheduler review remained explicit.
- the source evidence timestamp is synthetic fixture data, not live production freshness.

## Agent wording guardrails

The checked-in agent definition should:

- use **Available for Scheduler Consideration** instead of **Ready to Book** when
  availability alone has been established;
- label `searched_at` and similar fixture timestamps as **synthetic source timestamps**;
- continue to require `determine_workflow_state` before `search_availability`.

## Post-M6.3 toolkit cleanup

Before the final evaluation checkpoint, remove only the obsolete remote toolkit
registrations while preserving the active M6.3 toolkit and the local rollback
toolkit.

Dry run:

```powershell
.\deploy\ibm\orchestrate\cleanup-legacy-toolkits.ps1
```

Execute:

```powershell
.\deploy\ibm\orchestrate\cleanup-legacy-toolkits.ps1 -DryRun $false
```

The cleanup removes only:

- `veteran-access-mcp-remote-m61`
- `veteran-access-mcp-remote`

It preserves:

- `veteran-access-mcp-remote-m63` — active M6.3 toolkit
- `veteran-access-mcp` — local development / rollback registration
- unrelated toolkits

The script refuses cleanup if the active M6.3 toolkit is not present.

## CLI evaluation checkpoint

watsonx Orchestrate ADK supports command-line evaluation workflows.

Two supported patterns are useful:

1. generate test cases from user stories and then evaluate/analyze them;
2. record live interactions, then evaluate/analyze the recorded test cases.

Core commands:

```powershell
orchestrate evaluations generate --stories-path <stories.csv> --tools-path <tools_dir> --env-file .env

orchestrate evaluations evaluate --test-paths <test_case_path> --output-dir <output_dir> --env-file .env

orchestrate evaluations analyze -d <execution_path> --env-file .env

orchestrate evaluations analyze --mode enhanced -d <execution_path> --env-file .env
```

For the current Veteran Access Bridge checkpoint, use the M6.3 watsonx test suite
as the source of truth. The CLI report should capture at minimum journey success,
tool-call precision/recall, agent routing accuracy, total tool calls, and response
time. The UI remains useful for reviewing saved tests and visual metrics, but the
checkpoint can be executed and analyzed from the CLI.

### M6.4 direct CLI evaluation

After the M6.4 agent and remote toolkit are refreshed, run the versioned
13-case suite from Codespaces/Linux with:

```bash
pwsh ./deploy/ibm/orchestrate/run-m64-evaluation.ps1
```

The suite covers:

- identity required before protected scheduling disclosure;
- spoken DOB normalization and positive synthetic identity matching;
- failed identity verification / fail-closed behavior;
- fresh Scheduling Encounter + lifecycle + existing handoff sequencing;
- preference rank versus access-standard comparator;
- stale-slot exclusion;
- access-standard / Community Care / EPS guardrails;
- Veteran option validation without Scheduler impersonation or persistence;
- "book it" refusal at the governed human boundary;
- conflicting Community Care readiness/authorization evidence;
- Primary Care encounter and access-standard behavior;
- unknown-case fail-closed behavior.

The runner always prints `summary_metrics.csv` in a paste-ready block. Standard
and enhanced analyzer failures are treated as non-blocking post-processing
because the M6.3 evaluation demonstrated an IBM `text_match` schema
incompatibility after otherwise successful execution.

## Local rollback

Do not delete the local stdio path from the repository.

If remote connectivity fails:

1. repoint `agents/veteran-access-agent.yaml` tool references to the local
   `veteran-access-mcp` toolkit;
2. re-import the same `veteran_access_agent`;
3. validate the canonical synthetic Cardiology case locally.

The local toolkit may coexist with the remote toolkit as a rollback/development aid.
It is not the active toolkit for the validated remote agent.

## Security considerations

| Control | Status |
|---|---|
| TLS | Provided by Code Engine ingress |
| `VAB_MCP_API_KEY` | Demo service-auth control — not VA identity |
| Scheduler/Veteran role enforcement | Enforced server-side by service layer |
| Case-scope enforcement | Enforced server-side by service layer |
| Production writes | Disabled |
| PHI | No real PHI; synthetic data only |
| Secrets committed | Never |

A production deployment connecting to real VA scheduling systems requires approved
VA interfaces, strong identity/session management, secrets rotation, persistent
transactional storage, audit retention, and explicit VA security review.


## M6.3 Orchestrate acceptance — PASSED

For the M6.3 agent/toolkit update, the target toolkit name is:

`veteran-access-mcp-remote-m63`

The checked-in agent should use `get_scheduling_encounter` first for real-time
scheduling, option comparison, preference-fit, and current scheduling-status
questions.

Canonical acceptance prompt:

```text
For case DEMO-CARD-5000335-001, show me the current scheduling encounter,
the eligible internal options, which options best match the Veteran's
preferences, whether VA meets the applicable access standard, and what
governed action is allowed next.
```

Expected behavior:

1. `get_scheduling_encounter` is called.
2. The response preserves PID `2026-10-01`.
3. The Specialty access standard remains 28 days.
4. The earliest eligible VA comparator remains the FEHR 2026-11-05 option
   at 35 days even if the Veteran preference ranking places another option first.
5. Community Care is described as an eligibility-review recommendation only.
6. No authorization is inferred.
7. EPS is not invoked solely because the wait standard is exceeded.
8. No booking is claimed unless `SIMULATED_BOOKED` and booking evidence exist.
9. The environment is identified as synthetic demonstration data.
