> Historical UI roadmap. Checkboxes below describe earlier prototype checkpoints, not current blockers. Call in Browser now connects to the trusted backend. See [current deployment](docs/deployment/current-sandbox.md) and remaining submission work.

# Phase 1 foundation
- [x] VA tokens, reusable operations shell, responsive navigation and queue.
- [x] Rich synthetic conversation, observational activity, consistent replay lifecycle.
- [x] Success and verification-review fixtures; preserve approval and scheduling gates.
- [x] Design-system checkpoint and boundary guide.
- [x] Verify routes, replay/approval, drawers, tests and available diagnostics; no deployment.

# Complete handoff prototype
- [x] Orthogonal synthetic state machine and six replay scenarios.
- [x] Consistent queue, global/sticky alerts, inbox, review/actions and safe scheduling boundary.
- [x] Separate accept/join, rejection, timeout, reconnect, race and local audit trace.
- [x] Transition/negative tests, browser validation, and future projection contract guide.

# UX acceptance polish
- [x] Fix mobile C conversation, approval contrast/close/focus, and ended/disconnected fallback closure.
- [x] Compact demo controls, readable labels, calendar fit, historical turns, queue projections and branding.
- [x] Update regression tests and design guides; validate all six scenarios and three viewport sizes without deployment.

# Current-encounter console
- [x] Three-column console, simulated voice controls, tall transcript, scheduling/work and docked private copilot.
- [x] Autonomous routine fixtures and independent artifact lifecycle; preserve exception handoff boundaries.
- [x] Update tests/docs, run tests/lint and inspect automatic diagnostics; browser-check three viewports and capture evidence.
# Private one-click demo call
- [x] Server-side trusted one-click gate (opt-in, loopback backend, Host/Origin allowlist) for /api/demo-call and /api/msa-monitor; keep operator-code path.
- [x] Start Demo Call / mic status / Hang Up on Command Center; auto-hand IDs to observer with bounded 409 retry; advanced fallback hidden.
- [x] Fix JWT >256 rejection; validate wss/room scope; release state on failure/hang-up; not-configured empty state.
- [x] Tests, docs; lint/type/unit/handshake/build.
- [ ] Two-sided live audio + real MCP calls — blocked: needs running Codespace backend and Avery worker.
