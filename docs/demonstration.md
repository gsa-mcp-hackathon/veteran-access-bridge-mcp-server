---
title: Avery Scheduling Demonstration
hide:
  - toc
---

<div class="vab-demo">
  <header class="vab-demo-hero">
    <div class="vab-demo-eyebrow">VETERAN ACCESS BRIDGE · RECORDED DEMONSTRATION</div>
    <h1>Avery Scheduling Demonstration</h1>
    <p>One Veteran. One Conversation. Connected Care. Watch how Avery uses MCP tools while trusted services independently enforce a <strong>synthetic Primary Care booking</strong>.</p>
    <div class="vab-demo-meta"><span>November 16, 2026</span><span>3 min 36 sec recording</span><span>Synthetic data only</span></div>
  </header>

  <section class="vab-demo-section vab-demo-watch" id="watch">
    <div class="vab-demo-section-title"><div><span class="vab-demo-kicker">01 / WATCH</span><h2>The recorded call</h2><p>Listen to the conversation and follow the tool activity shown in the recording.</p></div><a href="../assets/avery-demo.mp4">Open full video (MP4) →</a></div>
    <div class="vab-demo-video-wrap">
      <video controls playsinline preload="metadata" poster="../assets/avery-demo-poster.jpg" aria-label="Avery Primary Care synthetic scheduling demonstration, November 16, 2026">
        <source src="../assets/avery-demo.mp4" type="video/mp4">
        <p>Your browser does not support embedded video. <a href="../assets/avery-demo.mp4">Open the MP4 recording</a>.</p>
      </video>
    </div>
    <p class="vab-demo-caption">Recorded generated-audio trial. The demonstration uses synthetic identities and scheduling records; this is not a live VA appointment service.</p>
  </section>

  <section class="vab-demo-section" id="chapters">
    <div class="vab-demo-section-title"><div><span class="vab-demo-kicker">02 / FOLLOW THE JOURNEY</span><h2>Six stages of one scheduling call</h2><p>Expand a stage for the corresponding system action and enforcement boundary. These are chapter descriptions, not unverified video seek markers.</p></div></div>
    <div class="vab-demo-chapters">
      <details><summary><span class="vab-demo-number">01</span><span><strong>Greet</strong><small>Identify the Primary Care scheduling request</small></span><span class="vab-demo-arrow" aria-hidden="true">⌄</span></summary><div class="vab-demo-chapter-body"><p>A synthetic caller describes a Primary Care scheduling need. The browser and LiveKit voice application carry the conversation.</p><p><b>Evidence boundary:</b> Conversation alone is not an authenticated scheduling action.</p></div></details>
      <details><summary><span class="vab-demo-number">02</span><span><strong>Verify</strong><small>Bind the caller to a trusted case and session</small></span><span class="vab-demo-arrow" aria-hidden="true">⌄</span></summary><div class="vab-demo-chapter-body"><p>The trusted host checks caller identity and session/case binding.</p><p><b>Evidence boundary:</b> Model statements do not create identity or case authority.</p></div></details>
      <details><summary><span class="vab-demo-number">03</span><span><strong>Retrieve</strong><small>Read permitted patient and call knowledge context</small></span><span class="vab-demo-arrow" aria-hidden="true">⌄</span></summary><div class="vab-demo-chapter-body"><p>IBM-selected patient-context and knowledge tools return structured, scoped evidence for the active synthetic call.</p><p><b>Evidence boundary:</b> Retrieved material provides information, not authorization.</p></div></details>
      <details><summary><span class="vab-demo-number">04</span><span><strong>Search &amp; select</strong><small>Find options and capture the Veteran's preference</small></span><span class="vab-demo-arrow" aria-hidden="true">⌄</span></summary><div class="vab-demo-chapter-body"><p><code>search_call_appointments</code> returned two verified options; <code>select_call_appointment</code> selected an option for the host to read back.</p><p><b>Evidence boundary:</b> Selecting an option is not a booking or consent.</p></div></details>
      <details><summary><span class="vab-demo-number">05</span><span><strong>Confirm</strong><small>Read back the exact option and obtain current confirmation</small></span><span class="vab-demo-arrow" aria-hidden="true">⌄</span></summary><div class="vab-demo-chapter-body"><p>The trusted host read back the selected appointment and captured explicit confirmation in a later turn.</p><p><b>Evidence boundary:</b> Consent and policy checks remain independent of agent-generated prose.</p></div></details>
      <details><summary><span class="vab-demo-number">06</span><span><strong>Book &amp; wrap up</strong><small>Perform a protected synthetic commit and record the result</small></span><span class="vab-demo-arrow" aria-hidden="true">⌄</span></summary><div class="vab-demo-chapter-body"><p>IBM selected <code>book_call_appointment</code>. The backend performed a policy-gated synthetic booking and the trusted host recorded CRM follow-up.</p><p><b>Verified result:</b> One persisted synthetic appointment, one host-written CRM note and <code>BOOKED_SIMULATED</code>.</p></div></details>
    </div>
  </section>

  <section class="vab-demo-section" id="tool-activity">
    <div class="vab-demo-section-title"><div><span class="vab-demo-kicker">03 / UNDER THE HOOD</span><h2>MCP tools in action</h2><p>Five distinct IBM-selected MCP tool types were observed in the accepted call. The selected scheduling sequence is highlighted below.</p></div><a href="../mcp-implementation/">Explore the MCP tool catalog →</a></div>
    <div class="vab-demo-toolflow">
      <div><span>01 · SEARCH</span><code>search_call_appointments</code><p>Return permitted appointment options</p></div>
      <div><span>02 · SELECT</span><code>select_call_appointment</code><p>Record a call-scoped choice; no booking yet</p></div>
      <div><span>03 · REQUEST</span><code>book_call_appointment</code><p>Request a protected synthetic booking</p></div>
    </div>
    <p class="vab-demo-note">The two other observed tool types performed patient-context retrieval and knowledge search. The automatic CRM note was written by the trusted host, <strong>not</strong> by a separate IBM-selected CRM tool invocation. The actual backend—not Avery's response text—decided whether the booking could be committed.</p>
  </section>

  <section class="vab-demo-section" id="outcome">
    <div class="vab-demo-section-title"><div><span class="vab-demo-kicker">04 / VERIFY</span><h2>Proof beyond the conversation</h2><p>Independent record reads confirmed the simulated outcome in the pinned November 16 acceptance trial.</p></div></div>
    <div class="vab-demo-proof-grid">
      <div class="vab-demo-proof"><span class="vab-demo-proof-icon" aria-hidden="true">✓</span><strong>1</strong><span>Persisted synthetic appointment</span></div>
      <div class="vab-demo-proof"><span class="vab-demo-proof-icon" aria-hidden="true">✓</span><strong>1</strong><span>Host-written CRM note</span></div>
      <div class="vab-demo-proof vab-demo-proof-receipt"><span class="vab-demo-proof-icon" aria-hidden="true">✓</span><strong>BOOKED_SIMULATED</strong><span>Recorded synthetic booking receipt</span></div>
    </div>
    <div class="vab-demo-evidence">
      <div><h3>Inspect the evidence</h3><p>CASE-047 · backend revision 00037 · frontend revision 00022. The accepted trial used generated caller audio and synthetic data.</p></div>
      <div class="vab-demo-evidence-links"><a href="https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/operations/avery-agent-led-scheduling-20261116.md">Read acceptance report →</a><a href="https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/agent-led-voice-20261116.json">View machine-readable proof →</a><a href="../evaluation/validation-agent/#end-to-end-voice-trial">Review evaluation context →</a></div>
    </div>
    <p class="vab-demo-boundary"><strong>Archived successful CASE-047:</strong> This is evidence from a pinned historical revision. Do not replay its protected write to demonstrate a fresh booking. No production VA appointment was created and no clinical decision authority is claimed.</p>
  </section>

  <section class="vab-demo-section" id="reproduce">
    <div class="vab-demo-section-title"><div><span class="vab-demo-kicker">05 / TRY IT SAFELY</span><h2>Reproduce a local MCP read</h2><p>A synthetic fixture verifies tool responses without making a new booking or requiring the voice services.</p></div></div>
    <pre class="vab-demo-code"><code>{"name":"get_scheduling_encounter","arguments":{"case_id":"DEMO-CARD-5000335-001"}}</code></pre>
    <p>Follow the <a href="../developer-guide/local-mcp-server/">local MCP server walkthrough</a>, then try an unknown case ID to inspect the explicit denial. A local read does not reproduce the pinned voice booking.</p>
    <div class="vab-demo-next"><a href="../developer-guide/">Developer Guide →</a><a href="../evaluation/">Evaluation Command Center →</a><a href="../security-governance/">Security &amp; Governance →</a></div>
  </section>
</div>
