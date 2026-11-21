# Engineering decisions: why the project uses these services

[System architecture](../solution-architecture.md) | [Security and authorization](../security-governance.md)

This section explains **why** Veteran Access Bridge uses its current technologies. It documents project requirements and tradeoffs rather than claiming that every alternative was formally benchmarked. For implementation commands, follow the linked setup guides.

!!! info "What is an architecture decision record?"
    A decision record explains the problem, selected approach, consequences, and what would cause the team to reconsider it. It is not a certification of production readiness.

## ADR-001 · A governed MCP layer for scheduling

**Problem.** Avery needs to retrieve scheduling evidence and prepare actions without allowing a language model to bypass clinical, identity, consent, or booking restrictions.

**Decision.** Expose documented capabilities through MCP tools while enforcing permissions and state transitions in deterministic backend services.

**Consequences.** Agent tool attachment and MCP discovery are separate checks; successful transport authentication does not authorize a case read or booking. We must test denials as well as successful requests.

!!! warning "MCP is not a booking authorization mechanism"
    Never equate a successful tool call or a case ID supplied by an agent with trusted patient identity, valid approval, or an actual appointment.

[Explore the MCP implementation](../mcp-implementation.md) · [Run a local request](local-mcp-server.md)

## ADR-002 · Supabase PostgreSQL for synthetic operational data

**Problem.** The prototype did not have VA Corporate Data Warehouse access or production appointment-writer access. It still needed persistent, relational scheduling cases, appointment slots, decisions, CRM interactions and receipts.

**Decision.** Use a controllable **synthetic operational analog** built on Supabase PostgreSQL; keep scheduling authorization in application services. Supabase is not a replica of VA CDW or a VA scheduling system.

**Why it fits.** PostgreSQL supports relational integrity, transactional state, role-scoped database access and auditable test records. Optional `pgvector` can support knowledge retrieval, but document retrieval cannot authorize scheduling.

**Alternatives and tradeoffs.** Repository JSON fixtures are simpler and remain appropriate for the local MCP tutorial, but do not by themselves demonstrate a durable multi-request lifecycle. A self-managed PostgreSQL deployment is possible, with additional operational responsibility. A direct VA database or appointment-writer connection was not available for this prototype. These are architectural tradeoffs, **not a claim of measured vendor superiority**.

**Reconsider when.** Approved VA interfaces, hosting requirements, governance constraints or operational needs change.

!!! warning "Synthetic, not production"
    Do not place real Veteran records, production VA credentials, or unapproved PHI in the Supabase demo environment.

[Configure Supabase](supabase.md) · [Read database setup source](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/db)

## ADR-003 · IBM watsonx Orchestrate and Code Engine

**Problem.** The system needs an agent workspace attached to governed tools and a deployment target for the backend and voice worker.

**Decision.** Use watsonx Orchestrate for Avery's agent configuration/tool attachment and Code Engine for containerized service hosting.

**Tradeoff.** These choices introduce separate account permissions, CLI sessions, runtime credentials, regions and deployment revisions. An IBM Cloud login is **not** equivalent to Orchestrate environment activation.

[Start IBM setup](avery-ibm-start.md) · [Review hosted operations](ibm-orchestrate.md)

## ADR-004 · LiveKit and Deepgram for the voice path

**Problem.** A browser caller must have a real-time audio session with Avery, including speech recognition and spoken responses.

**Decision.** Use LiveKit for real-time session/worker transport and Deepgram for speech services. The browser, voice worker, backend and agent each have distinct runtime responsibilities.

**Consequence.** A web page loading is not proof of two-way voice, and a successful audio connection is not proof of a trusted MCP tool call or booking.

[Connected voice components](connected-product.md)

## ADR-005 · VS Code first; Codespaces optional

**Problem.** Contributors need to run the same repository in different development environments, including workplaces where VS Code is already available.

**Decision.** Recommend local VS Code, with Codespaces as an optional browser-hosted alternative. Both environments run the same MCP code and test data. Neither is a required part of the deployed architecture.

**Consequence.** Keep environment bootstrap instructions separate, then converge on one shared MCP walkthrough. Check organization policy before installing tools or using external cloud services.

[VS Code](vs-code.md) · [Codespaces](codespaces.md)

## ADR-006 · Human- and policy-gated simulated booking

**Problem.** Availability is not the same as authorization or an actual booked appointment.

**Decision.** Require the trusted workflow's identity, scope, consent, slot freshness, and approval/evidence checks before supported synthetic booking actions. Do not allow model instructions to override these checks.

!!! tip "Evaluate denied requests, too"
    A correctly denied booking can indicate that the safety boundary worked. Evaluate the reason and evidence rather than recording every refusal as a software failure.

[Connected product](connected-product.md) · [Security and governance](../security-governance.md)
