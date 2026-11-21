# Clean-room reproducibility: test plan and observed status

This is the **independent install and verification protocol** for Veteran Access Bridge. Read it alongside the [VS Code walkthrough](vs-code.md), [configuration and secrets](configuration-and-secrets.md), and [connected product guide](connected-product.md).

!!! warning "Not yet certified as a fully reproducible Avery deployment"
    This audit performed static source checks and an attempted locked installation in a fresh, restricted execution environment. It **did not** deploy an IBM instance, obtain VA sandbox credentials, create a Supabase project, establish a LiveKit/Deepgram call, or execute a fresh hosted synthetic booking. Historical project evaluation reports are separate evidence, not a substitute for a new-reader run.

## What was tested in this audit

**Audit context:** 2026-11-20 repository archive (the uploaded main-branch ZIP with documentation improvements); isolated Linux execution environment; Python 3.13.5 preinstalled; `uv` available; no Python 3.12 runtime, prepopulated `uv` dependencies, cloud credentials or functional public network package-install route. A downloaded ZIP does not contain `.git` history; a genuine `git clone` is needed for the `git rev-parse` step. The audit was performed against unpacked archive contents, **not** a fresh Git clone.

| Check | Observed result | Interpretation |
|---|---|---|
| Required project Python version | `.python-version` says `3.12`; `pyproject.toml` permits Python `>=3.12` | Requirement identified; 3.12 not installed in audit environment |
| Offline locked install: `uv sync --locked --group dev --python 3.12 --offline` | **BLOCKED:** `No interpreter found for Python 3.12` | Prerequisite failure; does not establish package-resolution or application failure |
| Python syntax inspection | **PASS:** 153 source and script Python files parsed | Static parse only; does not prove imports or runtime behavior |
| Bundled fixture JSON parsing | **PASS:** 16 JSON files parsed | Structural JSON check only; not scheduling-contract validation |
| Relative Markdown file targets | **PASS:** 84 local Markdown targets existed | Does not validate external URLs, heading fragments or rendered page navigation |
| `uv run` MCP tool discovery and sample encounter | **NOT RUN** | Python 3.12/dependencies unavailable |
| MkDocs strict build / visual browser inspection | **NOT RUN** | MkDocs not installed in audit environment |
| Cloud integrations and full voice call | **NOT RUN** | Requires independently provisioned, approved service environments and credentials |

## Independent reviewer setup — VS Code (recommended)

1. On an **approved workstation**, verify that Git and `uv` are installed (`git --version`, `uv --version`). Python 3.12 must be available or downloadable through approved channels. Use a terminal that is permitted to install project dependencies. If workplace networking blocks installation, **stop and record that blocker**; do not bypass organizational controls.
2. Clone a clean copy; record the actual commit and branch. A ZIP can be inspected but cannot provide a Git revision ID.
3. Run the following commands in the repository root, one at a time:

```bash
git clone https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git
cd veteran-access-bridge-mcp-server
git rev-parse HEAD
uv --version
uv python find 3.12
uv sync --locked --group dev --python 3.12
uv run --no-sync python scripts/list_local_mcp_tools.py
uv run --no-sync python scripts/read_scheduling_encounter.py DEMO-PC-5000999-001
uv run --no-sync python scripts/read_scheduling_encounter.py UNKNOWN-CASE
uv run --no-sync python eval/primary-care/run_gold.py
uv run --no-sync pytest -q tests/test_m6_2_primary_care_scenarios.py
```

**Acceptance:** record the installed Python version, dependency installation result and actual tool count. The current walkthrough expects a 21-tool default configuration, with the established Primary Care encounter checking three slots (two eligible, one excluded). `read_only: true` and `booking_created: false` must be present. The `UNKNOWN-CASE` request must fail with an unknown synthetic case; that is an **expected negative test**. Record the exact gold-test and pytest results, including fails and skips. Do not mark PASS until a fresh run produces this evidence.

??? info "When Python 3.12 is unavailable"
    `uv python find 3.12` is a diagnostic, not an installer. `uv sync` may download an approved managed runtime when network access permits. If your organization prohibits it, ask for an approved Python 3.12 distribution. Do not silently switch runtime versions and call the documented install verified.

??? tip "Running in GitHub Codespaces instead"
    Codespaces is **optional**, not part of the application architecture. Follow the [Codespaces bootstrap](codespaces.md), record the commit SHA, and execute the **same** MCP fixture and evaluation commands above. Codespaces settings and secrets do not propagate to IBM Code Engine.

## Full Avery environment — staged gate checklist

Do not proceed to the next stage until the checkpoint is satisfied and the evidence recorded.

| Gate | Required setup | Observable acceptance evidence | Status in this audit |
|---|---|---|---|
| A. Local MCP | Python 3.12, `uv` locked dependencies, synthetic fixtures | Exact tools, expected/denied case responses, local tests | **BLOCKED** by unavailable runtime |
| B. Remote MCP | Docker or deployed server, bearer credential, trusted host/identity claims | Health + authenticated discovery **and** expected scope denial without caller authorization | **NOT RUN** |
| C. Supabase | Dedicated synthetic database, reviewed migrations, restricted backend role, fixtures | Safe readback of known case, role/permissions, persisted state; negative unauthorized-access test | **NOT RUN** |
| D. VA sandbox | API-specific approved credentials and documented read scopes | Facility and (where authorized) other API-specific reads, correct denial cases; no production VA writes | **NOT RUN** |
| E. IBM hosting | Code Engine project, container revision, secret references | Running backend image digest and health + correlated MCP trace | **NOT RUN** |
| F. IBM agent | Orchestrate environment, correct agent, authorized toolkit attachment | Agent-selected tool invocation **correlated with backend evidence** | **NOT RUN** |
| G. Voice | LiveKit project, registered worker, Deepgram key, matching frontend session | Real two-way audio, matching session/worker IDs and transcript/call traces with protected data handling | **NOT RUN** |
| H. End-to-end booking | Proper synthetic case, trusted identity, consent, approval, fresh slot | Approved simulated booking with persisted receipt, CRM note, confirmation letter; rejected unauthorized/stale case | **NOT RUN** |

!!! warning "What is not acceptable as proof"
    `HTTP 200` on `/health`, a browser loading, an agent simply stating that an appointment was booked, or an MCP bearer key by itself **cannot** certify a complete scheduling lifecycle. Never disable identity/approval checks merely to make a test pass.

## Cloud setup requirements for a truly independent test

The new reviewer needs **their own** IBM Cloud account or authorized team instance, watsonx Orchestrate entitlement and permissions, Code Engine project and image-pull credentials, an approved Supabase synthetic environment, a LiveKit project, a Deepgram API key, and API-specific VA sandbox credentials **only when testing those respective features**. The local MCP fixture path needs none of those. Third-party services may entail costs, entitlements or workplace restrictions; confirm approval before provisioning.

### Capture the environment and failure without exposing secrets

For each checkpoint, record: test date, reviewer, source repository and SHA, OS and shell, Python/uv versions, service environment labels (not credentials), image digests/revisions, exact command **without secrets**, sanitized stdout/stderr, expected outcome, observed outcome, pass/blocked/fail, and linked evidence location.

Record the outcomes of your independent run. A blocker is **not** a fail and must not be converted into a pass.

## What must happen before claiming reproducibility

1. Run every local command in a fresh, supported VS Code environment (or optionally Codespaces), then record test outputs.
2. Have a reviewer with suitable approved service access carry out gates B–H in a **fresh** synthetic environment, following actual schema migrations and authorized deployment configurations. Never reuse original team's credentials, hostnames, resource identifiers or consumed test cases.
3. Reconcile failures by updating the specific installation page and rerunning the failed checkpoint; preserve an evidence trail and document unresolved prerequisites.
4. Run `python -m mkdocs build --strict` from a development environment with MkDocs dependencies installed, then visually inspect the published navigation, callouts and links before claiming the documentation build passed.

[Return to Developer Guide](index.md) · [Troubleshooting](troubleshooting.md) · [Release checklist](release-checklist.md)
