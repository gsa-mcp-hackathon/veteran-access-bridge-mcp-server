# Supabase

??? info "Why Supabase instead of only JSON fixtures?"
    Local JSON fixtures work well for the introductory MCP tutorial. The connected Avery experience also needs durable synthetic cases, scheduling decisions, CRM activity and receipts. Supabase PostgreSQL provides relational test persistence without pretending to be VA CDW or a VA scheduling system. See [ADR-002](engineering-decisions.md#adr-002-supabase-postgresql-for-synthetic-operational-data).

!!! warning "Synthetic data only — safeguard existing databases"
    Never put real Veteran records in the demonstration database. Review the migration scope, role privileges and backup before changing an existing hosted test database.


**Why Supabase?** The project lacked production VA Corporate Data Warehouse (CDW) and appointment-writer access. Supabase PostgreSQL supplied a controllable **synthetic operational analog** for patient/case context, appointment slots, scheduling requests, CRM interactions and persisted receipts. It is **not** an actual replica or a direct connection to VA CDW.

**Separate concerns:**

- **Relational layer:** PostgreSQL tables, keys, integrity constraints and transactional state for synthetic appointments and CRM.
- **Security:** restricted database roles, enforced Row-Level Security (RLS) where applicable, scoped service credentials, idempotency/audit behavior.
- **Knowledge/RAG:** optional `pgvector` extension plus document/chunk/embedding storage and source/provenance metadata; retrieval must be validated and cannot issue scheduling authority.

### PostgreSQL / Supabase CLI inspection

```powershell
# Install Supabase CLI using supported method from official docs (e.g. npm via npx)
npx supabase --version
# Optional local development only, requires Docker
npx supabase start
npx supabase status

# Read-only SQL verification against an AUTHORIZED synthetic database
# Requires locally installed psql and an approved connection URI from your secret store
$env:SYNTHETIC_DATABASE_URL = '<private synthetic connection URI>'
psql "$env:SYNTHETIC_DATABASE_URL" -c "select current_database(), current_user;"
psql "$env:SYNTHETIC_DATABASE_URL" -c "select table_schema, table_name from information_schema.tables where table_schema='public' order by table_name;"
psql "$env:SYNTHETIC_DATABASE_URL" -c "select extname from pg_extension where extname='vector';"
```

The project’s actual SQL migrations and permissions should be applied from the **reviewed database migration directory** (`db/` in the backend) rather than invented `CREATE TABLE` statements. **Do not** run destructive migrations against hosted/demo data without approval, backup and review. `supabase start` is an illustrative *new local instance*, not proof that the hosted project can be reconstructed from a generic command.

### Safe RAG design / inspection

```sql
-- Read-only checks after the project's reviewed knowledge schema is installed
SELECT extname FROM pg_extension WHERE extname = 'vector';
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' AND (table_name ILIKE '%kb%' OR table_name ILIKE '%chunk%' OR table_name ILIKE '%embed%');
```

Store per-chunk document IDs, version, source and embedding-model identifier. Ensure source access checks at retrieval time; never allow retrieved document instructions to grant identity, consent or authority. The diagram's `kb_documents`, `kb_chunks` and `kb_sources` are **architectural labels** and are not certified deployed schemas. Verify the real Supabase schema before claiming operational RAG. [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) · [pgvector](https://supabase.com/docs/guides/database/extensions/pgvector).

---

**Developer Guide:** [Overview](index.md) · [← VHA Lighthouse sandbox](vha-sandbox.md) · [IBM watsonx Orchestrate →](ibm-orchestrate.md)

!!! success "Supabase validation checkpoint"
    Before testing a connected write, confirm the correct test database, expected schema, restricted role and a known synthetic case through the backend connection. Connectivity alone does not prove fixture readiness.

??? tip "If the connection works but the case is missing"
    Check the selected project and schema, applied migrations, loaded synthetic fixtures and role permissions. Do not weaken authorization checks to make a missing case appear.

See [Configuration and secrets](configuration-and-secrets.md) and [Troubleshooting](troubleshooting.md) for environment-specific checks.
