# Developer Guide

**CLI-first reproduction and integration setup.** Read-only fixture tests need no IBM, VA, Supabase or production credentials. Optional hosted integrations require authorized access and environment-specific configuration. Commands below distinguish **project-documented** runs from **general setup recipes that have not been rerun for this site**.

## 1 · Local MCP server: quickest independent check

**Requirements:** Python 3.12, Git, `uv`, Windows PowerShell 7 (examples), a clean checkout. The pinned November 18 documentation review used Python 3.12.9.

```powershell
# Backend source (historical evidence pin; private repository access required)
git clone https://github.com/wbgreen0405/veteran-access-bridge.git
cd veteran-access-bridge
git checkout --detach 5b6cd072f23b4d4edce2e19c4f75faa774c87988
uv venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -e '.[dev]'
.\.venv\Scripts\Activate.ps1
python --version
```

!!! warning "Lockfile finding"
    This reviewed candidate did **not** pass `uv sync --locked --group dev --python 3.12` because its `uv.lock` required updating. The editable install shown above passed in the documented environment; it does **not** establish lock reproducibility. Review `Reproducibility.md` in the repository before final judging.

```powershell
# Run server-side checks in local/synthetic fixture configuration
python -m pytest -q
python eval/probe_mcp_contracts.py --output-dir eval/results/reviewer-contracts-new
python eval/probe_mcp_adversarial.py --output-dir eval/results/reviewer-arguments-new

# MCP stdio mode: starts a process waiting for an MCP client
veteran-access-mcp
```

In another terminal (Node.js/npm required), the *source-derived Inspector command* is:

```powershell
npx @modelcontextprotocol/inspector veteran-access-mcp
```

The Inspector GUI command was **not run** during the documentation review; follow the locally printed address/token. Avoid storing sensitive tokens in Git. The default **21-tool** in-process discovery and two fixture reads *were* verified separately.

**Safe test inputs:** `DEMO-CARD-5000335-001` (35/28 synthetic specialty comparator), `DEMO-PC-5000999-001` (14/20 primary comparator), `UNKNOWN-CASE` (must deny). Do not reuse consumed booking cases.

## 2 · VHA Lighthouse API sandbox: access and verification

The [VA Developer portal](https://developer.va.gov/) provides published VA API specifications, sandbox-access forms and authorization guidance. **Sandbox credentials are API-specific**; a Facilities API key is different from a patient-health OAuth client. Sandbox access is not production VA system authority.

**Access process:**

1. Select the required API and read its **Sandbox access**, **Authentication**, OpenAPI and sample data documentation at [developer.va.gov](https://developer.va.gov/).
2. Request the applicable sandbox key/client ID through the API's sandbox form. For OAuth Client Credentials Grant (CCG), follow the **API-specific** JWK/public-key registration and sandbox JWT rules; for OAuth authorization-code APIs use the supplied test-user/consent flow.
3. Store the private key, API key and client secret **outside this repository**, in your approved credential manager or local ignored environment.
4. Confirm the permitted sandbox endpoint/paths from the selected API's **current OpenAPI specification**. Do not substitute arbitrary URL paths, production endpoints or live Veteran identifiers.
5. Validate one sandbox read and an expected denied/missing-credential case; record HTTP status, run date and sanitized response, **never** bearer/JWT secrets.

### PowerShell verification templates

```powershell
# Example A: API-key sandbox read, only for an API documented to use x-api-key
$env:VHA_SANDBOX_KEY = '<read from approved local secret store>'
$env:VHA_SANDBOX_TEST_URL = 'https://<documented-sandbox-host>/<documented-read-path>'
Invoke-RestMethod -Uri $env:VHA_SANDBOX_TEST_URL -Headers @{ 'apiKey'=$env:VHA_SANDBOX_KEY } -Method Get

# Example B: OAuth sandbox read, after completing API-specific token grant
$env:VHA_SANDBOX_ACCESS_TOKEN = '<authorized short-lived sandbox token>'
Invoke-WebRequest -Uri $env:VHA_SANDBOX_TEST_URL -Headers @{ Authorization="Bearer $env:VHA_SANDBOX_ACCESS_TOKEN" } -Method Get
```

!!! note "Header varies by API"
    The API-key header above is an *illustrative placeholder* and **must be replaced with the header or query parameter in that API's OpenAPI docs**. Do not execute templates with invented hosts or assume both grant flows apply. Keep JWT/private-key creation under the API's documented secure process. Earlier project notes say VA CCG OAuth/eligibility returned HTTP 200; that is historical user verification, **not a fresh probe for this site**.

**Project integration:** Configure read adapters only for approved sandbox APIs. No VistA, HSRM or EPS production booking is demonstrated. Reference: [VA API onboarding](https://developer.va.gov/onboarding/working-with-lighthouse-apis) · [VA sandbox access guide](https://developer.va.gov/explore/api/va-facilities/sandbox-access) · [OAuth authorization docs](https://developer.va.gov/explore/verification/docs/authorization).

## 3 · Supabase: PostgreSQL synthetic CDW, CRM and RAG

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

## 4 · IBM watsonx Orchestrate evaluation through ADK CLI

**Important:** Hosted evaluation commands require authorized IBM credentials and a known environment. Historical M6.3/M6.4 configurations are not equivalent to the later consolidated 29-tool server and 21-tool Avery attachment configuration.

```powershell
# Isolated IBM ADK environment (do not alter the backend Python environment)
python -m venv .venv-adk
.\.venv-adk\Scripts\Activate.ps1
python -m pip install --upgrade ibm-watsonx-orchestrate
orchestrate --version
orchestrate --help
orchestrate env --help
orchestrate env list

# Select an existing authorized environment
$EnvironmentName = 'YOUR_AUTHORIZED_ENVIRONMENT'
orchestrate env activate $EnvironmentName
orchestrate agents list
orchestrate toolkits list
orchestrate connections list
orchestrate evaluations --help
```

**Project-owned evaluation runners** (record the environment and output directory):

```powershell
pwsh ./deploy/ibm/orchestrate/run-m64-evaluation.ps1 -EnvironmentName $EnvironmentName
pwsh ./deploy/ibm/orchestrate/run-m63-evaluation.ps1 -EnvironmentName $EnvironmentName
pwsh ./deploy/ibm/orchestrate/run-m63-regression.ps1 -EnvironmentName $EnvironmentName
```

M6.4 historical runner uses **13 scenario JSON files**; that number does *not* imply 13/13 passed. M6.3 historical evaluation uses 10 direct cases and 6 focused regression cases. Inspect each newly written `summary_metrics.csv`, raw traces and run identity. The **November 2026** evidence is versioned and must not be merged across configurations.

A general current IBM ADK pattern is `orchestrate evaluations evaluate --help` and the [IBM evaluation guide](https://developer.ibm.com/learningpaths/watsonx-orchestrate-agentops/agent-evaluation-workflows/). Consult that command's output for your installed ADK version **before** supplying flags. Do **not** rerun original `configure-m64.ps1` against the accepted later Avery deployment; it may replace its earlier candidate toolkit. [Project IBM CLI runbook](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-m64-codespace-ibm-cli-relogin-deploy.md).

## 5 · DeepEval: agent outcome grading (optional reproduced environment)

DeepEval is a **separate agent-quality check**, not permission to bypass backend validation. Project history records a corrected **0.95** score on a bounded two-task, three-call read evaluation; an earlier 0.0 adapter run had zero evaluable tasks and cannot be interpreted as failure.

```powershell
# In an isolated evaluation environment
python -m pip install deepeval
deepeval --help
deepeval test run --help
# Run ONLY an actual reviewed DeepEval test file from the repository:
deepeval test run PATH_TO_REVIEWED_TEST_FILE.py
```

A runnable test must supply its own `LLMTestCase` (inputs, observed actual output and reference/context), configured metrics and any authorized evaluator-model credentials. This documentation **does not invent a project test-file path** or claim the above CLI has been rerun on the current deployment. See [DeepEval CLI](https://deepeval.com/docs/command-line-interface) and [quickstart](https://deepeval.com/docs/getting-started).

## 6 · Phoenix: tracing and visual inspection (optional)

Arize Phoenix can display traces, tool spans, prompts and latency **when an application has OpenTelemetry/OpenInference instrumentation and an export path**. Running Phoenix alone does not capture any agent calls.

```powershell
# Optional: local Phoenix server with Docker
# Review firewall and data-retention settings before exposing ports.
docker run --rm -p 6006:6006 -p 4317:4317 arizephoenix/phoenix:latest
# Open http://localhost:6006 and configure an OpenTelemetry exporter for the app.
```

For Python-based tracing, follow [Phoenix OpenInference setup](https://github.com/Arize-ai/phoenix/blob/main/.agents/skills/phoenix-tracing/references/setup-python.md); choose the instrumentor for the **actual framework** rather than installing an unrelated OpenAI instrumentor. Keep patient IDs, real PHI, secrets and tokens out of trace attributes. A Phoenix screenshot or trace-export artifact **must be collected separately** before claiming evaluated Phoenix results.

## 7 · Release and evidence checklist

- [ ] Record source SHA, Python version, environment and installed package versions.
- [ ] Confirm **read-only** Cardiology, Primary Care and unknown-case denial in local fixture mode.
- [ ] Run tests/probes in **new output directories**; retain failures and skip counts.
- [ ] Document *which* IBM toolkit, agent version and authorized sandbox were evaluated.
- [ ] Inspect PostgreSQL schema, RLS, migration version and provenance before describing RAG as deployed.
- [ ] Keep sandbox and Supabase credentials in approved secret storage—never in GitHub Pages or Markdown.
- [ ] Do not reuse consumed historical booking cases, claim production VA writes, or treat a generated sentence as a booking receipt.

[Reproducibility source guide](https://github.com/wbgreen0405/veteran-access-bridge/wiki/Reproducibility) · [IBM CLI runbook](https://github.com/wbgreen0405/veteran-access-bridge/wiki/IBM-watsonx-Orchestrate-CLI-Setup-and-Verification) · [Evaluation Results](evaluation-results.md)
