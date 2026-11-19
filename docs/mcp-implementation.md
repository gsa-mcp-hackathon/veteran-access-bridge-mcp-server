# MCP Implementation

**The MCP server is the primary deliverable.** Python FastMCP provides discoverable contracts; thin wrappers call deterministic, independently testable services.

## Published configuration

[![Published MCP configuration: Avery, trusted voice host, MCP server and deterministic services](assets/mcp-implementation-overview.png)](assets/mcp-implementation-overview.png)

## Capability groups

<div class="feature-grid">
<div class="feature"><strong>VHA & patient information</strong><p>Scoped synthetic patient summary, clinical context, Community Care and facilities/sandbox read adapters.</p></div>
<div class="feature"><strong>Scheduling & access</strong><p>Canonical encounter, access standard, options, workflow state, selection, confirmation and governed booking requests.</p></div>
<div class="feature"><strong>Knowledge</strong><p>Call-bound retrieval. An answer may cite supporting material but cannot gain identity or scheduling authority from it.</p></div>
<div class="feature"><strong>CRM & follow-up</strong><p>Case reads, interaction records, tasks and lifecycle state, with restricted durable writes when configured.</p></div>
</div>

## Representative MCP contracts

??? note "View tool contracts"

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

