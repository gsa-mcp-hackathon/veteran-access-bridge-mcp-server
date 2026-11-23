# 01 · Problem and solution

**Use case:** Veteran Access Bridge is a secured MCP server that gives any SI agent 29 validated tools to look up VA health summaries, search open slots and book appointments for Veterans. The IBM watsonx Orchestrate voice agent Avery uses those tools to complete a booking on a single call.

**Track:** Service: Write. The server's core job is completing actions safely: 10 of its 29 tools change records (selecting and booking a slot, recording Veteran confirmations, preparing scheduling handoffs and writing CRM notes and follow-ups), and each write is checked by trusted backend services for identity, case scope, eligibility, consent and booking authority before it is committed.

**Problem:** Scheduling a VA appointment by phone often means long holds and several handoffs. An SI agent can shorten that, but only if it can never act beyond what the caller is allowed to do.

**Solution:** MCP separates Avery's conversational tool requests from deterministic services that enforce those rules. The agent chooses a tool; only the server decides whether the action is allowed.

[Solution overview](../../docs/index.md) · [Architecture](../../docs/solution-architecture.md) · [MCP implementation](../../docs/mcp-implementation.md)

**Scope:** All data is synthetic. No production VA bookings and no operational time-savings claim.
