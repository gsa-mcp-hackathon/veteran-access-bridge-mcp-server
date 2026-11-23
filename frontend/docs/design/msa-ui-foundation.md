# MSA UI foundation — Phase 1

## Current-encounter console — November 9
The current `/` replaces the permanent queue with a slim sandbox header, active-encounter strip and Handoff inbox. Desktop uses voice/transcript, scheduling/work and a docked private staff copilot in roughly 40/35/25 proportions. Closing the copilot reclaims width; tablets use two tracks with the copilot below, mobile stacks all sections. A/B/C retain direct transcript access with restrained desktop emphasis changes. Fourteen-pixel body text and twelve-pixel provenance use the existing VA tokens. Transcript Latest and partial/final fixtures remain local.

Routine verified primary-care replay now books autonomously after eligibility, selected-slot verification and Veteran confirmation. No routine MSA approval is required. `exception-approval` remains a separate fixture for legacy authorization/decline tests, not a routine gate. All five exception scenarios hide protected scheduling/work. Safe synthetic dialogue contains no DOB.

`encounter-work.ts` derives independent letter, note, summary and notification phases from encounter events. Letter generation follows the simulated booking; notes/summaries draft during the call, then finalize separately. Saving/recording and notification delivery are explicit in-memory simulations, never external writes. Draft previews are safe fixture content. Staff copilot answers are deterministic current-encounter responses, not a connected AI service. Mute/Hold explain unsupported local media; Monitor is local-only; Join opens guarded handoff review; End requires confirmation. No real call action is claimed.

Validation: 40 tests pass across six files; lint has zero errors and nine existing Fast Refresh warnings. Automatic build/TypeScript diagnostics report build OK (no manual build run). Chromium exercised autonomous booking, independent generated/finalized/queued artifacts, preview/delivery simulation, private staff chat, rail collapse/reopen, End confirmation, mismatch protection, accepted-versus-joined, all handoff edge scenarios and inbox filtering. Escape returned focus to the review opener. Captures at 1440×900, 768×1024 and 390×844 showed no horizontal viewport overflow and no browser page errors. `/` and `/design-system` rendered. Evidence: `/tmp/browser/current-console/{1440,768,390}-final-console.png`, `390-artifacts.png`, `390-private-chat.png`, `accepted-not-joined.png`, `human-handling.png`, `390-*-review.png` and `design-system.png`. Browser screenshots are temporary. No backend, publishing or canonical repository change. Live media, AI services, persistent audit, letter delivery and EHR integration remain absent. This is not WCAG certification; mobile uses document scrolling to reach scheduling/work/copilot, and compact eligibility lists scroll independently.

## Boundary
This Lovable Veteran Appointment Bridge repository is a frontend-only synthetic design exploration, not the canonical live `veteran-access-bridge` system. No production data, credentials, service connections, backend policy changes, publication or deployment are authorized. The canonical stack remains Next.js apps/web, Python FastAPI, governed MCP, IBM watsonx Orchestrate Avery and LiveKit/Deepgram.

The user-provided architecture references are:
- docs/plans/lovable-msa-ui-new-conversation-handoff-2026-11-08.md
- docs/plans/msa-primary-care-demo-workflow.md
- docs/architecture/canonical-ui-backend-boundary.md
- docs/plans/avery-live-voice-handoff-guardrails-msa-ui-2026-11-08.md

Those documents are in the separate canonical repository, not this checkout. Their full contents were not verified; this implementation follows the boundaries supplied in the approved brief, not newly inferred live contracts.

## Tokens
Official source: https://design.va.gov/foundation/color-palette, fetched for this checkpoint. Exact values are retained in `src/styles.css` as `--vads-*`. MSA aliases map surface, background, foreground, primary, muted text, semantic status and header roles to the palette. The light shell uses base-dark supporting text for AA contrast. The bounded conversation uses separate canvas/text/muted/highlight tokens; primary-alt is reserved for highlights on dark backgrounds. No seal, certification or VA endorsement is implied. Reduced motion disables animation.

## Screen map and source
- `/`: MSAAppShell → MSAHeader + DemoQueue + AveryPanel + Progress + RichConversation / Activity + Scheduling. At wide desktop queue/context flank the larger conversation; laptops move queue into a drawer, tablets/mobile use Radix queue/context overlays with focus trapping and Escape. Context visibility and A/B/C composition previews remain available.
- `/design-system`: exact palette/value/usage swatches, light/dark contrast specimens, typography, simulated voice/slot states and checkpoint notes.
- `src/components/msa/use-live.ts`: local scripted replay state. Existing workspace exports remain compatible; scheduling/approval stay in workspace.tsx.
- Conversation auto-scroll follows only near the bottom; otherwise New messages returns to the latest turn. Partial fixture uses one stable identity and replaces its partial content with final content rather than appending a duplicate.
- Queue: six explicitly synthetic fixtures; two replayable cases, four queue-only rows. Search, status filtering, sort and selection are local only.

## Safety and fixtures
Successful primary care replay preserves the synthetic approval demonstration. Verification-review candidate never marks identity verified and exposes no scheduling availability. UI readiness checks do not self-certify identity; they only reflect local fixture fields. Morning preference ranks eligible options; afternoon options remain eligible. Exclusion examples remain deterministic fixture closure/team evidence, not new production rules.

Tool evidence is observational synthetic execution, with safe parameters, result, source, correlation and fixture duration. Identity inputs are redacted in tool details. Fixture identities and clinics are invented and explicitly synthetic; no real facility is used for workspace identity.

## Known limitations / unverified live behavior
### UX acceptance polish
Onscreen branding is Veteran Access Bridge · MSA Operations. Scenario and concept selectors are in the collapsible **Demo controls** section; the global **Handoff inbox** remains visible. The direct **Conversation** action works in every A/B/C composition, including narrow screens; C retains a Scheduling action. Approval uses semantic secondary foreground/background pairing and one Radix close control, with focus returned to its opener. Calendar provider labels are width-constrained with full-name tooltips. Supporting provenance/status text is 12px, primary actions target 44px, and the compact Avery presence reduces mobile vertical weight. Completed appointment replay survives scenario switches.

No actual audio, chat, LiveKit room, Deepgram transcription, Orchestrate agent, governed MCP execution, identity verification, record write, reminder or persisted user session exists here. Pause/mute/join/end are local demonstrations. Replay timestamps and durations are fixture values, not measured telemetry. Complete local synthetic handoff now layers on this foundation; see `msa-handoff-prototype.md`. No live handoff integration is implemented. Declining clears selection/confirmation and returns to Select; retry requires restarting this demo. Panel resizing is deferred in favor of stable responsive grid tracks and context collapse. Concept previews use the common accessible shell rather than three separate applications.

## Verification
### November 9 acceptance polish validation
Vitest: 30 passing tests across five files. Lint: zero errors and nine existing Fast Refresh warnings. Automatic build/TypeScript diagnostics: build OK. Chromium checked 1440×900, 768×1024 and 390×844: C's direct Conversation action, mismatch boundaries across A/B/C, drawer focus trap/return, and ended-pending fallback closure passed at all sizes without horizontal overflow. Mobile success approval and decline, all five handoff scenarios, accept versus join, retained historical join after reconnect, voice partial/final count, and both routes passed. Decline computed #1b1b1b on #f0f0f0 (about 15.1:1), height 44px; one close control. Conversation begins inside the initial mobile/tablet viewport. No browser page errors were recorded.

Evidence is temporary under `/tmp/browser/msa-polish/`: `390-final-default.png`, `390-approval-final.png`, `390-recovery-final.png`, `1440-final-default.png`, `768-final-default.png`, `390-history-reconnect.png`, and `design-system-final.png`. This is Chromium interaction QA, not WCAG certification or a screen-reader audit. Full-name native tooltips supplement clipped calendar labels; touch users can use List for complete provider names. Desktop retains compact/truncated progress labels with title text. No manual build, deployment or canonical-system change was performed.

The following records describe the earlier Phase 1 checkpoint, not the current test count:
- Automatic harness build and TypeScript checks: latest entries report `build OK`.
- `bunx vitest run`: 11 tests passed across route and synthetic scheduling/replay suites.
- `bun run lint`: zero errors, nine existing-pattern Fast Refresh export warnings.
- Playwright: `/` and `/design-system` rendered; success replay reached approval and simulated booking, verification-review remained unverified/locked, MCP detail expanded, partial fixture finalized without duplicate turn, A/B/C rendered, end/restart reset session, queue filtering showed an empty result, conversation scrolling preserved position away from bottom and New messages returned to bottom.
- Viewports checked: 390px mobile, 768px tablet, 1280px laptop, 1536px desktop; no horizontal viewport overflow. Drawer Escape closed and queue trigger focus was restored. No browser page errors in the central flow.
- No manual application build, service connection, deployment or publication occurred. Live-system behaviors remain unverified by design.

## Second UX polish (visual acceptance follow-up)

- The full-width handoff inbox strip under the header was removed. The inbox is now one icon button in the header (label "Handoff inbox"). It shows a count badge only when a synthetic request needs attention, it can still be reached by keyboard at zero, and closing the drawer returns focus to it. The pending-request banner shows only while a request is open.
- The voice panel is more compact: caller and Avery each sit in one row, the visuals are 56px on phones and 72px on desktop, the repeated status line was removed and the call time moved into the controls row. All five controls keep 44px touch targets. At 1648×900, four transcript turns now show without scrolling. At 390×844 the tabs start at about 444px.
- Tab labels are short ("Transcript / Activity / Timeline") below 1280px and full at 1280px and up. Each tab keeps its full name for screen readers, and the tab row no longer scrolls sideways.
- Before verification, Avery's Work shows one "Waiting for verification" note instead of four blocked rows. The four documents appear, each with its own status, only after the verified fixture event. Mismatch and exception scenarios still show no protected documents.
- The encounter ID appears only in the header. The header status reads "SANDBOX · Scripted replay · NO LiveKit audio connection".
- Join is an outlined, disabled button until a synthetic handoff request exists, then becomes solid primary. End is an outlined destructive button, set apart from Hold, and still asks for confirmation.
- LiveKit limitation: the vendored Agents UI Aura has no audio track in replay, so it only shows its idle or disconnected state. No media connection exists.

## Final visual fidelity pass

- Desktop (1100px and wider): the voice card is about 279px tall. Each persona sits in a centered column, with the caller placeholder at 78px and the Aura at 84px. At 1648×900, 2–4 transcript turns show above the fold.
- Phones: the voice card is about 211px tall. The five controls sit in one row of icon-over-label buttons, each at least 44px tall. The transcript tabs start at about 356px on a 390×844 screen.
- Phone header: the brand shows in full as "Veteran Access Bridge" over "MSA Operations"; screen readers also hear the full encounter title.
- The repeated "Scripted replay · no LiveKit connection" line was removed from the voice panel. The header label and the Aura's accessible label still carry this disclosure.

## Authoritative LiveKit monitor (sandbox opt-in)

- **Default stays scripted replay.** Demo controls → "Connect sandbox…" opts in. Fixture dialogue, bookings, artifacts and staff chat are never shown in authoritative mode; panels show only projected backend status or "Awaiting authoritative evidence". Voice transcript shows "Voice transcript unavailable from authoritative source" (`transcript_verified=false`).
- **Unmerged canonical dependency:** requires `wbgreen0405/veteran-access-bridge` branch `feat/msa-authoritative-livekit-monitor-20261109` (monitor-token and monitor-events endpoints, disabled by default there too).
- **Same-origin gateway** `POST /api/msa-monitor` (`src/routes/api/msa-monitor.ts`), actions `token` / `events` only, fixed backend paths, strict ID/cursor validation, no CORS headers, `Cache-Control: no-store`. Returns 403 unless ALL server-only env are set:
  - `VAB_MSA_LIVE_MONITOR_ENABLED=true`
  - `VAB_MSA_MONITOR_SERVICE_KEY` (≥32 chars, never sent to the browser)
  - `VAB_MSA_OPERATOR_ACCESS_CODE` (≥32 chars, different from the service key)
  - `VAB_API_BASE_URL` (HTTPS unless localhost)
  The operator code is typed into a sheet, held in memory only, sent as `Authorization: Bearer` to the gateway, and compared in constant time. `X-Demo-Role/Actor/Case` are set server-side only.
- **This is NOT production MSA authentication.** Use only for local synthetic sandbox runs; never enable on a public deployment until real actor-bound auth exists.
- **Media:** `livekit-client` Room, subscribe-only token, no local publishing. Status reads "LiveKit connected" only after `RoomEvent.Connected`. Agent audio (participant kind AGENT or trusted `vab_role` metadata) is bound to the vendored Aura `audioTrack`; caller audio (`vab_role: veteran_caller`) drives a Web Audio analyser waveform; unknown participants are ignored. Monitor = local playback after a click. Mute/Join/Hold/End are disabled for the observer; only "Disconnect observer" exists.
- **Events:** polled every 2.5 s with no overlap; every page must match the token's interaction, case and first-seen correlation or the monitor fails closed; deduplicated by `event_id`; only tool name/status/call id/error code are projected.
- Live audio has **not** been verified end-to-end in this repo (no backend configured here).
