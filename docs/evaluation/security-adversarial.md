# Security, Prompt Injection & Adversarial Evaluation

**Purpose:** distinguish direct deterministic controls from adversarial agent behavior and still-open attack classes.

Synthetic identities and cases only. Security certification is **not** claimed.

## Attack design → trace → outcome

<div class="ev2-flow">
<div><b>1 · Scenarios</b><span>Cross-case access, forged scope or consent, prompt instructions, unauthorized booking</span></div>
<i>→</i>
<div><b>2 · Evidence</b><span>Tool attempt counts, scope denials, state diffs, paired authorized follow-up</span></div>
<i>→</i>
<div><b>3 · Decision</b><span>Pass where the exact oracle holds; incomplete where before/after or run linkage is absent</span></div>
</div>

## Dated evaluations

| Family | Outcome | Recorded observation | What it does **not** prove |
|---|---|---|---|
| Protected-write, consent and CRM controls (Nov 19) | <span class="ev2-badge ok">135/135</span> | Deterministic checks passed; Phoenix grouped saved suites | Not 135 LLM prompt-injection trials |
| Hostile argument probes (Nov 16) | <span class="ev2-badge ok">76/76</span> | Bounded input probes | No comprehensive cross-MCP or poisoning claim |
| Scope and schema (Nov 16) | <span class="ev2-badge ok">261/261</span> | Overlapping local assertions | Not hosted multi-actor isolation |
| Adversarial voice sample (Nov 15) | <span class="ev2-badge warn">sample</span> | Five restricted requests had zero observed MCP attempts; three permitted follow-ups succeeded | Small selected sample; no paired before/after SQL assertions for the five turns |
| Voice and database reconciliation (Nov 19) | <span class="ev2-badge warn">gap</span> | Zero of three Nov 15 sessions matched the retained Nov 16 SQL audit | Different session windows cannot show that no protected record changed |

## Prompt injection vs. enforced boundary

An attacker-controlled document or voice prompt may try to override instructions or access another caller's case. Our **backend** must still deny missing scope, invalid authority, wrong caller, unconfirmed booking, and unauthorized writes, regardless of what the model says or attempts.

Prompts and tool results are not identity assertions. A logged refusal is evidence of observed behavior in one trial, **not** a general immunity claim.

## Unfinished security evidence

!!! danger "Open"
    - Paired pre-/post-state snapshots bound to **the same call and case** for cross-case mutation checks.
    - Concurrent independently authenticated session isolation.
    - Linked operator alert and acknowledgment evidence where a policy expects an alert.
    - Broad tool-result prompt injection, poisoning, SSRF and cross-MCP scenarios.
    - Hosted database races, uncertain-write recovery and remaining dependency triage.

## Original artifacts

- [November 19 judge review and reconciliation](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/README.md)
- [Individual local security checks](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f0cb216d5cc78601fdc85c40d37394e085/docs/evaluation/judge-review/control-results.csv)
- [Historical voice security evidence](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/release-closeout-20261115.md)
- [Security follow-up](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/security-followup-20261115.md)
- [Adversarial MCP scope tests](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/tests/test_mcp_scope_adversarial.py)

**See also:** [Security & Governance](../security-governance.md) · [Validation & agent evidence](validation-agent.md)
