# Security evaluation execution - November 14, 2026

Status: partial measured evidence; expanded 48-scenario evaluation remains in progress.

## Measured results

- **207 passed, 0 failed, 0 skipped** in the focused existing security regression selection (18.99 seconds, Windows Python 3.12). Source: `253fabb`.
- **3/3 deployed authentication denial checks passed**: missing credential, wrong bearer credential, and wrong authentication scheme each returned HTTP 401 at the existing canary's `/mcp/` endpoint.
- Initial `/mcp` probes returned a same-origin 307 redirect. Those requests were inconclusive authentication checks, not security failures; they were repeated at the observed canonical path. No authenticated tool invocation or booking was attempted.
- One Authlib deprecation warning remains. No deployment, credential rotation, agent change or live database write was performed by these checks.
- **53/53 bounded hostile-argument checks passed** on the existing in-process MCP server: four reference variants on 12 read tools (48 checks) plus forged authority fields on five mutating tools. Reference variants were instruction-like text, SQL-like text, a nonexistent file URI, and an example.invalid URL. All returned denial/unavailability without observed fixture-store changes. This does not test real SQL injection, outbound-request enforcement, or an LLM's instruction handling.

## Regression scope

| Existing test module | Executed cases |
|---|---:|
| test_mcp_transport_guard | 9 |
| test_mcp_remote_integration | 2 |
| test_sprint_b_durable_mcp_routing | 15 |
| test_trusted_voice_worker | 1 |
| test_trusted_voice_booking | 37 |
| test_trusted_primary_care | 47 |
| test_synthetic_veteran_consent | 11 |
| test_private_va_booking_grant_issuer | 26 |
| test_private_primary_care_booking | 41 |
| test_pg_eps_recovery_atomic | 3 |
| test_pg_booking_commit_invariants | 15 |

These tests use the project's existing fixtures and stubs. In particular, SQL commit tests use in-memory cursor stubs and execute no real SQL. Passing them does not establish live transactional concurrency or end-to-end database acceptance. No additional mock server was introduced.

## Mapping to expanded security design

| Challenges | Evidence now available | Remaining limitation |
|---|---|---|
| S01-S02: MCP credential denial | Deployed HTTP 401 for all three credential variants | Does not prove user/case authorization after authentication |
| S03: cross-scope access | Existing wrong-case and recovery-scope regression passes | Complete deployed cross-user read/handle matrix not run |
| S04-S06: signatures, claims, call binding | Forged assertion, mismatched/expired claims, wrong worker key and participant-reconnect regressions pass | Full deployed variant matrix not run |
| S07-S09: consent and authority | Ambiguous/declined/stale consent and policy denial regressions pass | Current IBM adversarial narrative tests pending |
| S10: replay | Replayed assertion and immutable receipt recovery regressions pass | Live database replay lane pending |
| S11: concurrent commit | Offline invariant evidence only | Real isolated database contention test NOT RUN |
| S12: ambiguous write recovery | Existing recovery and no-resubmit regressions pass | Network-fault injection against isolated persistent store pending |
| S13-S15: injection and tool trust | No new execution evidence | NOT RUN |
| S16: untrusted inputs | 53 hostile-argument probes plus earlier schema probes provide partial evidence | Size limits and all valid privileged-field permutations not established |
| S17-S18: outbound/parser attacks | URI strings used as references were denied, but outbound adapters were not exercised | SSRF and trace-parser challenge execution NOT RUN |
| S19-S23: secrets, browser, audit, revocation, drift | No complete challenge evidence in this run | NOT RUN; retain dependency findings and attribution gaps |
| S24: receipt integrity | Missing/conflicting readback and recovery regressions pass | Independent live persistence acceptance not rerun |

Do not report this table as 24/24 passed, or the regression count as 207 adversarial attacks. It combines existing unit/integration regressions with three narrow deployed checks. The benchmark still needs actual agent traces, broader attack coverage and independently verified write outcomes.

Raw local evidence: `eval/results/20261114-security/security.xml`, `test-output.txt`, and `deployed-auth-canonical.json`. Public summaries must not include credentials or unredacted logs.

## IBM execution prerequisite

The user privately refreshed the Orchestrate session. Six IBM evaluations completed from isolated checkout `/workspaces/vab-eval-20261114` at `9bd0b39`. See [IBM smoke results](IBM-SMOKE-20261114.md). The original Codespace checkouts were left intact. These are current-date observations of the configured agent and canary; the deployed image digest was not independently reverified in this run.

Six first-stage IBM smoke inputs are prepared under `eval/watsonx/current_release_smoke`: A01, A02, A03, A11, A19, A22. They are not the complete 24-journey suite. A02/A03/A11 retain fixture-bound historical setup and require preflight; A19/A22 introduce refusal challenges. Do not interpret semantic matching alone as evidence of no tool execution or no side effects.
