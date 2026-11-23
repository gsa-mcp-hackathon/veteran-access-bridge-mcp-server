> Historical narrative retained for traceability. Start with the [current review source](../evaluation/release-closeout-20261115.md); dates and claims below describe earlier checkpoints.

# Veteran Access MCP — Evaluation Documentation

## 1. Evaluation model

Veteran Access Bridge uses three complementary evaluation layers:

1. **Deterministic correctness and safety** — pytest and CI are authoritative for workflow rules, lifecycle transitions, slot eligibility, access-standard calculation, authorization/booking boundaries, idempotency, role controls, provenance, and fail-closed behavior.
2. **Primary agent/runtime evaluation** — watsonx Orchestrate Evaluate is the acceptance gate for the deployed `veteran_access_agent` using the governed remote MCP toolkit.
3. **Optional independent MCP evaluation** — Phoenix remains available for research, traces, and cross-runtime experiments. It is useful secondary evidence, but it is not a submission blocker.

All current evaluation evidence is synthetic/demo-only. It is not evidence of production VA deployment, HIPAA authorization, or operational booking authority.

## 2. Current M6.3 runtime

- Agent: `veteran_access_agent`
- Active toolkit: `veteran-access-mcp-remote-m63`
- Remote MCP: IBM Code Engine
- Governed tools:
  - `get_scheduling_encounter`
  - `assess_access_standard`
  - `determine_workflow_state`
  - `search_availability`
- Canonical synthetic cases:
  - Cardiology: `DEMO-CARD-5000335-001`
  - Primary Care: `DEMO-PC-5000999-001`

The shared Scheduling Encounter is the canonical context for current scheduling, preferences, option comparison, lifecycle/status, authorization-status, EPS-status, and booking-status questions.

For **access-standard-only** questions, `assess_access_standard(case_id)` is the single authoritative tool. It already loads the synthetic case/access context and performs the deterministic access calculation. A separate workflow-state call is not required for this intent.

`determine_workflow_state` remains available when workflow state itself is the user's intent. `search_availability` remains available for explicit legacy/raw availability inspection.

## 3. M6.3 evaluation checkpoint — accepted

Issue #19 is complete.

The evaluation effort used a versioned ten-case direct JSON suite under `eval/watsonx/direct_tests`, plus a six-case focused regression suite under `eval/watsonx/regression_tests`.

The final acceptance decision considered the smallest responsible layer rather than treating IBM's aggregate `is_success` field as authoritative by itself.

### Accepted behavior

- Cardiology and Primary Care scheduling-encounter questions route through `get_scheduling_encounter`.
- Preferences rank only already-eligible options.
- Preference rank does not replace the access-standard comparator.
- Stale and incompatible slots remain excluded.
- Cardiology preserves a 35-day wait against the 28-day Specialty standard and produces a Community Care **review recommendation only**.
- Primary Care preserves a 14-day comparator wait against the 20-day Primary Care standard.
- Community Care authorization remains separate from access-standard evidence.
- EPS is not invoked solely because an access threshold is exceeded.
- No booking is claimed without booking evidence.
- Unknown synthetic cases fail closed without fabricated scheduling facts.
- Synthetic-data disclosure is preserved.

### Final focused regression disposition

| Case | Disposition |
|---|---|
| 01 — Cardiology unified encounter | Accepted |
| 02 — Cardiology preference vs comparator | Accepted |
| 05 — Cardiology no-booking guardrail | Accepted behaviorally; IBM text matcher produced a false negative in some runs |
| 08 — Primary Care access standard | Accepted; correct authoritative access tool matched with correct parameters; extra non-required calls remain routing-efficiency debt |
| 09 — Primary Care no authorization/EPS/booking inference | Accepted |
| 10 — Unknown case / no fabrication | Accepted behaviorally; fail-closed behavior verified; IBM text matcher produced a false negative in some runs |

For the final #08 regression after the single-authority access contract was adopted:

- expected required tool calls: 1
- correct required tool calls: 1
- missed required tool calls: 0
- tool-call recall: 1.0
- tool-match success: true
- tool-parameter F1: 1.0
- semantic match: true
- total tool calls: 3
- tool-call precision: 0.33

The extra calls are recorded as **non-blocking routing-efficiency technical debt**. They do not change the deterministic access result and are not treated as a safety/correctness failure.

## 4. IBM evaluator limitations observed

Two independent evaluator limitations were observed during M6.3:

### Numeric `text_match` analyzer incompatibility

The persisted CSV uses numeric `text_match` values, while the standard analyzer version used during this checkpoint expected string enum labels. This caused post-processing to fail even after the evaluation execution completed and persisted `summary_metrics.csv`.

Therefore, analyzer failure is not treated as evidence that the underlying test execution failed.

### Text-goal false negatives

Some runs produced:

- correct tool routing,
- correct parameters,
- semantic match = true,
- safe behavior,

while still reporting `text_match = 0` and `is_success = false`.

For M6.3, acceptance therefore uses deterministic pytest/CI plus tool-routing, parameter, semantic, and safety evidence rather than a single aggregate field.

## 5. Historical baseline

An earlier seven-test saved-agent evaluation completed 7/7 with:

- journey completion: 1.00
- guardrail compliance: 1.00
- rubric mean: 1.00
- routing accuracy: 1.00
- tool-call precision: 1.00
- tool-call recall: 1.00
- tool-match success: 1.00
- missed tool calls: 0
- incorrect tool parameters: 0
- average response time: approximately 7.97 seconds

This remains historical evidence, separate from the later M6.3 direct-JSON checkpoint.

## 6. Safety and governance boundary

Current prototype boundary:

- synthetic data only
- no real PHI
- no production VA credentials
- no production write authority
- no independent clinical urgency determination
- no independent Community Care eligibility/authorization determination
- no EPS shortcut from an access-standard breach
- no booking claim without booking evidence
- deterministic backend services own business rules; MCP handlers remain thin wrappers

The server keeps `AVAILABLE`, `AUTHORIZED`, `VERIFIED`, and `BOOKED` separate.

## 7. Remaining evaluation work

The next evaluation work belongs to the UI/agent-interaction phase and Issue #23 Community Care research, not to reopening the M6.3 checkpoint.

### UI/agent-interaction evaluation

Measure:

- whether the Veteran and Scheduler views expose the same governed facts consistently;
- whether tool activity and source evidence are understandable;
- whether excluded slots and comparator/preference differences are explainable;
- whether the UI preserves synthetic/demo labeling;
- whether unsupported booking/authorization actions remain unavailable;
- tool-call efficiency and redundant-call rate as optimization metrics.

### Community Care / Issue #23

Add new tests only after authoritative semantics are researched for:

- HSRM referral/authorization vocabulary and status;
- referral/authorization correlation;
- appointment/completion evidence;
- SEOC/RFS where applicable;
- EPS participation/availability boundaries;
- freshness and closure evidence.

Do not infer these semantics from the current synthetic prototype.

## 8. Failure-analysis categories

For any future failure, classify the smallest responsible layer:

- policy/source-data mapping
- deterministic business rule
- source adapter
- lifecycle state/event
- MCP schema/docstring
- agent instructions/routing
- model behavior
- evaluation mismatch
- stale/invalid fixture
- dependency/runtime issue
