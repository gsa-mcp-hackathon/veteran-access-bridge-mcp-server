# Security follow-up and restricted reviewer access

November 15, 2026. Frontend candidate `803460ae73ff2d6deb256d3a2f16233a015a4c00`. The subsequent accepted rollout is revision 00019 from source f5ae071; see the verified rollout section below. These changes do not replace the earlier release evidence.

## Implemented and tested

- Both `/api/demo-call` and `/api/msa-monitor` now read at most 16 KiB before JSON parsing. Actual streamed bytes are counted even when Content-Length is absent or dishonest. A ten-second read deadline cancels stalled input. Unsupported compression, malformed JSON and invalid UTF-8 fail closed. Authorization still runs first; oversized requests never call the backend.
- The new reviewer landing/login page is enforced at the server entry before app routing. Anonymous pages redirect to `/login`; protected APIs return 401. A separate 32+ character reviewer code must differ from the staff/operator and service credentials. The code is never stored in browser storage.
- Successful sign-in issues an opaque Secure, HttpOnly, SameSite=Strict cookie. Only its hash is retained server-side; sessions expire after one hour, logout revokes them, and code changes invalidate them. Same-origin login/logout checks, bounded request parsing, ten login attempts per minute and a 32-session cap apply. Process restarts clear sessions; rate limits are process-local and not distributed abuse protection.
- Reviewer access grants UI access only. Existing caller identity, case scope, explicit consent, signed worker assertions and booking gates are unchanged. Call in Browser remains after login. Signing out is disabled while a call is active.

Validation: 150 frontend tests pass, including 12 body-limit tests and six reviewer-gate tests; typecheck and Code Engine Node build pass. The actual built HTTP server passed anonymous denial, wrong-code rejection, cross-origin denial, valid login, authenticated UI and logout replay rejection with dummy credentials and no backend connection. The earlier body-limit candidate also passed Linux CI and deployment Docker checks. Linux CI and the actual login-container checks passed before the verified rollout.

An initial parallel local test run hit the existing five-second dynamic-import timeout; the unchanged assertion passed with two workers. Windows full-tree lint reported checkout CRLF violations; changed-source lint passed, with clean Linux CI used for full-tree validation. Failures are not erased from the record.

## Dependency triage

The original frontend audit had 11 affected package groups. Targeted updates patched Vite 8.3.8, Vitest 4.1.12, Zod 4.6.7, Seroval 1.8.1, shell-quote 1.12.0, launch-editor 2.14.2 and compatible transitive fixes. Direct application source contains no Zod import; its major-version update still passed types, tests and build. Bun retained its verified lockfile and TLS verification used existing Windows trusted roots.

The new audit retains one moderate advisory: minimatch 10.2.6, pulled by the development-only `@typescript-eslint/typescript-estree`. The current upstream package still requires ^10.2.2; a blanket override to 11 would also affect ESLint's separate 3.x API. No minimatch/globparts, shell-quote or launch-editor match was found in the produced server tree; Seroval is present and updated. This is source/build reachability evidence, not a scan of the deployed container. Keep the lint dependency finding open until upstream remediation or a narrowly tested compatibility change.

Backend: fastmcp 2.14.7 and diskcache 5.6.3 findings remain in the pinned image. The application uses custom bearer authentication and no OAuthProxy configuration. The installed FastMCP source scan found DiskStore only in `server/auth/oauth_proxy.py`; this narrows the observed path but does not prove all transitive cache use absent in the deployed image. The Windows CLI-install advisory does not describe the Linux server execution path. Do not call these packages patched or the release vulnerability-free. A FastMCP 3.x migration requires separate transport, scope, tool-schema and agent compatibility acceptance. Reproducible backend dependency locking and a container SBOM remain open.

## Still open

1. Completed: private reviewer code configuration, container checks and the existing-frontend rollout. Nine HTTPS access/session checks passed; backend and voice worker stayed unchanged. The user subsequently confirmed login worked.
2. A login page restricts use but does not make internet hosting private or establish GSA approval. Confirm the organizers' accepted reviewer-access arrangement and submission instructions.
3. Wider adversarial scenarios, real-database concurrency, uncertain-write recovery, tool-result injection, poisoning, cross-MCP and SSRF coverage remain partial. No general security certification or aggregate pass percentage is claimed.
4. CASE-041 remains unbooked; final receipt rehearsal is deliberately deferred by the user.

Evidence: [candidate manifest and results](evidence/security-followup-20261115/). Prior measurements: [release report](release-closeout-20261115.md).

Sources: [GSA scope](https://www.gsa.gov/super-intelligence/si-community-of-practice/events-and-training/mcp-server-and-si-agent-government-hackathon), [shell-quote advisory](https://github.com/advisories/GHSA-pqg4-j6r4-53mv), [Zod advisory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5), [remaining minimatch advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249).

## Verified reviewer rollout - November 15, 2026

Frontend revision `vab-avery-callcenter-00019` runs image `ghcr.io/wbgreen0405/veteran-appointment-bridge@sha256:9bd7ed3ca09d5bae5111554c85736786566475591173739fc64dcb69682c725c` (source `f5ae0717c54fe79703f951e5abe0d26fc5e30530`; publication run 43751203560). Reviewer login is enabled. Anonymous page redirect and API denial, valid sign-in, secure cookie, authenticated session/application, logout and logout replay denial all passed at 19:40 UTC. Existing secret references were retained; secret values are excluded from evidence. Backend and worker specifications are unchanged. No voice call or booking was attempted; CASE-041 rehearsal remains deferred.

[Open restricted reviewer login](https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/login). Hosting approval remains a separate submission gate. Rollback must retain access restriction or take the demo offline.
