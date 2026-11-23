---
title: Per-Tool Evaluation
---

# Per-Tool Evaluation — M6.4

The full reviewed catalog contains **29 registered tools**; **21** were attached to Avery and **8** intentionally excluded. The historical November 16 local test matrix contains **25 tools**. A missing historical contract row for the four additional voice/knowledge tools is **not** a failed tool.

<div class="pt-dashboard" data-evidence-url="../evidence/m64-per-tool-evidence.json">
  <div class="pt-summary">
    <div><small>Registered</small><strong>29</strong><span>Reviewed M6.4</span></div>
    <div><small>Attached to Avery</small><strong>21</strong><span>8 server-only</span></div>
    <div><small>Historical contract rows</small><strong>25</strong><span>Nov 16 local run</span></div>
    <div><small>Focused verifier CI</small><strong>48/48</strong><span>PR #215 · not tool success</span></div>
  </div>
  <div class="pt-columns">
    <section class="pt-panel"><h2>Per-tool results</h2><p>Search the exact inventory and select any tool to inspect its bounded evidence.</p>
      <div class="pt-filters"><label>Search<input id="pt-search" type="search" placeholder="Tool name"></label><label>Capability<select id="pt-category"><option value="">All</option></select></label><label>Avery<select id="pt-attached"><option value="">All</option><option value="yes">Attached</option><option value="no">Server-only</option></select></label></div>
      <div class="pt-scroll"><table><thead><tr><th>Tool</th><th>Contracts</th><th>Hostile arguments</th><th>Scope denial</th><th>IBM M6.4</th></tr></thead><tbody id="pt-rows"><tr><td colspan="5">Loading catalog…</td></tr></tbody></table></div>
      <p id="pt-count" aria-live="polite"></p>
    </section>
    <section class="pt-panel"><h2>Evaluation scorecard</h2><p>Evidence dimensions, not fabricated 0–100 ratings.</p>
      <div class="pt-score"><span>Capability</span><b>Bounded local contracts</b></div>
      <div class="pt-score"><span>Reliability</span><b>Historical test suites</b></div>
      <div class="pt-score"><span>Efficiency</span><b>Current per-tool p95 unavailable</b></div>
      <div class="pt-score"><span>Safety</span><b>Four deployed PARTIAL</b></div>
      <div class="pt-score"><span>Developer experience</span><b>Focused CI evidence</b></div>
      <p><strong>Pass³:</strong> not evaluated—three independent trials per case are not established by this matrix.</p>
      <h3>Selected tool details</h3><div id="pt-detail">Select a tool.</div>
    </section>
  </div>
  <section class="pt-panel"><h2>Failed cases and evidence gaps</h2>
    <ul><li>Local contract PASS is not the same as successful IBM-selected execution.</li><li>`search_call_knowledge` is deployed, but current per-tool retrieval accuracy and p95 are not scored here.</li><li>S14 local verifier passed, while IBM pre-dispatch description enforcement remains unverified.</li><li>S03/A21, S13/A23 and S15 still require their separately defined runtime proof.</li></ul>
  </section>
</div>

**Source records:** [Machine-readable per-tool JSON](evidence/m64-per-tool-evidence.json) · [Evidence index](reviewer-index.md) · [Security outcomes](security-adversarial.md).

<script src="../../assets/per-tool-evaluation.js" defer></script>
