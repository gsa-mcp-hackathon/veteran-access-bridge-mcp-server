# Restricted reviewer login

The server entry can require reviewer sign-in before the application or any API is reachable. Call in Browser remains after login. This is a shared-code prototype gate, not individual accounts, MFA, government SSO or production identity proof.

Runtime settings (server-only): `VAB_REVIEWER_LOGIN_ENABLED=true`; `VAB_REVIEWER_ACCESS_CODE` in a protected Code Engine secret, random 32+ characters and different from operator/service credentials; `VAB_PUBLIC_GUEST_ORIGIN` equal to the exact existing HTTPS frontend origin. The reviewer cookie does not authorize staff/operator APIs or booking. Keep all existing gateway and identity/consent gates enabled.

Use the existing frontend application and secret workflow. Enter the code privately in IBM; never put it in chat, CLI history, GitHub, an image build argument or a VITE_/NEXT_PUBLIC_ variable. Missing/invalid configuration with login enabled returns 503. Do not activate with the test credentials from CI.

Sessions last one hour, are process-local, and clear on restart. Sign out revokes the session. Rotating the reviewer code invalidates existing sessions. Login is capped at ten attempts per minute globally and 32 sessions. This is a small restricted demo, not distributed abuse protection. Sign out after the call ends; start a fresh login before rehearsal if the session is old.

Release checks: Linux CI and actual Docker login smoke test; anonymous root redirects to /login; anonymous /api/demo-call returns 401; valid login shows Call in Browser; logout rejects the previous cookie; existing call and receipt gates remain. Do not consume the one approved CASE-041 booking during access checks.

Login restricts access but does not itself satisfy GSA's non-public-deployment language. Confirm the accepted reviewer-hosting arrangement with organizers before submission.

## Verified reviewer rollout - November 15, 2026

Frontend revision `vab-avery-callcenter-00019` runs image `ghcr.io/wbgreen0405/veteran-appointment-bridge@sha256:9bd7ed3ca09d5bae5111554c85736786566475591173739fc64dcb69682c725c` (source `f5ae0717c54fe79703f951e5abe0d26fc5e30530`; publication run 43751203560). Reviewer login is enabled. Anonymous page redirect and API denial, valid sign-in, secure cookie, authenticated session/application, logout and logout replay denial all passed at 19:40 UTC. Existing secret references were retained; secret values are excluded from evidence. Backend and worker specifications are unchanged. No voice call or booking was attempted; CASE-041 rehearsal remains deferred.

[Open restricted reviewer login](https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/login). Hosting approval remains a separate submission gate. Rollback must retain access restriction or take the demo offline.
