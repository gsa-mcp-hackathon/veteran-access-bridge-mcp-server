# Solution & Architecture

**A governed MCP server for Veteran healthcare scheduling**

Veteran Access Bridge connects Avery, an SI voice agent orchestrated with IBM watsonx Orchestrate, to structured scheduling tools and trusted backend services. **The MCP server is the primary hackathon deliverable**; Avery demonstrates how an SI agent can use it in a synthetic Veteran healthcare call.

**SYSTEM ARCHITECTURE · CALLING SCENARIO**

![Veteran Access Bridge calling scenario MCP architecture](assets/architecture-calling-scenario.png)

*Original approved architecture diagram, reproduced without content edits.* [Open the full-size diagram](assets/architecture-calling-scenario.png).

!!! info "How to read this diagram"
    The illustration represents the original **21-tool calling-scenario inventory**, not the full later server configuration. The November 18, 2026 review separately recorded **29 tools** with CRM and voice features enabled and **21 MCP attachments** assigned to Avery. The diagram depicts synthetic CDW and sandbox/API boundaries; it does **not** represent production VA scheduling access.

## What the components do

| Layer | Role |
| --- | --- |
| **Avery + voice host** | Receives the caller request through the voice application. IBM watsonx Orchestrate selects appropriate MCP tools; the trusted voice host manages verified session and confirmation context. |
| **Veteran Access Bridge MCP Server** | Exposes typed tools, validates requests, enforces scope and returns structured evidence rather than model-generated scheduling facts. |
| **Deterministic services** | Evaluate eligibility, access standards, policy, slot freshness, confirmation and permissions independently of the model. |
| **External services and synthetic data** | Supply authorized sandbox reads, synthetic appointment inventory and persisted CRM/appointment evidence. |

## Why we designed it this way

**01 · Normalize before SI**  
The agent receives consistent case information, source provenance and eligible options rather than reconciling different source formats on its own.

**02 · Policy as code**  
Scheduling rules and Community Care review decisions are evaluated by deterministic services. An available slot or an access-standard exception never grants authorization by itself.

**03 · Authority outside the model**  
Identity, caller scope, current consent, booking prerequisites and applicable service policy are enforced independently. A model’s request does not commit an appointment.

**04 · Durable, auditable outcomes**  
A successful synthetic booking is confirmed by persisted records and an explicit receipt—not only by Avery saying that an appointment was booked.

## Evidence from a demonstrated call

On **November 16, 2026**, a controlled real-time call using generated caller speech exercised IBM-selected patient, knowledge, appointment-search, selection and booking tools. Independent database reads verified **one synthetic appointment**, **one host-written CRM note**, and the receipt **`BOOKED_SIMULATED`** for that historical execution. This demonstrates that tested path; it is not a claim of production VA booking or a rerun on later revisions.

[Review the recorded demonstration](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-agent-led-scheduling-20261116.md) · [Inspect the machine-readable proof](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/agent-led-voice-20261116.json)

**Explore further:** [MCP tool contracts](https://github.com/wbgreen0405/veteran-access-bridge/tree/5b6cd072f23b4d4edce2e19c4f75faa774c87988/src/veteran_access_bridge/mcp/tools) · [Backend services](https://github.com/wbgreen0405/veteran-access-bridge/tree/5b6cd072f23b4d4edce2e19c4f75faa774c87988/src/veteran_access_bridge/services) · [Security and scope tests](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/tests/test_mcp_scope_adversarial.py)

<small>Technical prototype using synthetic data. No production VA scheduling authority is claimed. Architecture image preserved from the supplied PowerPoint; inventory notes are dated November 18, 2026.</small>
