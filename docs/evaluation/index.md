---
title: Evaluation Command Center
hide:
  - toc
---

<link rel="stylesheet" href="../stylesheets/evaluation-center.css">

<div class="ec" id="overview">
<nav class="ec-rail" aria-label="Evaluation sections"><strong>Evaluation &amp; Results</strong><a href="#overview" aria-current="page">Overview Dashboard</a><a href="#gold-questions">Gold Question Explorer</a><a href="validation-agent/#mcp-server-validation">MCP & Backend Evaluation</a><a href="validation-agent/#ibm-watsonx-orchestrate-and-deepeval">Agent & Voice Evaluation</a><a href="security-adversarial/">Security & Adversarial Testing</a><a href="reviewer-index/">Evidence Library</a></nav>
<div class="ec-main">
<header class="ec-hero"><small>EVALUATION &amp; RESULTS</small><h1>Evaluation Command Center</h1><p>Recorded results, evidence, and analysis for the Veteran Access Bridge MCP server and Avery voice experience.</p><div>October–November 2026 &nbsp; · &nbsp; Synthetic environment (no production VA data) &nbsp; · &nbsp; <a href="#boundaries">Evaluation scope &amp; boundaries</a></div></header>
<section class="ec-metrics" aria-label="Recorded outcomes">
<a href="#gold-questions"><b>16 / 16</b><strong>Gold answers matched</strong><small>Nov 19 · Primary Care</small></a><a href="method-gold/#phoenix-grouped-control-checks"><b>135 / 135</b><strong>Deterministic control checks</strong><small>Nov 19 · Six suites</small></a><a href="validation-agent/#mcp-server-validation"><b>1,380</b><strong>Backend tests passed</strong><small>Nov 16 · Linux · 19 skipped</small></a><a href="validation-agent/#end-to-end-voice-trial"><b>1</b><strong>Synthetic booking verified</strong><small>Nov 16 · Pinned voice trial</small></a></section>
<div class="ec-grid"><div class="ec-work"><div class="ec-pair"><section class="ec-box"><h2>Evaluation Coverage</h2>
<a class="ec-bar" href="#gold-questions">Gold question accuracy<b>16 / 16 (100%)</b><i aria-hidden="true"></i></a><a class="ec-bar" href="method-gold/#phoenix-grouped-control-checks">Deterministic controls<b>135 / 135 (100%)</b><i aria-hidden="true"></i></a><a class="ec-bar" href="validation-agent/#mcp-server-validation">MCP contract probes<b>108 / 108 (100%)</b><i aria-hidden="true"></i></a><a class="ec-bar" href="security-adversarial/">Hostile argument probes<b>76 / 76 (100%)</b><i aria-hidden="true"></i></a></section>
<section class="ec-box"><h2>What Was Evaluated</h2><ul><li>MCP tool correctness and contracts</li><li>Agent behavior (IBM / DeepEval)</li><li>Voice scheduling with Avery</li><li>Security and adversarial scenarios</li><li>End-to-end synthetic booking and CRM note</li></ul></section></div>
<section class="ec-box ec-explorer" id="gold-questions" data-source="evidence/primary-care-mcp-gold.csv"><nav aria-label="Related results"><a href="#gold-questions" aria-current="location">Gold questions</a><a href="validation-agent/#mcp-server-validation">MCP &amp; backend</a><a href="validation-agent/#end-to-end-voice-trial">Agent &amp; voice</a><a href="security-adversarial/">Security</a><a href="reviewer-index/">All results</a></nav>
<h2>Gold Question Explorer</h2><p>Review a test question, the expected answer, and the recorded result.</p>
<label for="ec-select">Select a question</label><div class="ec-choice"><select id="ec-select" disabled><option>Loading the gold matrix…</option></select><strong id="ec-verdict" role="status"></strong></div>
<div id="ec-record" aria-live="polite"><div class="ec-answers"><div><strong>Expected answer</strong><p id="ec-expected"></p></div><div><strong>Observed result</strong><p id="ec-observed"></p></div></div></div><details class="ec-details"><summary>Source and scoring details</summary><p id="ec-source"></p><p id="ec-values"></p><a href="evidence/primary-care-mcp-gold.csv">Download all 16 questions (CSV)</a> · <a href="method-gold/">How scoring works</a></details></section></div>
<section class="ec-box ec-journey"><h2>Evaluation Journey</h2><p>Key milestones in the project’s evaluation.</p><ol>
<li><small>October 2026</small><h3>Gold question foundation</h3><p>The first 10 questions established the fixture and expected answers. This was a design milestone.</p></li>
<li><small>November 15–16</small><h3>Server and contract evaluation</h3><p>Regression tests checked the backend. Separate probes exercised tool inputs and rejection behavior on the 25-tool configuration.</p></li>
<li><small>November 16</small><h3>Avery completed a synthetic booking</h3><p>Five IBM-selected tool types appeared in one trial. Database reads verified one simulated appointment and one host-written CRM note.</p><a href="validation-agent/#end-to-end-voice-trial">BOOKED_SIMULATED</a></li>
<li><small>November 19</small><h3>Expanded judge-review evidence</h3><p>The Primary Care matrix covers 16 questions. Six local suites contributed 135 control checks.</p></li></ol></section></div>
<aside class="ec-boundary" id="boundaries"><h2>Open Evaluation Boundaries</h2><p>Hosted concurrency, extended adversarial coverage, later-revision acceptance, final delivery evidence, and reproducibility remain open. The November 18 Windows run recorded one failure. See the <a href="validation-agent/#what-remains-open">evaluation scope</a> for details.</p></aside>
</div></div>
<script src="../assets/evaluation-center.js" defer></script>
