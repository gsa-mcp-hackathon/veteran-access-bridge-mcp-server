> Historical procedure. For the latest verified images, reviewer access, configuration, and trusted LiveKit boundary, use [current sandbox deployment](../deployment/current-sandbox.md). Do not execute older image updates as the current release. Existing text is retained for traceability.

# Avery M6.4 Live — inline IBM chat and native voice (sandbox)

**Purpose:** Let a guest open the existing Veteran Access Bridge site, click
**Talk with Avery**, then speak using IBM's native voice control in an always-
visible embedded conversation. No LiveKit worker is needed for this Veteran
text/voice proof of concept; existing LiveKit and MSA observer implementations
remain available separately. **Only synthetic appointment data.**

**Start here after reopening Codespaces:** [IBM Cloud + watsonx Orchestrate CLI re-login and exact M6.4 sandbox deployment commands](../operations/avery-m64-codespace-ibm-cli-relogin-deploy.md). This runbook is mirrored in both repositories.

## What is implemented

- `/` remains the existing MSA command center, with a **Talk with Avery** link
  rather than a misleading LiveKit voice-readiness button.
- `/demo-call` is the Veteran-facing chat/voice page, using the same VA-navy,
  light-panel styling and the real Live `veteran_access_agent_m64` IBM ID
  `b38da637-92e4-4c5c-9c7e-d4f8dce28160`.
- The IBM widget renders with `layout.form: "custom"` into a visible host
  element, uses `skin: "next"`, hides the standard IBM header and launcher
  with `instance.changeView({ launcher: false, mainWindow: true })`.
  No floating chatbot icon.
- Clicking **Start with Avery** gets a short-lived JWT from the same-origin
  `POST /api/avery-embed-token` gateway. The backend RS256 private key and
  bridge service key never enter browser code; IBM Embed Security remains ON.
- The `authTokenNeeded` event refreshes the expiring token through the same
  secure cookie-scoped endpoint; refresh preserves the guest subject.
- **Voice control is IBM native.** There is no supported public IBM API to
  force microphone start from our custom button, so use IBM's microphone
  control inside the inline panel. The button opens the conversation.

## Sandbox rollout (not performed by GitHub merge)

1. Verify Live M6.4 agent is published, has a working native voice
   configuration, and the **Live Embedded agent voice** toggle is enabled.
   Verify an actual spoken M6.4 MCP test in the IBM preview.
2. In IBM Orchestrate **Settings > Embed Security**, leave security enabled.
   Confirm the registered public RSA key corresponds to the private
   `ORCHESTRATE_EMBED_PRIVATE_KEY_B64` already held by the Code Engine canary.
   Do not share, paste, or commit either key.
3. In IBM Code Engine project `ce-550000w6t0`, create one distinct
   `VAB_EMBED_TOKEN_SERVICE_KEY` (32+ random characters) in a private secret
   attached to **both** the M6.4 canary and `vab-avery-callcenter`.
   The two applications must receive the **same** value. Do not reuse the
   MSA operator code, LiveKit secret, or signing key.
4. Attach an independent 32+ character `VAB_EMBED_GUEST_COOKIE_KEY`
   in a **frontend-only** secret.
5. Deploy the new backend image containing PR #182 and the new frontend image
   containing this UI change. On the IBM Code Engine applications set:
   - **Canary:** `VAB_EMBED_GUEST_ENABLED=true`;
     `VAB_EMBED_GUEST_TOKEN_TTL_SECONDS=600` (optional).
   - **Call center:** `VAB_PUBLIC_AVERY_EMBED_ENABLED=true`;
     `VAB_PUBLIC_AVERY_EMBED_ORIGIN=https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud`;
     `VAB_API_BASE_URL` must point to the M6.4 canary.
   - Neither of these should ever be `VITE_*` variables. Do not touch
     the main `veteran-access-bridge` production app.
6. Verify login-free sandbox flow in a fresh browser profile:
   open `https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/demo-call`;
   click **Start with Avery**, confirm inline conversation and no floating
   launcher; use native voice; test a synthetic primary-care scheduling
   request and see the actual MCP tool call in IBM trace. Check the MSA
   workspace separately, without claiming a synchronized voice transcript.

## Smoke checks

```bash
# Read-only app inventory; no secrets displayed by these list commands.
ibmcloud ce application list
ibmcloud ce secret list

CALLCENTER="https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"
CANARY="https://veteran-access-bridge-m64-canary.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"
curl -si "$CALLCENTER/demo-call" | head -n 12
curl -sS "$CANARY/api/voice/status" | python -m json.tool
```

**Do not expect `browser_softphone_enabled=true`.** This uses IBM native
embedded voice and no longer depends on the separate LiveKit browser
softphone flag. A 403 from the embed token BFF before configuration is
expected and is a safe fail-closed result.

## Boundaries

- This is a synthetic demonstration, not VA production scheduling or identity.
- Native IBM voice events are **not** automatically synchronized into the
  MSA's LiveKit observer track or authoritative transcript. Do not invent
  events, booking receipts, or call-connected indicators.
- A signed IBM identity token grants a guest conversation, not clinical
  identity or scheduler privileges.
- Preserve the existing backend booking approval checks and no-production-
  write safeguards. Keep MSA-only monitoring behind its operator gate.
- If a guest gets 403, verify the two separate enable flags, same value
  of the service key, and exact HTTPS origin **without printing secrets**.
- Roll back by setting either embed enable flag to `false` or reverting
  the frontend image. Existing LiveKit code is unchanged.
