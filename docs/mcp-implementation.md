# MCP Implementation

**The MCP server is the primary deliverable.** Python FastMCP provides discoverable contracts; thin wrappers call deterministic, independently testable services.

## Interactive overview

<iframe class="mcp-interactive" src="../assets/mcp-implementation-interactive.html" title="Interactive MCP implementation overview" loading="lazy"></iframe>

[Open the interactive overview full-size](assets/mcp-implementation-interactive.html){ target=_blank }

## What is registered?

| Configuration | Tool count | Scope |
|---|---:|---|
| Baseline local MCP | **21** | Core read and scheduling contracts |
| CRM enabled | **25** | Baseline + four scoped CRM tools |
| CRM and agent-scheduling enabled | **29** | Adds four trusted-voice scheduling/knowledge tools |
| Avery, Nov 18 reviewed configuration | **21 attached** | Subset attached to IBM agent, **not** entire server registry |

**These are configuration/inventory observations, not a 29/29 execution pass rate.** [Pinned registration source](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/src/veteran_access_bridge/mcp/tools/__init__.py).

## Capability groups

<div class="feature-grid">
<div class="feature"><strong>VHA & patient information</strong><p>Scoped synthetic patient summary, clinical context, Community Care and facilities/sandbox read adapters.</p></div>
<div class="feature"><strong>Scheduling & access</strong><p>Canonical encounter, access standard, options, workflow state, selection, confirmation and governed booking requests.</p></div>
<div class="feature"><strong>Knowledge</strong><p>Call-bound retrieval. An answer may cite supporting material but cannot gain identity or scheduling authority from it.</p></div>
<div class="feature"><strong>CRM & follow-up</strong><p>Case reads, interaction records, tasks and lifecycle state, with restricted durable writes when configured.</p></div>
</div>

## Representative MCP contracts

| Tool | Core input | Behavior / limitation |
|---|---|---|
| `get_scheduling_encounter` | `case_id` | Canonical read-only evidence; no booking |
| `assess_access_standard` | `case_id` | Deterministic wait comparator; does not authorize Community Care |
| `search_availability` | `case_id` | Normalize available options; does not create handoff |
| `search_call_appointments` | `case_id`, date/time preferences | Call-scoped options, without booking |
| `select_call_appointment` | `case_id`, `option_id` | Select for host readback, not consent |
| `book_call_appointment` | `case_id` | Booking **request**; separate verified current confirmation/policy checks |
| `search_call_knowledge` | `case_id`, `query` | Grounded retrieval, no privilege elevation |

[Full enabled 29-tool source catalog](https://github.com/wbgreen0405/veteran-access-bridge/tree/5b6cd072f23b4d4edce2e19c4f75faa774c87988/src/veteran_access_bridge/mcp/tools) · [Versioned inventory](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/guidelines-and-tool-inventory-20261118.md).

## A safe MCP tool call

```json
{"name":"get_scheduling_encounter","arguments":{"case_id":"DEMO-CARD-5000335-001"}}
```

Expected **selected assertions**, not a fabricated full server response:

```json
{"synthetic":true,"read_only":true,"workflow_state":"READY_TO_SEARCH","booking_created":false,"community_care_authorization_granted":false,"eps_invoked":false}
```

For a negative case, call with `UNKNOWN-CASE` and require explicit denial rather than an invented patient or option.

## Transport and execution

- **Local:** `veteran-access-mcp` starts an MCP **stdio** process for a client; it does not host a browser UI.
- **Hosted:** `veteran-access-demo` serves authenticated streamable HTTP on `/mcp`, with additional trusted session/host configuration.
- **Boundary:** MCP client tool arguments are untrusted; the server checks service authentication, scope and applicable service permissions independently of agent text.
- **State changes:** Durable CRM/appointment writes require the backend policy, idempotency and confirmation lifecycle.

The tool interface is intentionally thin. The deterministic [services source](https://github.com/wbgreen0405/veteran-access-bridge/tree/5b6cd072f23b4d4edce2e19c4f75faa774c87988/src/veteran_access_bridge/services) and [scope tests](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/tests/test_mcp_scope_adversarial.py) carry the consequential behavior.

**Next:** [Security & Governance](security-governance.md) · [Developer Guide](developer-guide.md)
