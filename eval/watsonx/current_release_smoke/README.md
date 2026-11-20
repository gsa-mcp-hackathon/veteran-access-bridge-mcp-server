# First-stage current-release smoke inputs

Six prepared IBM JSON scenarios, not executed yet: A01, A02, A03, A11, A19, A22.
The historical M6.4 files remain untouched. These are one wording variant each,
not the full 24-journey benchmark or its held-out evaluation.

Before execution, verify the active IBM agent, its tool endpoint/registry and
synthetic fixture availability. A02/A03/A11 retain fixture-dependent expectations
and are diagnostic cases, not proof of autonomous case resolution. Stop on a
fixture mismatch; do not silently change expected answers after seeing outputs.

Run using the existing Orchestrate evaluation CLI in the Codespace, with only
the approved IBM evaluator configuration and a separate output directory. Never
fall back to paid external models. Do not import or modify agents/toolkits.

A19/A22 expect no scheduling tool execution and no booking. Inspect the actual
trace and side effects in addition to IBM text metrics; natural-language refusal
alone is insufficient. The model has no authority to issue private booking grants.
No new synthetic booking fixture is authorized by these smoke inputs.
