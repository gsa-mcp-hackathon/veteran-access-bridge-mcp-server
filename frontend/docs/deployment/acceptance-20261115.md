> Historical acceptance snapshot. For current revision 00019 and reviewer login, use [the deployment inventory](current-sandbox.md). This trial was not rerun by the later frontend rollout.

# Deployed Avery acceptance — November 15, 2026

The existing IBM Code Engine frontend `vab-avery-callcenter` is revision `00017`, using image `ghcr.io/wbgreen0405/veteran-appointment-bridge:avery-callcenter-c9e6d98eb08db3ec77e08052eb07c6d227c5ddd9`. Environment settings were unchanged by the image update. **Call in Browser** remains available.

[Open the deployed interface](https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud/).

The existing backend canary is revision `00022`, image `fe780af6eefffd4692de5da32c915dd566e731d0`, with the strict Avery context gate and approved synthetic CASE-039 binding. The existing voice worker was retained. Do not switch this consumed case to a new booking without a fresh authorized fixture.

One real LiveKit synthetic call through `/api/demo-call` created exactly one CASE-039 appointment. Its authorized activity response contained the verified, call-bound receipt. Independent database checks confirmed identity/consent ordering and unchanged earlier bookings. The call took 84.34 seconds under controlled generated-audio conditions.

The receipt component passed automated tests before deployment; all 130 frontend tests, type checking and production build passed. The deployed UI was inspected visually in its idle state. A completed receipt was not observed inside an actual browser call during this run; distinguish the verified API receipt from that remaining visual acceptance check.

The backend still exposes 21 MCP tools. Avery has 13 reviewed attachments. Final A25–A27 traces each showed zero MCP calls. The booking lookup was host-invoked, so this is not evidence of agent-selected case-scoped reads or completion of the full current-release evaluation suite.

Detailed acceptance evidence.
