# 05 · Security and adversarial assessment

[Detailed evaluation](../../docs/evaluation/security-adversarial.md) · [Interactive security architecture](../../docs/security-governance.md) · [Sanitized final closeout](evidence/m64-security-closeout-summary.md)

**Core rule:** Avery can select an MCP tool. The trusted voice host and deterministic backend independently decide whether the call has authority to perform the action. Security does not depend on the model behaving well.

## Controls by layer, with recorded evidence

| Layer | Control | Recorded evidence |
|---|---|---|
| MCP transport | Service bearer authentication on remote MCP calls; missing or wrong credentials denied | 3/3 HTTP 401 denials |
| Session and case scope | Opaque short-lived turn capabilities, case binding, per-session tool allowlists, replay denial | 261/261 local scope and schema checks (Nov 16) |
| Tool arguments | Untrusted arguments cannot override policy, inject queries or reach files and URLs | 86/86 hostile-argument checks on all 29 tools (Nov 21) |
| Policy and booking authority | Verified identity, explicit current consent, fresh option and a signed host grant required before a booking | 135/135 protected-write, consent and CRM controls (Nov 19) |
| Writes | Idempotent commits; forged or replayed writes rejected; persistence verified before success is reported | Local regression passed; hosted fault tests open |
| Database | Row-level security on synthetic appointment, consent, audit and CRM tables | 18/18 audited tables with RLS |
| Voice | Restricted requests made by voice | 5 restricted requests produced no MCP attempts; 3 permitted follow-ups succeeded (Nov 15 sample) |
| Tool catalog | Verifier rejects unauthorized description, metadata and scope-classification drift | 48/48 focused local and CI checks (Nov 22) |
| Reviewer login | Secure cookie, expiry, logout revocation, bounded requests, login attempt limits | Protects the frontend only, not Veteran identity |

## Threats considered

| Threat | How it is stopped |
|---|---|
| Caller claims to be someone else | Identity is verified by the trusted voice host, not by what the caller or model says |
| Agent asks for another Veteran's case | Case binding and scope checks deny it regardless of the case ID supplied |
| Prompt injection in speech, documents or tool results | Prompts and tool results are never treated as identity or authority; protected actions still require trusted checks |
| Forged authority on a write tool | Write tools require trusted host context; all 10 denied forged authority in the Nov 21 probes |
| Booking without consent | Booking requires a separate, current confirmation captured by the trusted host |
| Model claims a booking that doesn't exist | Success is reported only after independent database readback |
| Replayed or duplicated writes | Idempotency and replay denial |

## Final security closeout (Nov 22–23)

Four deployed scenarios remain **PARTIAL**: the local controls passed, but the deployed IBM runtime evidence needed to close them was not produced.

| Scenario | What passed locally | What is still needed for deployed acceptance |
|---|---|---|
| **S14** · tool description drift | Verifier rejects unauthorized descriptions, metadata and scope drift (48/48) | An approved immutable manifest and IBM pre-dispatch enforcement |
| **S13/A23** · malicious CRM note | Paired synthetic results reached a local MCP client | A write-isolated IBM Avery replay with side-effect evidence |
| **S15** · endpoint redirection | Local endpoint binding drift is rejected | Managed IBM outbound destination, connection and credential-forwarding telemetry |
| **S03/A21** · concurrent callers | Caller isolation passed locally; corrected fixture check found no unused eligible callers to run the live test | Two authorized, overlapping, independently verified caller sessions |

No unauthorized deployed execution, disclosure or credential forwarding was found. Missing managed telemetry is a gap in evidence, not evidence of a breach.

## Open items

- Paired before-and-after database snapshots tied to the same call and case for cross-case mutation checks
- Concurrent, independently authenticated session isolation in the deployed environment
- Broad tool-result prompt injection, poisoning, SSRF and cross-MCP scenarios
- Hosted database races and uncertain-write recovery
- No centralized OAuth2 identity provider, gateway, WAF or SIEM in front of the MCP server

## Publication safeguards

This public package contains only synthetic data and sanitized summaries. Before publication, an expired IBM token and IBM instance identifiers were redacted from copied evaluation outputs, and IBM account and instance IDs in the browser app were replaced with placeholders. No passwords, live tokens, patient details or identity factors are published.

**No security certification is claimed.**

**Sources:** [Security remediation report (27/27)](../engineering-records/docs/evaluation/m64-security-remediation-20261122.md) · [PR #215 record](../engineering-records/pr-215.md) · [48-check CI run](../engineering-records/ci/ci-run-45101968969.md) · [Nov 19 control results](../engineering-records/docs/evaluation/judge-review/control-results.csv) · [Adversarial scope tests](../../tests/test_mcp_scope_adversarial.py)
