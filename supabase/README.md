# Supabase scheduling migration history

The six original files in [migrations](migrations/) preserve the hosted scheduling changes in timestamp order. Begin with the [database setup guide](../db/README.md) for the required base schema.

| Version | Change |
| --- | --- |
| 011 | Add decision ordering to the existing scheduling schema. |
| 012 | Create the private scheduling writer role. |
| 013 | Create the scheduling login scaffold with login disabled. |
| 014 | Add restricted grants for locking scheduling rows. |
| 015 | Create the isolated test schema with scheduling tables and row-level security. |
| 016 | Add the test roles and writer policies. |

For a fresh schema rehearsal use PostgreSQL 16 or later with the Supabase role names `anon`, `authenticated` and `service_role` already present. The reproduction check creates empty non-login roles on its disposable instance. After 016, apply the separately tracked CRM SQL from the setup guide. Several migrations deliberately stop when roles, tables or prior decisions already exist. Use a fresh instance for each rehearsal.
