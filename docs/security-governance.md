# Security & Governance

**The LLM is not the security boundary.** Avery selects tools and coordinates a conversation. Independent trusted services determine whether information may be disclosed and whether a synthetic appointment may be committed.

<div class="sec-kpi"><div><b>Identity</b><span>Verified host + case scope</span></div><div><b>Consent</b><span>Current caller confirmation</span></div><div><b>Policy</b><span>Deterministic authorization</span></div><div><b>Receipt</b><span>Verified persisted outcome</span></div></div>

## 01 · The protected request path

<div class="sec-flow" aria-label="Protected MCP request path">
 <div class="sec-flow-node"><strong>SI Agent</strong><span>Avery selects a tool, but cannot issue its own authority</span></div>
 <div class="sec-flow-arrow">→</div>
 <div class="sec-flow-node"><strong>MCP Boundary</strong><span>Authenticate, validate tool arguments, enforce trusted case scope</span></div>
 <div class="sec-flow-arrow">→</div>
 <div class="sec-flow-node focal"><strong>Deterministic Services</strong><span>Confirm current identity, consent, slot and policy</span></div>
 <div class="sec-flow-arrow">→</div>
 <div class="sec-flow-node"><strong>Decision</strong><span>Scoped read · Denial / review · Idempotent synthetic commit + receipt</span></div>
</div>

!!! info "A booking request is not a booking authorization"
    **Selection ≠ confirmation ≠ persisted booking.** A valid MCP bearer token or a UI login is not scheduling authority. Routine internal synthetic Primary Care may use a separately trusted service-policy grant after confirmation; other workflows may require staff/Community Care review.

## 02 · Defense by control layer

| Enforcement layer | What it checks | Evidence |
|---|---|---|
| Service authentication | Authenticated remote MCP access; missing or invalid service credentials denied | [Scope/session service](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/src/veteran_access_bridge/mcp/session_scope.py) |
| Trusted caller and case | Identity and call/participant/case binding, expired/mismatched claims denied | [Trusted Primary Care checks](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/control-results.csv) |
| Current consent | Verified confirmation from the active call; cannot be inferred from tool text | [Consent suite](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/primary-care-control-suites.csv) |
| Eligibility and authority | Wait-standard logic, patient classification, slot freshness and service-policy gates | [Booking service](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/src/veteran_access_bridge/services/booking.py) |
| Persistence & CRM | Restricted data roles, replay guards, idempotency, receipt validation and case-bound writes | [Booking/CRM suites](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/control-results.csv) |
| Untrusted text | KB content/tool results cannot grant patient scope, signing keys or booking authority | [Adversarial evaluation](evaluation/security-adversarial.md) |

## 03 · Security evaluation: observed results vs. risk

<div class="sec-split"><section><div class="sec-eyebrow">DETERMINISTIC CONTROLS · NOV 19</div><strong>135 / 135</strong><p>Local checks passed across six suites, including trusted session assertions, consent, protected bookings, CRM receipts and case isolation. Phoenix organized the saved results.</p><a href="evaluation/method-gold/#phoenix-grouped-control-checks">Inspect Phoenix control suites →</a></section><section><div class="sec-eyebrow">ADVERSARIAL MCP INPUTS · NOV 16</div><strong>76 / 76</strong><p>Bounded hostile-argument probes. A separate 261/261 record covered overlapping schema/scope assertions. These are not live red-team penetration tests.</p><a href="evaluation/validation-agent/#mcp-server-validation">Inspect MCP probes →</a></section><section><div class="sec-eyebrow">VOICE DEFENSE · NOV 15</div><strong>5 turns</strong><p>Five restricted voice requests recorded zero observed MCP attempts; three permitted follow-ups succeeded. No contemporaneous paired DB snapshots were retained for the restricted requests.</p><a href="evaluation/security-adversarial/">Inspect voice tests and limitations →</a></section></div>

## 04 · How controls handle attacks

<details><summary><strong>Cross-case disclosure and forged scope</strong> — caller asks about another case</summary>

**Expected:** reject foreign-case reads and writes unless backed by the correct trusted caller/case context. **Observed:** bounded local session/case tests passed; the separate voice defense sample recorded zero MCP attempts for restricted prompts. **Gap:** the historical voice test lacks paired before/after SQL snapshots tied to its own sessions.

[Control-check artifacts](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/control-results.csv)
</details>

<details><summary><strong>Consent and unauthorized booking</strong> — model requests a protected write</summary>

**Expected:** require current, persisted call-bound consent, fresh option, applicable policy and a trusted host grant before a synthetic write. **Observed:** protected Primary Care and consent local suites passed; the recorded successful voice booking had a persisted receipt. **Gap:** hosted multi-writer concurrency and uncertain-write recovery are not universally covered.

[Individual booking checks](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/control-results.csv)
</details>

<details><summary><strong>Prompt injection and untrusted knowledge</strong> — source text attempts to confer authority</summary>

**Expected:** treat document/KB/tool-result instructions as untrusted data; no content can authorize identity or booking. **Observed:** authorization checks exist independently of model output. **Gap:** broad tool-result injection, cross-MCP poisoning and SSRF coverage is incomplete; do not mark these as passed.

[Adversarial scope tests](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/tests/test_mcp_scope_adversarial.py)
</details>

<details><summary><strong>Replay, CRM manipulation and confirmation fraud</strong></summary>

**Expected:** reject expired and replayed assertions, protect CRM receipt provenance, and avoid duplicate or conflicting writes. **Observed:** local protected booking, trusted host and CRM suites passed. **Gap:** process loss and hosted race conditions require separately correlated integration evidence.

[Suite summary](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/primary-care-control-suites.csv)
</details>

## 05 · Known limitations and required follow-up

**Not a production security certification.** The documentation covers synthetic records and selected tests. Remaining evaluation includes paired DB before/after snapshots for the same voice session, independently authenticated overlapping caller sessions, operator alert receipts where applicable, more injection/poisoning/SSRF cases, dependency remediation, and hosted concurrency.

<div class="sec-evidence"><strong>Security evidence index</strong><p><a href="evaluation/method-gold/#phoenix-grouped-control-checks">Gold + Phoenix grouped control results</a> · <a href="evaluation/security-adversarial/">Prompt-injection and voice adversarial record</a> · <a href="evaluation/validation-agent/#what-remains-open">End-to-end and remaining gates</a></p></div>

*Independent synthetic technical prototype. No live VA scheduling access, protected real-patient data, production authorization, or HIPAA/VA accreditation claimed.*
