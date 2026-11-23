> **Historical deployment inventory:** These values describe their recorded checkpoint. See the [November 18 reconciliation](../submission/documentation-reconciliation-20261118.md) before treating them as the latest deployed state. No deployment was changed during this documentation review.

# Current sandbox deployment

Updated November 16, 2026 through the existing Codespace and IBM Code Engine application metadata. Reviewer login remains enabled. This is a prototype inventory, not authorization to expose a public patient service. Organizer hosting approval remains a submission gate.

## Components and versions

IBM region `ca-tor`, project `ce-550000w6t0`. Reuse these existing applications.

| Component | Existing application | Deployed image suffix |
|---|---|---|
| MCP/API and trusted voice host | `veteran-access-bridge-m64-canary` revision `00032` | `veteran-access-bridge:sha-a531d48a2fdeb34785eb7051b43d5d6a92fa31cd` |
| LiveKit worker | `vab-avery-voice-worker` | Existing revision `00003`, source `0165196` |
| Frontend | `vab-avery-callcenter` revision `00021` | `veteran-appointment-bridge:avery-callcenter-cf95b1ff0a66b2de94c5122d01ed8cdd39dcbe66` |

All images use `ghcr.io/wbgreen0405/`. Backend PR #205 remains unmerged. The Call in Browser interface is preserved. The frontend now projects verified call-bound offers and booking receipts and stops activity polling on hang-up. The worker image is unchanged.

The CRM rollout adds minimum-necessary save receipts in Wrap Up. Frontend CI passed
162 tests, lint, typecheck and build; deployment-package and runtime checks passed.
Backend CRM is opt-in and enabled on this canary: 25 server tools, 17 Avery
attachments. Frontend environment values and secret references were preserved.
See the CRM rollout and live acceptance report.
The sections below describe historical checkpoints, not the current CRM acceptance.

## Earlier browser connection acceptance — November 14

The existing **Call in Browser** button now reaches IBM watsonx Orchestrate through LiveKit and the authenticated voice host. The server binds the intake interaction to the issued room and participant. Worker signatures, participant SID checks, expiry and replay checks remain enforced. Intake calls cannot switch into the protected booking state machine through model output or caller metadata.

- 58 routing/runtime tests, 104 booking/connection policy tests, and 27 caller-activity/monitor tests passed (189 tests across disjoint test files).
- A real browser call received Avery's greeting as a LiveKit caption and was ended normally.
- A separate synthetic RTC caller used the same frontend gateway, sent real speech requesting Primary Care, and received IBM's request for name and date of birth. The event feed contained two `agent_answered` events from `watsonx_orchestrate`.
- Voice session `vs-b054aec2-32be-4028-8285-cde62dafe8a8`, interaction `int-89971c04f6444e04`; end returned HTTP 200. Missing-token and other-session activity requests returned HTTP 403.
- This acceptance verifies conversation and scoped events, **not a booking through browser intake or an MCP tool invocation**. No identity or booking consent was supplied in this test. The earlier protected CASE-031 booking remains separate evidence; this earlier test preceded the protected handoff implemented below.

Caller activity uses the dedicated `vab-avery-caller-activity` secret reference on the backend and frontend only. Backend `VAB_CALL_ACTIVITY_ENABLED=true` and frontend `VAB_PUBLIC_GUEST_ACTIVITY_ENABLED=true` enable sanitized events for the caller's own short-lived session. The service key never reaches the browser; existing origin, session, and staff-monitor gates remain intact.

## Endpoint map

| Purpose | Endpoint | Interpretation |
|---|---|---|
| Frontend | https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/ | Existing sandbox UI, not proof of authoritative live booking |
| Embedded IBM experience | https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/demo-call | IBM native embedded agent; separate from trusted LiveKit acceptance |
| Backend | https://veteran-access-bridge-m64-canary.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud | Existing canary only |
| Health | Backend + `/health` | Liveness; does not prove booking correctness |
| MCP | Backend + `/mcp` | Bearer-authenticated existing 21-tool server |
| Private voice | Backend + `/internal/synthetic-primary-care/voice-turn` | Worker assertion required; not a browser or MCP tool endpoint |
| Worker | Existing internal Code Engine application | No public worker URL or new service required |

The Lovable preview is a design/development surface, not the verified voice acceptance endpoint. The separate main backend and KB application are outside this deployment update.

## Frontend setup

```bash
git clone https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git
cd veteran-appointment-bridge
bun install --frozen-lockfile
cp .env.example .env
bun run dev
```

Default configuration keeps live gateways disabled and allows the existing scripted UI prototype. Do not equate fixture/replay state with persisted booking evidence. Configure server variables privately only for the mode being tested:

| Variables | Purpose / boundary |
|---|---|
| `VAB_API_BASE_URL` | Server-only canonical backend URL; local default is loopback, hosted target is the canary above |
| `VAB_MSA_LIVE_MONITOR_ENABLED` | Existing monitor gate; observer readiness still requires backend support |
| `VAB_MSA_MONITOR_SERVICE_KEY`, `VAB_MSA_OPERATOR_ACCESS_CODE` | Separate private keys; never `VITE_*`, browser code, screenshots, or Git |
| `VAB_MSA_ONE_CLICK_DEMO_ENABLED` | Loopback/private-forwarding mode only; false for hosted IBM/Lovable |
| `VAB_PUBLIC_AVERY_EMBED_ENABLED`, `VAB_PUBLIC_AVERY_EMBED_ORIGIN` | Legacy IBM embed opt-in and exact HTTPS origin; these do not enable trusted LiveKit booking |
| `VAB_EMBED_TOKEN_SERVICE_KEY`, `VAB_EMBED_GUEST_COOKIE_KEY` | Existing server-side embed broker secrets; preserve security and origin checks |
| `VAB_PUBLIC_GUEST_CALL_ENABLED`, `VAB_PUBLIC_GUEST_ORIGIN` | Separate guest call mode; disabled example defaults, not authorization for publication |
| `VAB_PUBLIC_GUEST_ACTIVITY_ENABLED`, `VAB_CALL_ACTIVITY_SERVICE_KEY` | Separate activity gate and server credential; not implied by a working voice connection |
| `VAB_DEPLOY_TARGET=code-engine`, `NITRO_PRESET=node-server` | Build the standalone Node server, not a static-only Vite export |

Frontend checks: `bun run lint`, `bunx tsc --noEmit`, `bun run test`, `node --test scripts/smoke-msa-monitor.test.mjs`, `bun run build`. Container packaging is governed by `Dockerfile` and `.github/workflows/code-engine-package.yml`. Do not regenerate `bun.lock` to update documentation.

## Trusted LiveKit backend configuration

This configuration belongs in the **backend/worker**, not this frontend's `.env` or browser bundle. The deployed trusted path uses one replica and a scoped approved fixture. Read backend PR #205 before changing it.

- `VAB_ENABLE_TRUSTED_VOICE_BOOKING=true`; `VAB_VOICE_WORKER_SECRET` is shared only by the backend and worker.
- `VAB_TRUSTED_HOST_ISSUER`, `VAB_TRUSTED_HOST_AUDIENCE`, `VAB_TRUSTED_HOST_SUBJECT` define the exact trusted host identity. RSA private material stays backend-only. Supply exactly one of each `VAB_TRUSTED_HOST_PRIVATE_KEY_PATH` / `_B64` and `VAB_TRUSTED_HOST_PUBLIC_KEY_PATH` / `_B64` pair.
- `VAB_SIGNED_DECISION_VERIFIER_SECRET` and `VAB_PRIVATE_VA_BOOKING_SIGNING_SECRET` remain backend-only and distinct from worker authentication.
- `VAB_SUPABASE_TEST_MODE=true`, `VAB_ENABLE_SUPABASE_TEST_WRITES=true`, `VAB_SUPABASE_PROJECT_REF=wntbjxjeaxngjrffmnis`, and a restricted `VAB_SUPABASE_TEST_DATABASE_URL`; operational `VAB_ENABLE_SUPABASE_SCHEDULING_WRITES` remains disabled.
- `VAB_ENABLE_BROWSER_PC_BOOKING=true` enables the host-controlled Primary Care handoff. `VAB_PRIVATE_PC_APPROVED_CASE` pins one reviewed synthetic case on the backend; CASE-031, 033, 035, 037 and 039 are consumed. CASE-041 is prepared for one approved rehearsal; verify its current count before any call. Never change the pin from browser metadata.
- `PGSSLROOTCERT=/app/supabase-ca/root.crt`, with full database TLS verification. Do not substitute the older incompatible KB certificate bundle or relax certificate validation.
- Existing LiveKit and Deepgram credentials stay in their respective runtime secrets. Do not copy database or host signing credentials to the voice worker.

Existing secret references: backend `vab-pr205-voice-backend`, worker `vab-pr205-voice-worker-auth`, CA `vab-pr205-supabase-ca`, plus pre-existing runtime secrets. Names are inventory, not secret values. Preserve the complete existing configuration during any future release.

## Verify before a future release

Use the existing authenticated Codespace, currently `/workspaces/vab-pr205` for the accepted backend. The old instruction to use `/workspaces/veteran-appointment-bridge` is not valid for the inspected Codespace: that directory was absent. Confirm actual worktrees rather than creating another Codespace.

```bash
ibmcloud target
ibmcloud ce project current
git status --short
git rev-parse HEAD
```

Inspect application image/revision and secret **references** privately. Do not paste raw configuration dumps into evaluation artifacts. Require tests, immutable published image, preserved rollback configuration, expected target, health, authenticated MCP discovery, denial probes, and independent database acceptance before claiming a new release. No deployment commands are executed by this documentation change.

For future updates, change only the intended existing canary/worker after those gates. Never reuse the November 10 runbook's old image as the current release, replace all environment variables wholesale, enable production writes, or use `*-latest` as acceptance evidence. A single-instance restart invalidates active call authority; it does not authorize retrying an uncertain commit.

## Acceptance evidence

### Current browser booking acceptance

The final approved CASE-033 call completed through the actual frontend gateway in
74.66 seconds, with a verified call-bound booking receipt and successful end
acknowledgement. Independent database readback found exactly one appointment and
identity/consent bound to the same voice session. CASE-031 and CASE-035 remain
intact. All three cases are now consumed; another rehearsal needs a separately
approved fresh fixture. The current backend pin remains CASE-033.

Backend and frontend ready revisions are both `00016`. Authenticated discovery
confirmed all 21 MCP tools. Validation: 176 backend tests, 126 frontend tests,
typecheck/build and Linux release checks passed. The separate Chrome UI check
verified connection, greeting/captions, mute and normal hang-up.

- Final sanitized browser receipt and database evidence
- Browser integration acceptance report

The MCP encounter read is invoked by the trusted host; it is not evidence that IBM
selected a tool. The full booking was exercised by a real RTC client through the
frontend gateway, not manually completed through the visual Chrome interface.

### Earlier protected voice acceptance

- Backend PR #205
- Pinned acceptance report
- Pinned transcript and database evidence
- [Current backend image publication](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/ci/ci-run-43600257159.md)
- [Worker image publication](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/ci/ci-run-43562472928.md)

One real synthetic voice call passed, with independent readback and no duplicate booking. This is not production patient authentication, a real VistA/HSRM/EPS booking, broad trial reliability, or proof that all frontend surfaces use the trusted path.

## Verified reviewer rollout - November 15, 2026

Frontend revision `vab-avery-callcenter-00019` runs image `ghcr.io/wbgreen0405/veteran-appointment-bridge@sha256:9bd7ed3ca09d5bae5111554c85736786566475591173739fc64dcb69682c725c` (source `f5ae0717c54fe79703f951e5abe0d26fc5e30530`; publication run 43751203560). Reviewer login is enabled. Anonymous page redirect and API denial, valid sign-in, secure cookie, authenticated session/application, logout and logout replay denial all passed at 19:40 UTC. Existing secret references were retained; secret values are excluded from evidence. Backend and worker specifications are unchanged. No voice call or booking was attempted; CASE-041 rehearsal remains deferred.

[Open restricted reviewer login](https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/login). Hosting approval remains a separate submission gate. Rollback must retain access restriction or take the demo offline.
