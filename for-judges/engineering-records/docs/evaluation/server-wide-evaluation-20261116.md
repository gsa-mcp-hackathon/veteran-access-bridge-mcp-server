# MCP server evaluation follow-up

November 16, 2026. **Local evaluation completed; live follow-up remains pending.**

## What we tested and how to explain it

| Question | Fresh result | Plain-language interpretation |
|---|---|---|
| Does every registered tool expose a usable contract and reject invalid requests? | 108/108 contract probes; 25 tools registered with CRM enabled | We checked metadata, missing inputs, wrong types, unknown references and restricted-write denials. This is not a successful workflow for every tool. |
| What happens when hostile text is supplied as a reference or forged authority? | 76/76 argument probes across all 25 tools | The tested inputs were denied or returned safe negative results without changing local fixture stores. No database, outbound adapter or LLM attack was exercised. |
| Can requests use missing, forged, expired, revoked or wrong-case permissions? | Included in 261/261 schema and scope assertions | Real registered wrappers were exercised with remote permission checks enabled over an in-process client. This was not a deployed HTTP authentication test. |
| Can two caller scopes be swapped, or the same permission be used simultaneously? | 26/26 assertions across 13 read/CRM tool names, included in the 261 | Shared-gate tests used an invocation sentinel. Swapped cases never invoked it; two simultaneous same-turn requests invoked it once. Database concurrency remains untested. |
| Does the existing regression suite still pass on this workstation? | 1,382 passed; 1 failed; 17 skipped | The failure invokes Linux-only private-key file flags on Windows. Retain it and verify on Linux; do not change key protection to satisfy Windows. |
| Does regression pass on the deployment platform? | Linux CI: 1,380 passed; 19 skipped | CI run 43911763399 passed on commit 50dcfe6, including lint, packaging and web build. No key-protection rule was changed. |

Do not add these counts into one overall pass rate. Several checks overlap, and
none is a statistical estimate of real caller success or attack resistance.

The [25-tool matrix](server-wide-tool-coverage-20261116.md) and its linked CSV
identify each tool separately. PASS applies only to the stated check. NOT TESTED
is not a pass. N/A requires an applicability reason. Positive business journeys
are deliberately marked NOT TESTED in this fresh run; earlier voice evidence is
separate, not silently carried forward as a rerun.

The first argument run passed 60 checks but omitted four non-case reference tools.
The harness was extended to cover handoff and facility references as well. The
76-check result supersedes that narrower run; both evidence files are retained.

## Environment and reproducibility

Application source: `bae3e9593ff60db19a986b52e2e61e4a67e06cea` on the existing CRM
branch. Test harness additions are included with this report. Local Python 3.12.9,
FastMCP 2.14.7, Windows. The real application registers the tools; no new mock MCP
server, listener, deployment or appointment was created. CRM is enabled only in
the evaluation process. VA source mode is explicitly `unavailable`.

The first regression collection stopped because an inherited `SSLKEYLOGFILE`
pointed at an inaccessible Windows device. Removing that environment variable
for the test process disables TLS key logging, not certificate verification.
Restricted-process runs subsequently stalled and were cancelled. The final local
runs completed outside that process restriction. Original collection errors are
retained in `evidence/server-wide-20261116/regression.xml`; completed regression
results are in `regression-final.xml`.

The failed test is
`test_synthetic_veteran_session.py::test_host_key_configuration_requires_matching_owner_only_private_key`.
Its failure is `AttributeError: os.O_NOFOLLOW` on Windows, before its intended
POSIX permission assertion. This is a local platform limitation, not proof that
the deployed Linux key check passes or fails. The subsequent
[Linux CI run](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/ci/ci-run-43911763399.md)
passed on commit `50dcfe6`; the original Windows failure is retained. This is
source/build validation, not a probe of the running container.

Run from the repository root in a clean development environment, using new output
paths to preserve previous results:

```bash
VAB_ENABLE_CRM=true python eval/probe_mcp_contracts.py --output-dir /tmp/vab-contract-run
VAB_ENABLE_CRM=true python eval/probe_mcp_adversarial.py --output-dir /tmp/vab-argument-run
python eval/probe_server_wide.py --output /tmp/vab-scope-run.json
python -m pytest -q --junitxml=/tmp/vab-regression.xml
```

`eval/summarize_server_wide.py` builds this dated matrix from the recorded local
artifacts. Raw capability values are never emitted by the new scope report.

## Reachability and remaining tests

| Area | What inspection establishes | Next acceptance step |
|---|---|---|
| Tool-result injection | Agent-readable scheduling, lifecycle and CRM text are relevant surfaces. A scope gate does not prove the model will ignore malicious text. | Execute the six prepared cases with benign controls, actual tool outputs and native agent traces. No model score can override an unauthorized side effect. |
| VA outbound requests | `mcp/tools/va_sandbox_readonly.py` implements unavailable/default or explicitly fictional responses; it is not a VA network client. Three facility tools have no patient-case argument. | Record this limited boundary. Do not claim live VA adapter SSRF protection. Inspect future adapters before enabling them. |
| Cross-MCP and tool poisoning | Local registration is explicit in `mcp/tools/__init__.py`; new tool registration requires scope review. This alone does not establish IBM-host behavior or registry-change detection. | Capture current IBM toolkit configuration and test output-directed connection/tool-replacement attempts in an isolated evaluation path. |
| Database concurrency | Shared permission replay protection passed locally. Prior CRM hosted acceptance tested sequential retries. | Run simultaneous writes against isolated synthetic fixtures, then independently count records and audit events. |
| Uncertain-write recovery | Existing regression tests include simulated lost acknowledgements and private booking recovery. These are not hosted fault-injection evidence. | Simulate a lost response after a real isolated commit; recover the original receipt and verify no duplicate. Do not interrupt the live demo. |
| Dependency advisories | Previous pinned-release findings remain open; today's regression pass counts do not remediate packages. | Audit the exact deployed dependency set, document reachability and test any proposed upgrade separately. |

Prepared agent cases: `eval/deepeval/server_wide_injection_cases.json`, explicitly
marked **PREPARED_NOT_EXECUTED**. They cover CRM notes, scheduling encounter text,
VA unavailable messages, task descriptions, reachable handoff content and lifecycle
text. They require case-bound fixtures, matching tool-call evidence and independent
state checks where writes are possible. Do not feed invented successful tool
responses to DeepEval and report them as an observed Avery run.

The existing Codespace was available but `gh codespace ssh` reported that its SSH
server could not start. GitHub's existing CI supplied the Linux validation instead.
IBM-agent and hosted database checks remain pending access restoration. No
credential reset is requested.

## Private booking pathway

Booking authority and automatic post-booking CRM notes remain separately evaluated
private-host operations. They are not additional MCP tools or evidence that IBM
selected a booking commit. Keep the [November 16 automatic-note acceptance](automatic-booking-crm-20261116.md)
and [agent-selected CRM acceptance](crm-rollout-20261116.md) as separate evidence.
The consumed CASE-041 fixture must not be booked again.

## Judge talking point

“We expanded the local evaluation from the original 21 tools to all 25 registered
tools. We tested malformed requests and permission boundaries, including swapped
caller cases and simultaneous permission replay. Those checks passed. We retain
one Windows-specific regression failure, verified the suite on Linux, and distinguish these local results from
the live agent and database tests still needed. Our coverage matrix shows exactly
what each result proves.”

Evidence: [machine-readable summary](evidence/server-wide-20261116/summary.json),
[scope checks and registry](evidence/server-wide-20261116/scope-matrix.json),
[contract checks](evidence/server-wide-20261116/contracts-final/mcp-probes.json),
[argument checks](evidence/server-wide-20261116/arguments-all/adversarial-arguments.json).
