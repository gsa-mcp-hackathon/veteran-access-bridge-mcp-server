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
      <span>▦ &nbsp; Recorded Nov 16, 2026</span>
      <span>◷ &nbsp; 3 min 36 sec</span>
      <span>◇ &nbsp; Synthetic demo</span>
    </div>
  </header>

  <section class="vab-demo-stage" aria-label="Demonstration video and call chapters">
    <div class="vab-demo-video-card">
      <video id="avery-demo-video" controls playsinline preload="metadata" poster="../assets/avery-demo-poster.jpg" aria-label="Recorded Avery Primary Care synthetic scheduling demonstration">
        <source src="../assets/avery-demo.mp4" type="video/mp4">
        <p>Video playback is unavailable. <a href="../assets/avery-demo.mp4">Open the recorded MP4</a>.</p>
      </video>
      <div class="vab-demo-video-foot"><span>Recorded synthetic call · November 16, 2026</span><a href="../assets/avery-demo.mp4">Open full video ↗</a></div>
    </div>
    <div class="vab-demo-chapter-card" id="chapters">
      <div class="vab-demo-card-heading"><h2>☷ &nbsp; Call chapters</h2><span>Follow the conversation</span></div>
      <div class="vab-demo-chapters">
        <details open><summary><span class="vab-demo-number">01</span><span><strong>Greet</strong><small>Identify the Primary Care scheduling request</small></span></summary><p>Synthetic caller describes the request. This begins the conversation but does not establish booking authority.</p></details>
        <details><summary><span class="vab-demo-number">02</span><span><strong>Verify</strong><small>Trusted caller and case-scoped identity</small></span></summary><p>Trusted host verifies the caller and binds the case/session. The model cannot assert identity authority.</p></details>
        <details><summary><span class="vab-demo-number">03</span><span><strong>Retrieve</strong><small>Permitted patient context and knowledge</small></span></summary><p>IBM-selected tools retrieve scoped patient context and supporting knowledge. Retrieved text grants no privileges.</p></details>
        <details><summary><span class="vab-demo-number">04</span><span><strong>Search &amp; select</strong><small>Find available options and choose one</small></span></summary><p>Two verified options were returned using <code>search_call_appointments</code> and <code>select_call_appointment</code>. Selecting a slot is not booking it.</p></details>
        <details><summary><span class="vab-demo-number">05</span><span><strong>Confirm</strong><small>Read back the exact appointment option</small></span></summary><p>The host read back the selected time and obtained a separate, current caller confirmation. Consent and policy are enforced by trusted services.</p></details>
        <details><summary><span class="vab-demo-number">06</span><span><strong>Book &amp; wrap up</strong><small>Commit a governed synthetic booking</small></span></summary><p>IBM selected <code>book_call_appointment</code>. Backend policy gates produced one persisted synthetic appointment and one host-written CRM note.</p></details>
      </div>
      <p class="vab-demo-chapter-disclaimer">Stages describe the archived call; exact seek timestamps have not been verified.</p>
    </div>
  </section>

  <section class="vab-demo-tool-card" id="tool-activity" aria-label="MCP tools in action">
    <div class="vab-demo-tool-intro"><h2>⌘ &nbsp; MCP tools in action</h2><p>Five distinct IBM-selected MCP tool types were observed in the accepted call. The scheduling sequence is shown here.</p></div>
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
    <div class="vab-demo-bottom-card vab-demo-outcome" id="outcome"><h2>✓ &nbsp; Verified outcome</h2><div class="vab-demo-outcome-grid"><div><strong>1</strong><small>Synthetic appointment</small></div><div><strong>1</strong><small>Host-written CRM note</small></div><div><strong class="vab-demo-receipt">BOOKED_SIMULATED</strong><small>Persisted synthetic receipt</small></div></div></div>
    <div class="vab-demo-bottom-card vab-demo-boundaries"><h2>♢ &nbsp; Trusted boundaries</h2><p>Identity, case scope, consent, and booking authority remain controlled by trusted services—not agent-generated prose.</p><div class="vab-demo-checks"><span>✓ Identity</span><span>✓ Scope</span><span>✓ Consent</span><span>✓ Booking</span></div></div>
    <div class="vab-demo-bottom-card vab-demo-evidence"><h2>↗ &nbsp; Review the proof</h2><a href="https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-agent-led-scheduling-20261116.md">Acceptance report ↗</a><a href="https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/agent-led-voice-20261116.json">Evidence JSON ↗</a><a href="../developer-guide/local-mcp-server/">Reproduce safe local read ↗</a></div>
  </section>

  <aside class="vab-demo-banner"><strong>Archived successful CASE-047.</strong> Recorded on a pinned revision (backend 00037, frontend 00022). The host-written CRM note is not an additional IBM-selected tool call. This demonstration is synthetic, not live production VA booking; do not replay the historical protected write.</aside>

  <div class="vab-demo-followup"><details><summary>Try a read-only MCP example</summary><p>Use the Developer Guide to call <code>get_scheduling_encounter</code> with a synthetic fixture. This does not reproduce the archived booking.</p><pre><code>{"name":"get_scheduling_encounter","arguments":{"case_id":"DEMO-CARD-5000335-001"}}</code></pre></details><a href="../evaluation/">See the Evaluation Command Center →</a><a href="../mcp-implementation/">Explore MCP Implementation →</a></div>
</div>
