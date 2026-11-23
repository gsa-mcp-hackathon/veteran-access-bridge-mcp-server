> Historical procedure. For the latest verified images, reviewer access, configuration, and trusted LiveKit boundary, use [current sandbox deployment](../deployment/current-sandbox.md). Do not execute older image updates as the current release. Existing text is retained for traceability.

# IBM Code Engine — Avery synthetic call center

**Current Avery M6.4 native IBM embed deployment:** [Re-login and deploy from the one existing Codespace](../operations/avery-m64-codespace-ibm-cli-relogin-deploy.md). The sections below also preserve the older LiveKit call-center workflow for reference.

## Intent

Host the **existing** Lovable/GitHub TanStack Start frontend as a separate IBM
Code Engine application named `vab-avery-callcenter`. Keep the existing Python
Veteran Access Bridge backend, LiveKit/Deepgram voice worker, IBM watsonx
Orchestrate Avery, and MCP tools unchanged. This is an **unofficial, synthetic-only
demonstration**; no real Veterans, VA production systems, or booking.

**Brand:** Veteran Access Bridge / Avery Call Center. No Architonomy branding or
domain is required. Do not assume any third-party domain is registered.

## How this differs from Lovable hosting

- Lovable remains the UI editing environment; GitHub `main` is the deployed source.
- Code Engine runs the **TanStack Start SSR/API server** and its static assets.
- Only Node deployment builds set `VAB_DEPLOY_TARGET=code-engine` and
  `NITRO_PRESET=node-server`; Lovable keeps its own native build preset.
- The BFF routes `/api/demo-call` and `/api/msa-monitor` communicate with
  the existing backend over HTTPS. No IBM/LiveKit/Deepgram signing keys go
  into browser JavaScript or `VITE_*` variables.
- The browser receives a backend-issued, short-lived LiveKit **participant**
  token, never the LiveKit API secret.

## Security gate: read before deployment

The current hosted demo flow uses a **random 32+ character operator access code**
entered once in the browser. This is a temporary shared bearer code, **not
individual sign-in or VA staff authentication**. Share only with explicitly invited
synthetic-demo participants; do not use real patient data. Add identity-backed
login, user rate limiting, abuse controls, and actor scoping before broad public
usage. The Code Engine URL itself is public when ingress visibility is public.

The old unauthenticated one-click gate remains localhost/Codespace-only and
is deliberately **disabled** on a hosted Code Engine deployment.

Never enable the MSA observer gateway against a public backend relying only
on synthetic `X-Demo-Role` headers without a separate reviewed access-control
boundary. Voice activity and MCP/booking claims must remain source-verified.

## Prerequisites

1. IBM Cloud access to an existing **Code Engine project** and Code Engine CLI
   (`ibmcloud ce`); deployment is performed by an authorized account holder.
2. Backend `/health`, `/api/voice/status`, `/api/interactions`,
   `/api/voice-sessions`, and `/webrtc-token` available on a verified HTTPS
   IBM Code Engine endpoint running the compatible implementation.
3. Backend configured for synthetic-only voice, with LiveKit Cloud's browser-
   reachable `wss://` signaling URL, matching worker credentials, Deepgram
   and remote IBM Orchestrate; worker online. A status flag alone does not
   establish media readiness.
4. The private GitHub repository has GitHub Actions enabled with permission
   to publish GitHub Container Registry packages. This deployment path uses
   `--image` with the Code Engine registry pull secret rather than
   `--build-source`, which can fail when the IBM account cannot assign the
   automatically managed IBM Container Registry service-ID IAM policies.
5. Code Engine already has a GHCR registry secret `ghcr-veteran-access`, or
   you create a separate narrowly scoped GHCR pull secret for this frontend
   package. The existing secret must be authorized to read the **new frontend**
   GHCR package; a working pull for the backend package does not prove this.

## Set up server-only environment

In the **IBM Cloud console** under the selected Code Engine project's
**Secrets and configmaps**, create a **Generic** secret named
`vab-avery-callcenter-config` (name may be changed). Add:

- `VAB_MSA_MONITOR_SERVICE_KEY`: same distinct 32+ character service key
  as the *authorized synthetic backend* (do not create or reuse one blindly).
- `VAB_MSA_OPERATOR_ACCESS_CODE`: different, random 32+ character temporary
  code for invited synthetic-demo users.

Never store these values in GitHub, this guide, Lovable, `VITE_*`, image
build arguments, source files or logs. Add the backend's matching configuration
through its own private secret store; do not change backend production gates to
make this frontend build pass.

Set nonsecret **frontend runtime** variables:

| Variable | Value |
| --- | --- |
| `VAB_API_BASE_URL` | `https://<verified-VAB-backend-Code-Engine-host>` |
| `VAB_MSA_LIVE_MONITOR_ENABLED` | `true` to enable the existing BFF config gate (does *not* imply backend observer readiness) |
| `VAB_MSA_ONE_CLICK_DEMO_ENABLED` | `false` for public HTTPS hosting |

IMPORTANT: Existing `readGatewayConfig` currently makes the demo-call BFF
depend on valid monitor *frontend* configuration, even if backend observation
is not enabled. This is a legacy coupling, not a reason to expose observer
endpoints. A future dedicated call-center auth gate should remove that coupling.

## Publish via GitHub Container Registry (recommended)

IBM Code Engine source builds (`--build-source .`) ask IBM to create
managed Container Registry access and IAM policies. In some restricted IBM
accounts, this fails with:

```text
The permission to assign required policies to the service ID ... is insufficient.
```

**Do not request broader IAM just to deploy this demo, and do not retry
`--build-source` unchanged.** This repository has a separate GitHub Actions
workflow, `.github/workflows/publish-avery-callcenter.yml`, which builds
the already-tested Dockerfile and publishes to GHCR. GitHub's
`GITHUB_TOKEN` has `packages: write` only for that workflow; no IBM
Cloud permissions or application service secrets are needed during build.

On a push to `main` that changes the app or its build configuration, the
workflow publishes two tags:

```text
ghcr.io/wbgreen0405/veteran-appointment-bridge:avery-callcenter-<commit-SHA>
ghcr.io/wbgreen0405/veteran-appointment-bridge:avery-callcenter-latest
```

You can also run **Actions → Publish Avery Call Center image (GHCR) →
Run workflow** on `main`. Wait for a green result and confirm the package
is available before calling the IBM CLI. The workflow creates a **new private
frontend image** and does not replace the existing backend's GHCR image.

## Deploy the already-built image from the authenticated Codespace

Do not run `ibmcloud ce application create` if the new application exists.
Review possible IBM Code Engine charges and check the **target project**.

```bash
cd /workspaces/veteran-appointment-bridge
git switch main
git pull --ff-only

ibmcloud login --sso
ibmcloud target -g eid-6ac41f127818aff458d82ac8 -r ca-tor
ibmcloud ce project select --name ce-550000w6t0

ibmcloud ce registry list
ibmcloud ce secret list
ibmcloud ce application list

# Use the exact successful workflow commit; do not guess a tag.
IMAGE="ghcr.io/wbgreen0405/veteran-appointment-bridge:avery-callcenter-$(git rev-parse HEAD)"
CANARY_URL="https://veteran-access-bridge-m64-canary.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"

ibmcloud ce application create \
  --name vab-avery-callcenter \
  --image "$IMAGE" \
  --registry-secret ghcr-veteran-access \
  --port 8080 \
  --cpu 1 \
  --memory 2G \
  --min-scale 1 \
  --max-scale 1 \
  --env VAB_API_BASE_URL="$CANARY_URL" \
  --env VAB_MSA_LIVE_MONITOR_ENABLED=true \
  --env VAB_MSA_ONE_CLICK_DEMO_ENABLED=false \
  --env-from-secret vab-avery-callcenter-config \
  --wait

ibmcloud ce application get --name vab-avery-callcenter
```

The chosen canary is already deployed and reports LiveKit signaling
configured, but its last verified `/api/voice/status` returned
`browser_softphone_enabled=false`. **The hosted site can be deployed and
loaded, but Start Demo Call must remain unavailable until canary browser
voice is explicitly enabled with the correct backend voice worker and
authorization controls.** Do not change the main IBM Phone/SIP deployment.

The Code Engine CLI supplies the new public HTTPS URL when the app becomes
ready. Use the actual returned address; no custom DNS purchase is required.

If Code Engine fails to pull from GHCR, check the new GHCR package's
visibility/access and whether the `ghcr-veteran-access` registry
credential has package read permissions. Do not rotate an existing backend
registry secret casually. Create a separate read-only registry secret for
this frontend package if the current credential lacks access.

For later updates, publish a new image tag on `main`, then use:

```bash
ibmcloud ce application update \
  --name vab-avery-callcenter \
  --image "ghcr.io/wbgreen0405/veteran-appointment-bridge:avery-callcenter-<NEW_COMMIT_SHA>" \
  --wait
```

The built image uses Node.js 22, listens on port 8080, and contains the
Nitro `.output` server; it excludes local `.env` files. The GitHub CI
workflow previously verified the server HTTP startup and fail-closed API.
It does not verify Avery or LiveKit readiness.

## Temporary public guest-call mode (no caller access code)

This is **opt-in**, synthetic-only, and limited to `POST /api/demo-call`.
The existing `/api/msa-monitor` scheduler/observer endpoint still requires
the private operator code; no backend service key is sent to a browser.

The guest request must come from the exact configured HTTPS frontend origin
with the browser's same-origin fetch metadata and a custom guest header.
The frontend BFF restricts all calls to `DEMO-PC-VOICE-INTAKE-001`,
uses process-local limits (at most two concurrent guest sessions and eight
starts per hour), and returns a short-lived random capability token scoped to
that call for connect/end lifecycle updates.

**These limits are not durable, distributed anti-abuse protection**. Code
Engine restarts reset them; do not treat this as a public production
security control. Keep the demo synthetic; before wide public sharing add
edge rate limiting and cost budgets. Only use `--max-scale 1` for this
temporary demonstration.

Once the GitHub Actions GHCR publishing workflow for the updated `main`
commit succeeds:

```bash
cd /workspaces/veteran-appointment-bridge
git pull --ff-only

FRONTEND_URL="https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"
IMAGE="ghcr.io/wbgreen0405/veteran-appointment-bridge:avery-callcenter-$(git rev-parse HEAD)"

ibmcloud ce application update \
  --name vab-avery-callcenter \
  --image "$IMAGE" \
  --env VAB_PUBLIC_GUEST_CALL_ENABLED=true \
  --env VAB_PUBLIC_GUEST_ORIGIN="$FRONTEND_URL" \
  --wait
```

This **does not** enable browser voice on the canary. The separate canary
still reports `browser_softphone_enabled=false`, so the caller should see
a `Retry backend connection` state until the LiveKit worker, token
authorization, and canary softphone are verified and enabled. Never turn on
the canary switch solely to make the button appear enabled.

To switch off anonymous calls later without modifying the image:

```bash
ibmcloud ce application update \
  --name vab-avery-callcenter \
  --env VAB_PUBLIC_GUEST_CALL_ENABLED=false \
  --wait
```

To verify **public guest status without a call start**:

```bash
curl -sS -i "$FRONTEND_URL/api/demo-call" \
  -X POST \
  -H "Origin: $FRONTEND_URL" \
  -H "Sec-Fetch-Site: same-origin" \
  -H "X-VAB-Guest-Call: 1" \
  -H "Content-Type: application/json" \
  --data '{"action":"status"}'
```

Expect HTTP 200 with `backend_connected:true` and the canary's
actual `browser_softphone_enabled` flag. Cross-origin requests and
`/api/msa-monitor` without operator credentials must still reject.

## Smoke check, before inviting testers

1. Load the assigned default HTTPS URL. HTML must render.
2. Request `POST /api/demo-call` with `{"action":"status"}` and **no**
   operator code. Expect **403**, not a successful call.
3. Use the authorized synthetic demo code from the user-facing login form.
   Confirm the backend answers the status request, then click **Start Demo Call**.
4. Verify the browser joins the backend-created LiveKit room, publishes its
   microphone, hears Avery, and sees a reply to a synthetic scheduling request.
5. Verify actual IBM/MCP events in the backend event log and ensure no
   fabricated booking claims. If monitor access remains off, it must say so.
6. Test Hang Up, invalid code, unplugged worker, disconnected backend, and
   microphone permission denied. Check no secrets appear in the browser bundle
   or browser network response.
7. Only then invite limited testers. Keep the frontend and backend single-
   instance as needed for the current in-memory interaction/session state.

A green Node container build proves packaging, **not live voice connectivity**.

## Custom domain: optional, after the initial URL works

Preferred *branding examples* (availability and ownership **not verified**):

- `callavery.ai` — short, call-center oriented
- `veteranaccessbridge.ai` — project-oriented
- `avery.veteranaccessbridge.com` — subdomain, only if the root is owned

All are examples and must not imply an official U.S. VA website. Avoid
`architonomy` in the hostname. You can use IBM's generated URL while selecting
and registering a new domain.

Once you **own** a domain: obtain a trusted TLS certificate for the chosen host;
create Code Engine's domain mapping for `vab-avery-callcenter`; add the required
DNS CNAME at your registrar; and validate HTTPS. IBM supports editing domain
mappings later. Refer to
https://cloud.ibm.com/docs/codeengine?topic=codeengine-domain-mappings .

## Final verification for later rollout

- Frontend package CI verifies `NITRO_PRESET=node-server`, the SSR entry, and
  fail-closed API behavior without real server secrets.
- Do not deploy a new backend revision, enable production booking or change IBM
  Orchestrate/LiveKit/Deepgram configuration as part of frontend packaging.
- The new frontend is a **separate Code Engine app**, not a replacement for the
  deployed VAB backend. Do not route its custom domain to the backend app.
- For broader public access, replace the temporary shared code with actual
  user authentication and authorization and add request rate limits.
