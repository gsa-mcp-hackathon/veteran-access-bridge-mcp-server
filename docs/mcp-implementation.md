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


## Explore the registered MCP tools

The searchable catalog below is a **static snapshot of the reviewed November 18, 2026 configuration**, linked to the repository's actual Python tool sources. The server exposes **29 registered tools when the optional CRM and agent-scheduling groups are enabled**; **21 were attached to Avery** in that reviewed configuration. Eight restricted handoff/control-path tools were intentionally **not attached**. Registration or attachment is not evidence of a live invocation or permission to access a case.

<link rel="stylesheet" href="../stylesheets/mcp-tool-explorer.css">

<div class="vab-tool-explorer" id="vab-tool-explorer">
  <div class="vab-tool-summary"><strong>29 registered · optional groups enabled</strong><strong>21 attached to Avery</strong><strong>8 not attached to Avery</strong></div>
  <div class="vab-tool-controls">
    <label>Search tools<input id="vab-tool-search" type="search" placeholder="Search name, category, or purpose" autocomplete="off"></label>
    <label>Capability<select id="vab-tool-category"><option value="all">All capabilities</option></select></label>
    <label>Avery attachment<select id="vab-tool-attachment"><option value="all">All tools</option><option value="attached">Attached to Avery</option><option value="excluded">Not attached</option></select></label>
  </div>
  <p id="vab-tool-count" role="status">29 registered tools in the reviewed configuration</p>
  <div id="vab-tool-list" class="vab-tool-list"><p>Loading the local tool catalog…</p></div>
  <noscript><p>JavaScript is needed for the catalog filters. The <a href="https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/src/veteran_access_bridge/mcp/tools">registered tool source directory</a> and the <a href="https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/release/evidence/guidelines-and-tool-inventory-20261118.md">versioned attachment reconciliation</a> are available without JavaScript.</p></noscript>
</div>

<script src="../assets/mcp-tool-explorer.js" defer></script>

**Tool access is governed.** The model cannot supply its own trusted identity, consent, scope, or booking authorization. Review [Security & Governance](security-governance.md) for the trust boundaries and [the inventory record](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/release/evidence/guidelines-and-tool-inventory-20261118.md) for the historical server/agent counts.

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

