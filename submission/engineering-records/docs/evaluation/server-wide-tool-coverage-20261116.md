# Coverage of all 25 registered MCP tools

November 16, 2026. Fresh local checks; **evaluation remains partial**.

Full matrix: [CSV](evidence/server-wide-20261116/tool-coverage.csv). Counts overlap and must not be combined into a security percentage.

| Tool | Local contracts | Hostile arguments | Remote scope denial |
|---|---|---|---|
| `verify_synthetic_identity` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `determine_workflow_state` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `search_availability` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `assess_access_standard` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `check_community_care_eligibility` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `get_case_lifecycle_state` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `get_scheduling_encounter` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `prepare_scheduling_handoff` | PASS 5/5 | PASS 1/1 | PASS 5/5 |
| `get_scheduling_handoff` | PASS 4/4 | PASS 4/4 | N/A handoff remote access denied separately |
| `validate_option_selection` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `record_option_selection` | PASS 5/5 | PASS 1/1 | PASS 5/5 |
| `prepare_veteran_confirmation_request` | PASS 5/5 | PASS 1/1 | PASS 5/5 |
| `record_veteran_confirmation` | PASS 5/5 | PASS 1/1 | PASS 5/5 |
| `validate_booking_preconditions` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `record_lifecycle_event` | PASS 5/5 | PASS 1/1 | PASS 5/5 |
| `get_va_sandbox_health_facility` | PASS 4/4 | PASS 4/4 | N/A public facility lookup |
| `search_va_sandbox_health_facilities` | PASS 4/4 | PASS 4/4 | N/A public facility lookup |
| `get_va_sandbox_health_facility_service` | PASS 4/4 | PASS 4/4 | N/A public facility lookup |
| `get_va_community_care_case_summary` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `get_va_patient_health_sandbox_summary` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `get_va_clinical_health_case_summary` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `get_crm_case` | PASS 4/4 | PASS 4/4 | PASS 5/5 |
| `record_crm_interaction` | PASS 5/5 | PASS 1/1 | PASS 5/5 |
| `create_crm_follow_up` | PASS 5/5 | PASS 1/1 | PASS 5/5 |
| `update_crm_follow_up` | PASS 5/5 | PASS 1/1 | PASS 5/5 |

## How to read the matrix

PASS means the listed bounded assertions passed. NOT TESTED is a gap, not a failure or a pass. N/A includes a specific scope reason. Contract checks include metadata and safe rejection, not a successful business journey for each tool. The CSV separately identifies concurrency at the shared permission gate and true database concurrency.

The 261 checks include 26 gate-sentinel checks across 13 read/CRM tools. These prove invocation denial/replay behavior in process; they do not prove database locking, recovery after restart, or agent resistance to malicious tool output.

Prior agent-selected read and CRM acceptance evidence remains dated separately; it was not rerun here. No new appointment was created.
