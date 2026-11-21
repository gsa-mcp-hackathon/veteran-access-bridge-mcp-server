---
title: Evaluation Command Center
hide:
  - toc
---

<link rel="stylesheet" href="../stylesheets/evaluation-center.css">

<div class="ec" id="overview">
<nav class="ec-rail" aria-label="Evaluation sections"><strong>Evaluation &amp; Results</strong><a href="#overview" aria-current="page">Overview Dashboard</a><a href="#gold-questions">Gold Question Explorer</a><a href="validation-agent/#mcp-server-validation">MCP & Backend Evaluation</a><a href="validation-agent/#ibm-watsonx-orchestrate-and-deepeval">Agent & Voice Evaluation</a><a href="security-adversarial/">Security & Adversarial Testing</a><a href="reviewer-index/">Evidence Library</a></nav>
<div class="ec-main">
<header class="ec-hero"><small>EVALUATION &amp; RESULTS</small><h1>Evaluation Command Center</h1><p>From a scheduling question to a verified appointment: explore what the MCP server returned and what Avery did during a call.</p><div>October–November 2026 &nbsp; · &nbsp; Synthetic data &nbsp; · &nbsp; <a href="#boundaries">Evaluation scope</a></div></header>
<section class="ec-metrics" aria-label="Recorded outcomes">
<a href="#gold-questions"><b>16 / 16</b><strong>Gold answers matched</strong><small>Nov 19 · Primary Care</small></a><a href="method-gold/#phoenix-grouped-control-checks"><b>135 / 135</b><strong>Local control checks passed</strong><small>Nov 19 · Six suites</small></a><a href="validation-agent/#mcp-server-validation"><b>1,380</b><strong>Backend tests passed</strong><small>Nov 16 · Linux · 19 skipped</small></a><a href="validation-agent/#end-to-end-voice-trial"><b>1</b><strong>Synthetic booking verified</strong><small>Nov 16 · Pinned voice trial</small></a></section>
<div class="ec-grid"><div class="ec-work"><div class="ec-pair"><section class="ec-box"><h2>Evaluation coverage</h2>
<a class="ec-bar" href="#gold-questions">Gold question accuracy<b>16 / 16</b><i aria-hidden="true"></i></a><a class="ec-bar" href="method-gold/#phoenix-grouped-control-checks">Deterministic controls<b>135 / 135</b><i aria-hidden="true"></i></a><a class="ec-bar" href="validation-agent/#mcp-server-validation">MCP contract probes<b>108 / 108</b><i aria-hidden="true"></i></a><a class="ec-bar" href="security-adversarial/">Hostile argument probes<b>76 / 76</b><i aria-hidden="true"></i></a></section>
<section class="ec-box"><h2>What was evaluated</h2><ul><li>Tool outputs against fixture facts</li><li>Tool contracts and access controls</li><li>IBM agent behavior and voice turns</li><li>Booking receipt and CRM persistence</li></ul><a href="reviewer-index/">Inspect the evidence →</a></section></div>
<section class="ec-box ec-explorer" id="gold-questions" data-source="evidence/primary-care-mcp-gold.csv"><nav aria-label="Related results"><a href="#gold-questions" aria-current="location">Gold questions</a><a href="validation-agent/#mcp-server-validation">MCP &amp; backend</a><a href="validation-agent/#end-to-end-voice-trial">Agent &amp; voice</a><a href="security-adversarial/">Security</a></nav>
<h2>Gold Question Explorer</h2><p>Select a question to compare the expected fields with the MCP tool’s recorded output.</p>
<label for="ec-select">Recorded question</label><select id="ec-select" disabled><option>Loading the gold matrix…</option></select>
<div id="ec-record" aria-live="polite"><div class="ec-answers"><div><strong>Expected answer</strong><p id="ec-expected"></p></div><div><strong>Observed result</strong><p id="ec-observed"></p></div></div><p id="ec-source"></p></div>
<a href="evidence/primary-care-mcp-gold.csv">Download all 16 questions (CSV)</a> · <a href="method-gold/">How scoring works</a></section></div>
<section class="ec-box ec-journey"><h2>Evaluation journey</h2><ol>
<li><small>October 2026</small><h3>Define the gold questions</h3><p>The first 10 questions established the fixture and expected answers. This was a design milestone.</p></li>
<li><small>November 15–16</small><h3>Check the server contracts</h3><p>Regression tests checked the backend. Separate probes exercised tool inputs and rejection behavior on the 25-tool configuration.</p></li>
<li><small>November 16</small><h3>Follow a booking to the database</h3><p>Five IBM-selected tool types appeared in one trial. Database reads verified one simulated appointment and one host-written CRM note.</p><a href="validation-agent/#end-to-end-voice-trial">View the booking evidence →</a></li>
<li><small>November 19</small><h3>Compare each recorded answer</h3><p>The Primary Care matrix covers 16 questions. Six local suites contributed 135 control checks.</p></li></ol></section></div>
<aside class="ec-boundary" id="boundaries"><h2>Open evaluation boundaries</h2><p>Each figure has its own date, configuration and denominator. The November 18 Windows run recorded one failure. IBM and DeepEval reports cover historical agent configurations. Hosted concurrency, extended adversarial coverage, later-revision acceptance, final delivery evidence and independent reproduction remain open.</p><a href="validation-agent/#what-remains-open">Inspect open gaps</a> · <a href="security-adversarial/">Security reconciliation</a> · <a href="../developer-guide/clean-room-reproducibility/">Reproduction status</a></aside>
</div></div>
<script src="../assets/evaluation-center.js" defer></script>
