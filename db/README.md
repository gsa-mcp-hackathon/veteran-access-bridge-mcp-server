# Scheduling and CRM schema

This directory preserves four SQL files from backend release `ea0880f`. Choose the path that matches what you want to reproduce.

| Goal | Order in an empty, disposable database |
| --- | --- |
| Inspect the local scheduling model | [001](schema/001_initial.sql) creates the base `vab` tables. [003](schema/003_scheduling_lifecycle_evidence.sql) adds scheduling lifecycle evidence. [004](schema/004_scheduling_decision_order.sql) adds decision ordering. |
| Reconstruct the scheduling and CRM schema used by the demo | Start with 001 and 003. Follow the [Supabase migration history](../supabase/README.md) from 011 through 016. Finally apply [005](schema/005_crm_test_candidate.sql) to add CRM interactions, follow-up tasks and events in `vab_test`. |

Local 004 and hosted 011 implement the same ordering change. File 005 depends on the test schema and writer role created by 015 and 016. The original release records a manual CRM application verified against database metadata. Its filename reflects its origin as a candidate.

The [database reproduction check](../.github/workflows/database-schema.yml) shows the SQL invocation for each path. These files define schema and permissions. Demo appointments, credentials and the hosted knowledge corpus require separate provisioning.
