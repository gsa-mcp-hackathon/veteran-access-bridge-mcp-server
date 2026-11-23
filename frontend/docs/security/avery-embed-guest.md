# Secure Avery M6.4 guest embed — staged, disabled by default

**Status:** Code review gate only. This branch is NOT deployed, does NOT turn on
public IBM embedded voice, and does NOT disable IBM Embed Security.

## Purpose

The public Veteran caller is allowed to request a short-lived, signed IBM
embed identity for **synthetic-only** scheduling conversations. The guest does
not need to type a password; the private IBM signing key never leaves the
VAB backend. This does not authorize access to VA records or a real
appointment. The MSA monitor stays separately protected.

IBM recommends RS256 JWTs with a unique `sub`, an expiration, and a public
key registered at Orchestrate Settings > Embed Security. Voice uses the same
JWT mechanism as text. **Leave Embed Security on.**

## Trust boundary

```text
Browser on exact HTTPS guest origin
  POST /api/avery-embed-token {}
  Origin, Sec-Fetch-Site: same-origin, X-VAB-Guest-Embed: 1
      |
      v
Frontend server-only BFF
  - explicit disabled-by-default flag
  - HTTPS, origin+host check, no Authorization from browser
  - signed, 1-hour HttpOnly Secure SameSite=Strict session cookie
  - quota: 6 new guests/h, 24 tokens/h, 8 tokens/guest/h (process-local)
  - sends only random opaque guest session ID with private bearer secret
      |
      v
VAB canary POST /api/orchestrate/guest-embed-token
  - different 32+-character server-only VAB_EMBED_TOKEN_SERVICE_KEY
  - explicit disabled-by-default VAB_EMBED_GUEST_ENABLED=true
  - exact guest_session_id validation; never browser-controlled case/actor
  - RS256 JWT signed using existing ORCHESTRATE_EMBED_PRIVATE_KEY_B64
  - unique stable `sub=synthetic-guest:<opaque-session-id>`
  - 10-min exp (configurable 60-900 seconds); no-cache response
      |
      v
IBM M6.4 Live embedded chat/voice (IBM Embed Security ON)
```

The browser may receive its own signed, expiring IBM JWT. It must NEVER
receive either the signing private key or backend bearer secret.
No service credential should be placed in any VITE_* variable or browser JS.

## Secret deployment contract (NOT applied)

Generate separate random secrets using your approved secret manager:

- Backend Code Engine canary:
  - `VAB_EMBED_TOKEN_SERVICE_KEY` — new private 32+ random character service bearer.
  - `VAB_EMBED_GUEST_ENABLED=false` until acceptance.
  - Existing `ORCHESTRATE_EMBED_PRIVATE_KEY_B64` remains in its current IBM
    Code Engine secret, matching the public key registered with IBM.
- Frontend Code Engine callcenter:
  - the SAME `VAB_EMBED_TOKEN_SERVICE_KEY` only in a server-side Code Engine secret;
  - `VAB_EMBED_GUEST_COOKIE_KEY` — a DIFFERENT 32+ random secret;
  - `VAB_PUBLIC_AVERY_EMBED_ORIGIN` — exact public HTTPS frontend origin;
  - `VAB_PUBLIC_AVERY_EMBED_ENABLED=false` until acceptance;
  - existing `VAB_API_BASE_URL` points at the intended canary.
- Do not put any of these in GitHub, web responses, screenshots, or telemetry.

**Migration:** The legacy `GET /api/orchestrate/embed-token` also requires
`VAB_EMBED_TOKEN_SERVICE_KEY` once the backend PR is deployed. Existing
internal embedded-chat clients must be updated to supply the server-only
bearer credential, not a browser-supplied header.

## Integration contract (future UI PR)

The Veteran client can request a JWT only from the same-origin gateway with
`fetch("/api/avery-embed-token", { method: "POST", headers: {
"Content-Type": "application/json", "X-VAB-Guest-Embed": "1" },
body: "{}" })`. Use the `identityToken` with the IBM widget's supported
initial-token and `identityTokenExpired` refresh API. **Do not log it or
persist it into localStorage.** Do not assume that the custom Start Call button
can directly initiate IBM native voice without an IBM-supported API.

## Release blockers (must pass before enabling)

1. Backend RS256 signature verification with IBM's registered public key;
   same guest cookie refresh returns same JWT `sub`; different guests have
   different subjects.
2. Missing/incorrect secret, spoofed demo headers, cross-origin requests,
   invalid sessions, excess quotas fail closed.
3. Confirm M6.4 Live agent is restricted to approved synthetic MCP cases,
   read-only or governed simulated writes, and no PHI or production VA access.
4. Add **edge/distributed rate limits** and independent abuse protection:
   process-local quotas reset on restart and Host/Origin headers can be
   fabricated by non-browser clients. This route is NOT general public auth.
5. Validate IBM Embed Security enabled with matching RS256 public key, Live
   voice enabled, HTTPS microphone controls, and valid token refresh.
6. Verify separately authenticated MSA access. A JWT is NOT a substitute for
   Veteran eligibility or scheduler authorization.

Rollback: leave the two embed enable flags false or undeploy the candidate
revisions. Do not modify working LiveKit or Orchestrate deployments for this PR.
