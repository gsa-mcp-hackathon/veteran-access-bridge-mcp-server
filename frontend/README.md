> **Documentation review — November 18:** Read the [reconciliation](docs/submission/documentation-reconciliation-20261118.md) and judge wiki for milestone-specific evidence. End-to-end synthetic scheduling is proven; later UI/configuration checks and final visual presentation have distinct scopes. Deployment counts below retain their original checkpoints.

# Avery Call in Browser

**Latest call improvements:** PR #31,
branch `feat/voice-call-polish`. The live view replaces offered slots with the confirmed
appointment, moves the saved letter into Wrap Up, follows new conversation content
with a Jump to latest control, and provides a typed-reply option. Active calls renew
through the original participant check instead of a fixed five-minute cutoff.
The existing frontend is kept at one warm instance because reviewer and call sessions
are process-local. Restarts still require sign-in again. Backend evidence and limits.
Earlier release entries below describe their own historical acceptance runs.

The reviewer interface for **Veteran Access Bridge**, a synthetic Veteran appointment-coordination prototype. This repository contains the TanStack Start/React frontend and protected server-side gateways. The MCP backend is the primary competition submission and owns the governed server, scheduling policy, identity, consent and persistence. The current enabled catalog has 29 tools; Avery has 21 attachments.

## Start here for judges

| Purpose | Link |
|---|---|
| Review the main MCP submission | Backend judge guide |
| Understand the solution | Presentation and architecture |
| Assess testing and limits | Evaluation document and security follow-up |
| Open the demonstration | [Restricted reviewer login](https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/login) and [4:30 caller script](docs/submission/demo-script.md) |
| Inspect this repository | [Documentation index](docs/README.md), [deployment inventory](docs/deployment/current-sandbox.md), [cleanup review](docs/submission/repository-audit.md) |

**Review branch:** `docs/gsa-submission-alignment-20261114`, PR #27. Review files remain drafts pending final rehearsal and submission instructions. `main` is not assumed to match the reviewed deployment.

## Reviewer experience

1. Open the login page and enter the reviewer code supplied privately.
2. Use **Call in Browser**, allow microphone access, and speak with Avery using the prepared synthetic scenario.
3. Observe the conversation and scoped activity. A booking claim requires a verified receipt; replay fixtures and page availability are not booking evidence.
4. End the call, then sign out. Active calls renew through the original participant check in the later call-polish implementation; expiry still applies when renewal fails or is absent. Reviewer sessions expire separately after one hour. The earlier five-minute expiry test describes its own revision.

CASE-041 was booked on November 16, with its automatic CRM note verified. Do not repeat consumed cases or create extra bookings without a prepared approved fixture. Sign in privately before recording or screen sharing.

## Dated rollout and acceptance records

**Deployed after-call work:** the new panel supports saved CRM wrap-up, a confirmation-letter preview and download after hang-up. A focused real gateway/RTC call verified one CASE-048 booking, saved wrap-up, letter and duplicate-end protection. Letter generated, not sent. The successful panel/download was not visually inspected in that separate browser session; see results, retained failures and attribution. CASE-048 is consumed; do not book it again.

Current review: `feat/dynamic-sandbox-callers`, PR #30, stacked on PR #29. Frontend image `11a4fd9`, revision **00024**, is deployed behind reviewer login. **175 tests**, lint, typecheck, build and CI passed. Call-specific case IDs are accepted only in verified session-bound option and receipt projections. Dynamic caller acceptance and limits. The authenticated deployed page was inspected in Chrome.

Appointment cards now appear inside the conversation from verified call-bound option events. They show patient-local dates/times and source-supplied provider/clinic information, with an honest missing-provider label. Spoken confirmation remains required. One real RTC acceptance call verified two options in Central time, all five required IBM-selected tools, one appointment and one automatic CRM note. See the acceptance report and retained failures.

CASE-047 is consumed. The populated calendar was verified through component tests and the actual authorized option feed; the headless browser check covered the initial page, not the populated live call. Latency remains open (4.879-second median, 13.720-second maximum in this controlled call). Earlier presentation and evaluation files require an update before submission.

### Historical CRM checkpoints

CRM development branch `feat/avery-crm-call-management` adds call-bound save receipts
to Wrap Up and four optional CRM tool labels. The browser receives receipt metadata
only, never database credentials or raw CRM notes. The matching backend CRM branch
uses the existing Supabase `vab_test` schema. Frontend source `cf95b1f`, revision
`00021`, is deployed with reviewer login preserved. CI passed 162 tests, lint,
typecheck, build and the separate deployment-package/runtime checks. The backend
canary at that checkpoint had 25 tools and Avery has 17 attachments. One controlled voice call
passed: IBM-selected CRM reads, a saved note, and a follow-up created then cancelled.
Three call-bound receipts matched Supabase records; no appointment was created.
Visual receipt rendering remains unverified. CRM call acceptance is
tracked in the CRM rollout report.

A separate booking trial verified one CASE-041 appointment and one automatic CRM
summary. Wrap Up now shows **Automatic booking note saved** or **pending**, with
trusted booking-service provenance. This automatic action is distinct from an
IBM-selected MCP write. The repeat status question created no duplicates. See
automatic-note evidence and limitations.

Prior checkpoint: frontend source `f5ae071`, revision `00019`, passed nine live access/session checks and 150 tests. The November 15 [deployment inventory](docs/deployment/current-sandbox.md) retains that rollback reference.

IBM watsonx Orchestrate remains the agent behind the LiveKit voice path. The baseline 21 tools and 13 attachments are preserved, with four optional CRM tools added. Separate IBM-native evidence verifies independently selected case reads. The earlier CASE-039 booking used a host-invoked lookup and returned an API receipt; the final visible browser-receipt rehearsal remains open. See the prior release report for exact scope.

All patient records and appointment writes are synthetic. Reviewer login grants UI access, not booking authority or production identity. Broader security evaluation remains partial, and organizer hosting approval is unconfirmed.

## Code map

| Path | Responsibility |
|---|---|
| `src/server.ts`, `src/lib/reviewer-access.ts` | Server-enforced reviewer login and session checks |
| `src/routes/api/demo-call.ts` | Protected browser-call gateway |
| `src/routes/api/msa-monitor.ts` | Protected monitor gateway |
| `src/lib/bounded-json.ts` | Request byte limit and read deadline |
| `src/components/msa/` | Call workspace, conversation, activity and receipts |
| `src/lib/live-monitor.ts`, `src/lib/mcp-execution.ts` | Evidence projections and MCP activity presentation |
| `src/test/`, `scripts/` | Frontend regressions and HTTP/package smoke checks |
| `Dockerfile`, `.github/workflows/` | Standalone Node build, validation and controlled publication |

## Local development

Use Bun and the committed lockfile, matching CI. Copy environment examples only if a local file does not already exist.

```bash
git clone --branch docs/gsa-submission-alignment-20261114 https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git
cd veteran-appointment-bridge
bun install --frozen-lockfile
# Optional: copy .env.example to a new .env, without overwriting existing settings.
bun run dev
```

Live gateways are disabled by default. Local replay is a UI fixture, not a live call or booking. Keep credentials server-side and out of `VITE_*` variables. Follow the [reviewer configuration guide](docs/deployment/reviewer-access.md) for the restricted hosted mode.

```bash
bun run lint
bunx tsc --noEmit
bun run test
node --test scripts/smoke-msa-monitor.test.mjs
bun run build
```

## Deployment and historical interfaces

The existing application is `vab-avery-callcenter` in IBM Code Engine project `ce-550000w6t0`, region `ca-tor`. It requires a server runtime; static uploads cannot run its protected gateways. Use [current deployment guidance](docs/deployment/current-sandbox.md).

The `/demo-call` IBM embed is a separate legacy interface. [Lovable](https://lovable.dev/projects/5df751a6-a78b-4e1d-8847-de6364a53f63) remains a design/development surface, not the verified voice deployment. Preserve published Git history. Earlier designs, screenshots and procedures are labeled in the [documentation index](docs/README.md).

The primary backend submission checklist tracks remaining rehearsal, security review and submission decisions.
