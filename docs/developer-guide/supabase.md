# Prepare the Supabase scheduling database

For the local MCP tutorial, use the bundled records. For the connected Avery call, create a dedicated Supabase project for synthetic cases, slots and CRM records. Run these commands in **Bash**, at the backend repository root, with the PostgreSQL client (`psql`) installed.

??? info "Why Supabase?"
    The voice call and after-call work need the same durable appointment and receipt. Supabase hosts the demonstration’s PostgreSQL tables. VA facility and patient information have separate access paths. [Engineering decision](engineering-decisions.md#adr-002-supabase-postgresql-for-synthetic-operational-data)

!!! important "Read this before provisioning for a full voice call"
    The submitted backend checks the Supabase project reference against a project fixed in its database boundary. A new project can reproduce the SQL schema; setting a new connection URI alone cannot authorize the application to use it. An independent hosted deployment needs a reviewed adaptation of that boundary and its tests. Keep the project, schema, restricted-role and TLS checks in place. [Connection checks in the submission](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/src/veteran_access_bridge/adapters/supabase_scheduling_connection.py)

### 1. Connect to a fresh test database

Create an empty project in your Supabase account. Open **Connect** and copy the PostgreSQL connection details for your administrative role. Choose the direct connection if your network supports it or the session pooler for IPv4 connectivity. Set the displayed host, port and database user below. Supply the database password when prompted by PostgreSQL or use a private PostgreSQL password file. [Supabase connection instructions](https://supabase.com/docs/guides/database/connecting-to-postgres)

```bash
read -rp "Database host: " PGHOST
read -rp "Database port: " PGPORT
read -rp "Database user: " PGUSER
export PGHOST PGPORT PGUSER PGDATABASE=postgres PGSSLMODE=require
psql -X -c "select current_database(), current_user, to_regnamespace('vab_test');"
```

**Check:** confirm the project host and user. The last column should be empty. If the schema exists, select a fresh project for the rehearsal.

### 2. Apply the scheduling and CRM migrations

Copy this whole block. It runs in a subshell and stops at the first SQL error. This is the hosted-schema order used by the [repository database check](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/.github/workflows/database-schema.yml). The migrations assume the standard Supabase roles exist.

```bash
(
  set -e
  for file in db/schema/00{1,3}_*.sql; do
    psql -X -v ON_ERROR_STOP=1 -f "$file"
  done
  for file in supabase/migrations/*.sql; do
    psql -X --single-transaction -v ON_ERROR_STOP=1 -f "$file"
  done
  psql -X -v ON_ERROR_STOP=1 -f db/schema/005_crm_test_candidate.sql
)
```

**Check:** run `psql -X -c '\dt vab_test.*'`. Look for `appointment_request`, `slot`, `appointment`, `crm_interaction`, `crm_follow_up` and `crm_event`. If a migration reports an existing role or table, identify the last successful file before attempting a retry. Some migrations intentionally refuse a second application.

### 3. Connect the backend and check fixture readiness

Migration 016 creates restricted role scaffolding with login disabled. Have the database owner provision the runtime login for this test environment under the intended restricted grants. Store its private connection URI on the backend as `VAB_SUPABASE_TEST_DATABASE_URL`. The administrative connection used above is for migration only.

Use the restricted connection and the runtime’s permitted role to check whether the required rows are visible. In a private terminal with the backend connection value already loaded, run:

```bash
psql -X -v ON_ERROR_STOP=1 "$VAB_SUPABASE_TEST_DATABASE_URL" \
  -c 'SET ROLE vab_test_scheduling_writer' \
  -c 'SELECT count(*) AS linked_cases FROM vab_test.scheduling_case_link' \
  -c 'SELECT count(*) AS slots FROM vab_test.slot'
```

**Before the first call:** an empty schema needs an authorized synthetic patient, linked request and matching inventory for the chosen facility. The submitted schema migrations do not seed the hosted demo population. The bundled local JSON example is a separate data source. If you have only a fresh clone and empty tables, pause the booking walkthrough here until your test data owner supplies a prepared fixture. A nonzero row count alone does not prove a specific case can be booked.

**If the login works but the query fails:** check membership in the restricted role and its grants. For a zero count, check the project, fixture load and row visibility. [Configuration and secrets](configuration-and-secrets.md)

### 4. Prepare a rehearsal identity in an authorized test environment

The repository includes a fixture helper for Judy Morrison. It creates a synthetic patient, open Primary Care request and case link. It does not populate slots or create an appointment. Use it only after the test environment has the approved project binding, the restricted runtime connection and permission for fixture writes. In that environment, run the preview first:

```bash
uv run --no-sync python scripts/prepare_simple_voice_patient.py
```

**Check:** look for `"applied": false` and `"appointment_count_unchanged": true`. The preview exercises the writes inside a rolled-back transaction. To retain that fixture in your disposable database, repeat with `--apply`. A booking rehearsal additionally requires eligible slot bindings for the case. If the helper reports “Approved Supabase project required,” revisit the project boundary above.

Continue with [VA sandbox reads](vha-sandbox.md), then [IBM Cloud setup](avery-ibm-start.md).
