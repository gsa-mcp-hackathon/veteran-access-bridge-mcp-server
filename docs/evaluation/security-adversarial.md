# Security, Prompt Injection & Adversarial Evaluation

**Purpose:** distinguish direct deterministic controls from adversarial agent behavior and still-open attack classes.

<div class="ev-meta"><span>Data: synthetic identities and cases</span><span>Controls: Python and MCP negative probes</span><span>Voice: bounded recorded attack turns</span><span>Security certification: not claimed</span></div>

## Attack design → trace → outcome

<div class="eval-three"><div><b>01 · Scenarios</b><p>Cross-case access, forged scope/consent, prompt instructions, unauthorized booking</p></div><div><b>02 · Evidence</b><p>Tool attempt counts, scope denials, state diffs, paired authorized follow-up</p></div><div><b>03 · Decision</b><p>Pass where exact oracle holds; incomplete where before/after or run linkage is absent</p></div></div>

## Dated evaluations

| Family | Recorded observation | What it does **not** prove |
|---|---|---|
| Local protected-write/consent/CRM controls, November 19 | **135/135** deterministic checks passed; Phoenix grouped saved suites | Not 135 LLM prompt-injection trials |
| November 16 hostile argument probes | **76/76** | No comprehensive cross-MCP/poisoning claim |
| November 16 scope & schema | **261/261**; overlapping local assertions | Not hosted multi-actor isolation |
| November 15 adversarial voice sample | Five restricted requests had zero observed MCP attempts; three permitted follow-up sessions succeeded | Small selected sample; no independent paired before/after SQL assertions for the five turns |
| Voice/database reconciliation November 19 | Zero of three Nov 15 sessions matched the retained Nov 16 SQL audit | Different session windows cannot establish that no protected record changed |

## Prompt injection vs. enforced boundary

An attacker-controlled document or voice prompt may try to override instructions or access another caller's case. Our **backend** must still deny missing scope, invalid authority, wrong caller, unconfirmed booking, and unauthorized writes, regardless of what the model says or attempts.

Prompts and tool results are not identity assertions. A logged refusal is evidence of observed behavior in one trial, **not** a general immunity claim.

## Unfinished security evidence

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

**Next:** [End-to-End & Final Review](final-review.md)
