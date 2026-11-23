---
title: Avery Scheduling Demonstration
hide:
  - toc
---

<div class="vab-demo vab-demo-reference">
  <header class="vab-demo-hero">
    <div class="vab-demo-hero-copy">
      <div class="vab-demo-eyebrow">ONE VETERAN. ONE CONVERSATION. CONNECTED CARE.</div>
      <h1>Avery Scheduling Demonstration</h1>
      <p>Watch a verified synthetic Primary Care scheduling journey — not a live VA appointment.</p>
    </div>
    <div class="vab-demo-meta" aria-label="Recording details">
      <span>▦ &nbsp; Final demonstration call</span>
      <span>◷ &nbsp; 3 min 39 sec</span>
      <span>◇ &nbsp; Synthetic demo</span>
    </div>
  </header>

  <section class="vab-demo-stage" aria-label="Demonstration video and call chapters">
    <div class="vab-demo-video-card">
      <video id="avery-demo-video" controls playsinline preload="metadata" poster="../assets/avery-demo-poster.jpg" aria-label="Recorded Avery Primary Care synthetic scheduling demonstration">
        <source src="../assets/avery-demo.mp4" type="video/mp4">
        <p>Video playback is unavailable. <a href="../assets/avery-demo.mp4">Open the recorded MP4</a>.</p>
      </video>
      <div class="vab-demo-video-foot"><span>Synthetic Primary Care call · appointment booked for Dec 4, 2026</span><a href="../assets/avery-demo.mp4">Open full video ↗</a></div>
    </div>
    <div class="vab-demo-chapter-card" id="chapters">
      <div class="vab-demo-card-heading"><h2>☷ &nbsp; Call chapters</h2><span>Follow the conversation</span></div>
      <div class="vab-demo-chapters">
        <details open><summary><span class="vab-demo-number">01</span><span><strong>Greet</strong><small>Identify the Primary Care scheduling request</small></span></summary><p>Synthetic caller describes the request. This begins the conversation but does not establish booking authority.</p></details>
        <details><summary><span class="vab-demo-number">02</span><span><strong>Verify</strong><small>Trusted caller and case-scoped identity</small></span></summary><p>Trusted host verifies the caller and binds the case/session. The model cannot assert identity authority.</p></details>
        <details><summary><span class="vab-demo-number">03</span><span><strong>Retrieve</strong><small>Permitted patient context and knowledge</small></span></summary><p>IBM-selected tools retrieve scoped patient context and supporting knowledge. Retrieved text grants no privileges.</p></details>
        <details><summary><span class="vab-demo-number">04</span><span><strong>Search &amp; select</strong><small>Find available options and choose one</small></span></summary><p>Avery offered two verified options (Thursday, Dec 3 at 10 AM and Friday, Dec 4 at 9 AM CST) using <code>search_call_appointments</code>; the caller chose Friday, captured with <code>select_call_appointment</code>. Selecting a slot is not booking it.</p></details>
        <details><summary><span class="vab-demo-number">05</span><span><strong>Confirm</strong><small>Read back the exact appointment option</small></span></summary><p>The host read back the selected time and obtained a separate, current caller confirmation. Consent and policy are enforced by trusted services.</p></details>
        <details><summary><span class="vab-demo-number">06</span><span><strong>Book &amp; wrap up</strong><small>Commit a governed synthetic booking</small></span></summary><p>IBM selected <code>book_call_appointment</code>, which requests a booking. Trusted backend services verified identity, current consent, slot and policy before committing it, then confirmed the appointment by independent database readback. After hang-up, the trusted booking service saved a CRM note and generated a confirmation letter (not sent).</p></details>
      </div>
      <p class="vab-demo-chapter-disclaimer">Key moments: about 2:00 patient-health read · 3:12 booking confirmed with independent readback · 3:36 wrap-up complete.</p>
    </div>
  </section>

  <section class="vab-demo-tool-card" id="tool-activity" aria-label="MCP tools in action">
    <div class="vab-demo-tool-intro"><h2>⌘ &nbsp; MCP tools in action</h2><p>A trusted voice service verified the caller first. IBM then selected four MCP tools: <code>get_va_patient_health_sandbox_summary</code> and the scheduling sequence shown here. The call recorded seven tool calls in total.</p></div>
    <div class="vab-demo-tool-content">
      <div class="vab-demo-tool-tags"><span>Patient context</span><span>Knowledge</span><span>Scheduling</span><span>Protected booking</span></div>
      <div class="vab-demo-flow-label">Scheduling tool activity (in order)</div>
      <div class="vab-demo-toolflow">
        <div><b>1</b><span><code>search_call_appointments</code><small>Find permitted options</small></span></div>
        <i aria-hidden="true">→</i>
        <div><b>2</b><span><code>select_call_appointment</code><small>Capture the selected option</small></span></div>
        <i aria-hidden="true">→</i>
        <div><b>3</b><span><code>book_call_appointment</code><small>Request a governed booking</small></span></div>
      </div>
    </div>
  </section>

  <section class="vab-demo-bottom" aria-label="Recorded outcome, safety, and original evidence">
    <div class="vab-demo-bottom-card vab-demo-outcome" id="outcome"><h2>✓ &nbsp; Verified outcome</h2><div class="vab-demo-outcome-grid"><div><strong>1</strong><small>Synthetic appointment</small></div><div><strong>Verified</strong><small>Independent database readback</small></div><div><strong class="vab-demo-receipt">51976dfb…</strong><small>Synthetic confirmation</small></div></div></div>
    <div class="vab-demo-bottom-card vab-demo-boundaries"><h2>♢ &nbsp; Trusted boundaries</h2><p>Identity, case scope, consent, and booking authority remain controlled by trusted services—not agent-generated prose.</p><div class="vab-demo-checks"><span>✓ Identity</span><span>✓ Scope</span><span>✓ Consent</span><span>✓ Booking</span></div></div>
    <div class="vab-demo-bottom-card vab-demo-evidence"><h2>↗ &nbsp; Review the proof</h2><a href="https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/docs/operations/avery-agent-led-scheduling-20261116.md">Earlier accepted trial (Nov 16) ↗</a><a href="https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/docs/evaluation/agent-led-voice-20261116.json">Nov 16 evidence JSON ↗</a><a href="../developer-guide/local-mcp-server/">Reproduce safe local read ↗</a></div>
  </section>

  <aside class="vab-demo-banner"><strong>Final demonstration call.</strong> Synthetic case DEMO-PC-VOICE-INTAKE-001; Primary Care appointment Friday, December 4, 2026, 9:00 AM CST, at Colmery-O'Neil VA Medical Center; synthetic confirmation 51976dfb-30da-5f04-a628-e9ca1ec31fd9. The same call appears on presentation slides 10–11. An earlier accepted trial (Nov 16, CASE-047, backend 00037) is documented separately. Synthetic only, not a live VA booking; do not replay a historical protected write.</aside>

  <div class="vab-demo-followup"><details><summary>Try a read-only MCP example</summary><p>Use the Developer Guide to call <code>get_scheduling_encounter</code> with a synthetic fixture. This does not reproduce the archived booking.</p><pre><code>{"name":"get_scheduling_encounter","arguments":{"case_id":"DEMO-CARD-5000335-001"}}</code></pre></details><a href="../evaluation/">See the Evaluation Command Center →</a><a href="../mcp-implementation/">Explore MCP Implementation →</a></div>
</div>
