# Troubleshooting and validation checkpoints

Use a **single failed checkpoint** to narrow your investigation. Preserve a sanitized error message, commit SHA, execution environment, and backend/worker revision. Do not copy secrets into logs or issues.

!!! info "What counts as a successful setup?"
    Local MCP: tool discovery and deterministic fixture results. Full Avery: working audio **and** actual correlated agent-selected MCP activity, followed by an authorized synthetic lifecycle outcome. A loaded page or an HTTP health result alone is insufficient.

| Symptom | Likely boundary | First safe check | Success or next action |
|---|---|---|---|
| `uv` not found | Local tool installation/PATH | `uv --version` in the active VS Code terminal | Install through approved method; reopen shell |
| Python imports from another checkout | Editable package/environment | `git rev-parse HEAD`, inspect Python interpreter and installation | Run from intended checkout and `.venv` |
| Codespaces variable missing | GitHub secret injection | Check existence, not value | Confirm repository scope; restart Codespace |
| IBM Cloud login works, agent list fails | Different IBM authentication boundaries | `orchestrate env list`, active environment and permitted account | Activate correct environment or request access |
| MCP HTTP health works, tool returns 401 | MCP service authentication | Verify auth header and server-side secret references | Correct the authorized client configuration |
| MCP tool returns trusted-scope denial | Identity/case authorization, not necessarily outage | Check correlated trusted-host claims and scope | Resolve identity/permission; **do not bypass gate** |
| Supabase reachable, case absent | Schema, database, role, or fixtures | Read database identity and known synthetic record | Apply reviewed setup in a safe test DB |
| Browser loads, no voice | LiveKit/worker/media path | Check session, worker registration, mic permission, audio logs | Prove two-way audio independently |
| Voice works, no MCP event | Agent attachment/backend/tool flow | Correlate agent tool trace with backend activity | Verify active agent/toolkit/version and connection |
| Booking denied after voice success | Consent, identity, approval, slot freshness | Inspect safe decision code and approval evidence | Determine expected safety denial vs configuration failure |
| Old behavior after deployment | Backend/worker/frontend revision drift | Compare all deployed image digests and revisions | Redeploy only reviewed artifacts and retest |

??? info "Why do we test negative cases?"
    The system deliberately refuses some requests. Invalid credentials, stale slots, untrusted patient scope and missing approval should not silently succeed. Record both allowed and denied scenarios in acceptance evidence.

??? warning "Do not troubleshoot by disabling safeguards"
    Do not enable production booking, substitute real patients, weaken case scope, or bypass signed approval just to obtain a green demo. If a required gate cannot be met, stop at a documented simulation checkpoint.

## A minimum acceptance record

For each test, record: checkout commit, environment (VS Code/Codespaces/hosted), synthetic fixture version, active MCP tool inventory, relevant backend/worker/frontend revisions, action taken, observed outcome, sanitized trace/evidence, and whether the result was expected.

## Operational evidence to consult

- [Original project recovery runbook](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/submission/engineering-records/docs/operations/avery-m64-codespace-ibm-cli-relogin-deploy.md) — dated, environment-specific troubleshooting history; **not** a fresh-install script.
- [Evaluation evidence](../evaluation/reviewer-index.md) — measured scenarios and limitations.
- [Remote services](connected-product.md) — authenticated MCP and connected architecture.

!!! tip "Report the right failure"
    Distinguish **setup failure** (dependency/credential missing), **integration failure** (no correlated tool call), and **expected policy denial** (authorization or consent gate) before fixing code.
