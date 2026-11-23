# Avery browser demo rehearsal

Target length: **4 minutes 30 seconds**, with a five-minute hard stop. Presenter portrays the synthetic caller. Use the existing **Call in Browser** flow. Keep the MCP activity panel visible. No real personal information or production booking.

## Operator preflight

The single approved fresh rehearsal uses **VAB-DEMO-20261113-CASE-041**, synthetic patient **Gerry91 Torphy630**, birth date **May 21, 1967**. Before the call, confirm zero appointments for this case, an available attested slot and the canary's exact case binding. The selected rehearsal slot begins **November 25, 2026 at 10:00 a.m. Central / 16:00 UTC**. Avery must read the actual returned slot; this script does not authorize substituting a different option.

Do not repeat a completed booking. This rehearsal consumes the one-booking approval once an appointment exists. A later judged live booking needs another explicitly prepared unused fixture. Existing CASE-031 through CASE-039 bookings remain intact. Keep identity details on the presenter's cue sheet; the audience only needs to know they are synthetic.

Sign in to the existing reviewer login privately before screen recording. Do not display or dictate the reviewer code. Confirm the authenticated application appears, allow the microphone when asked, and close other active calls. Keep the current report and the independent IBM read trace ready in a second tab. Never show credentials, raw service exports, scope tokens or private trace files.

## Timed script

| Time | Presenter words and action | Expected evidence |
|---|---|---|
| 0:00–0:25 | “Veteran Access Bridge helps coordinate appointment access through a governed MCP server. I’m portraying a caller using synthetic data. This demonstration cannot book a real VA appointment.” Show the architecture's MCP boundary. | Clear mission and synthetic scope |
| 0:25–0:45 | “The server exposes 21 tools. Avery has 13 reviewed attachments. The server validates authority independently of what the model says.” Show the registry summary and click **Call in Browser**. | Actual connection and greeting; no fabricated tool activity |
| 0:45–1:20 | Caller: “I would like to schedule a Primary Care appointment.” When asked for a name, say “My name is spelled Golf Echo Romeo Romeo Yankee nine one, space, Tango Oscar Romeo Papa Hotel Yankee six three zero.” When asked for birth date: “May twenty-first, nineteen sixty-seven.” | Exact synthetic identity validation; no protected disclosure before identity |
| 1:20–2:00 | Wait for Avery's actual offer. “Please repeat the appointment date and time.” Avoid talking over Avery. Presenter: “The offer comes from returned synthetic scheduling evidence. The model cannot invent a slot.” | Current eligible option and caller-visible date/time |
| 2:00–2:30 | Only if the exact offer is suitable, caller: “Yes, book that appointment.” Speak continuously and clearly. Wait for the result. | Explicit current-call consent; signed worker/session binding; governed private commit |
| 2:30–3:00 | End the call and show the receipt. “We claim a booking only when the system returns a verified synthetic receipt. Here is the appointment identifier and the same-call evidence.” | Visible BOOKED_SIMULATED receipt. If missing, state that verification is pending |
| 3:00–3:40 | Show the separate recorded IBM read proof. “This booking lookup is host-invoked. In this independent read trial, IBM chose identity verification and two case-scoped MCP reads. Matching native tool IDs and server receipts establish who invoked them.” | Accurate distinction between agent selection and host booking authority |
| 3:40–4:10 | Show the evaluation scorecard. “89 contract checks and 53 adversarial argument checks passed. Five live attack prompts produced no prohibited MCP attempts, followed by three successful permitted reads. DeepEval scored one recorded read conversation 0.95.” | Separate denominators, bounded evidence, current release pins |
| 4:10–4:30 | “We also report failures and remaining risks: dependency advisories, untested concurrency and broader injection paths. The next stage is controlled hardening and operational validation.” | Honest limitations and close |

## Failure and timing rules

If identity fails, repeat the exact spelling once when Avery asks; never substitute another person's data or bypass the check. If availability is empty, explain that safe empty results are expected and do not claim a booking. If confirmation is ambiguous, answer Avery's clarification; do not send a direct booking request. If a result is uncertain, inspect persisted evidence before any retry.

At 3:00, if the live interaction has not completed, stop extending the planned scenario and use the clearly labeled recorded evidence for the remaining presentation. At the five-minute session deadline the browser disconnects automatically. Never present a recording as live. A call screenshot proves only what it visibly displays; an idle screen is not a receipt.

## After rehearsal

Record the actual duration, final voice/interaction IDs, receipt screenshot, one-appointment count and ordered identity/consent/booking evidence. Mark the case consumed. Save only sanitized metadata to GitHub. The presenter's live rehearsal and receipt observation remain pending until those checks complete.
