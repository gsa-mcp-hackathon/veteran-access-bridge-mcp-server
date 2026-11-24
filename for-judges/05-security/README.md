# 05 · Security and adversarial assessment

**Security:** The SI can choose a tool, but only the server decides what is allowed. Every request passes four layers of protection, and any failed check returns a structured denial with no data and no change. Local and CI controls all passed; four deployed scenarios remain PARTIAL until IBM runtime evidence is produced.

[Detailed evaluation](../../docs/evaluation/security-adversarial.md) · [Interactive security architecture](../../docs/security-governance.md) · [Sanitized closeout](evidence/m64-security-closeout-summary.md)

## Four layers of protection

![Security: four layers of protection with their recorded evidence; all checks pass leads to a committed write with a receipt, any failure leads to a structured denial; test A27 shows the server refusing a forged request](../assets/security-layers.png)

The 86/86 and 18/18 results are from Nov 21 (local, all 29 tools) and Nov 23 (deployed server); 5/5 voice attacks and 18/18 RLS tables from Nov 15; 135/135 from Nov 19. Scope checks also passed 261/261 locally on Nov 16.

## Threats and how each is stopped

| Threat | How it is stopped |
|---|---|
| Caller claims to be someone else | Identity is verified by the trusted voice host, not by what the caller or model says |
| Agent asks for another Veteran's case | Case binding and scope checks deny it whatever case ID is supplied |
| Prompt injection in speech, documents or tool results | Prompts and tool results are never treated as identity or authority; protected actions still require trusted checks |
| Forged authority on a write tool | All 10 write tools refused forged authority (Nov 21) |
| Booking without consent | Booking requires a separate, current confirmation captured by the trusted host and a signed, session-bound grant |
| Model claims a booking that doesn't exist | Success is reported only after independent database readback |
| Replayed or duplicated writes | Idempotency keys and replay denial |
| Exposure of real health data | Synthetic patient and scheduling data only; credentials and service keys stay server-side |

## Still being proven on the live system

The fixes for these findings passed **27/27 local checks (Nov 22)**, and the catalog verifier passed **48/48**. Deployed acceptance needs IBM runtime evidence that has not been produced yet, so all four remain **PARTIAL**.

| Scenario | What passed | What deployed acceptance still needs |
|---|---|---|
| **S13/A23** · ignores instructions hidden in CRM data | Paired synthetic results reached a local MCP client | A write-isolated IBM Avery replay with side-effect evidence |
| **S14** · tool list can't be silently changed | Verifier rejects unauthorized description, metadata and scope drift (48/48) | An approved immutable manifest and IBM pre-dispatch enforcement |
| **S15** · connects only to approved servers | Local endpoint-binding drift is rejected | Managed IBM outbound destination and credential-forwarding telemetry |
| **S03/A21** · one caller can't see another's case | Caller isolation passed locally | A live test with two authorized, overlapping, independently verified callers |

No unauthorized deployed execution, disclosure or credential forwarding was found. Missing managed telemetry is a gap in evidence, not evidence of a breach.

## Known limitations and next steps

| Priority | Work |
|---|---|
| **01 · Close security gaps** | Tool-result injection, tool poisoning, cross-MCP, outbound adapter tests and dependency risk triage |
| **02 · Harden write recovery** | Concurrent restricted Supabase writes, lost-acknowledgement recovery, durable pending-CRM reconciliation |
| **03 · Expand evaluation** | Repeated IBM Evaluate and DeepEval variants, held-out prompts, independently verified tool side effects |
| **04 · Advance VHA integration** | Approved VA source contracts for specialty care, Community Care, secure messaging and knowledge retrieval |

Production VA access and appointment writes remain disabled. There is no centralized OAuth2 identity provider, gateway, WAF or SIEM in front of the MCP server.

## Publication safeguards

This package contains only synthetic data and sanitized summaries. Before publication, an expired IBM token and IBM instance identifiers were redacted from copied evaluation outputs, and IBM account and instance IDs in the browser app were replaced with placeholders. No passwords, live tokens, patient details or identity factors are published.

**No security certification is claimed.**

**Sources:** [Remediation report (27/27)](../engineering-records/docs/evaluation/m64-security-remediation-20261122.md) · [PR #215 record](../engineering-records/pr-215.md) · [48-check CI run](../engineering-records/ci/ci-run-45101968969.md) · [Nov 19 control results](../engineering-records/docs/evaluation/judge-review/control-results.csv) · [Adversarial scope tests](../../tests/test_mcp_scope_adversarial.py)

**Next:** [06 · Reproducibility →](../06-reproducibility/README.md)
