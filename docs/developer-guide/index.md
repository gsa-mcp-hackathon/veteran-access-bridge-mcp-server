# Developer Guide

**CLI-first reproduction and integration setup.** Read-only fixture tests need no IBM, VA, Supabase or production credentials. Optional hosted integrations require authorized access and environment-specific configuration. Commands distinguish **project-documented** runs from **general setup recipes that have not been rerun for this site**.

<div class="feature-grid">
<div class="feature"><strong><a href="local-mcp-server/">1 · Local MCP server</a></strong><p>Quickest independent check: run the server and fixture tests locally.</p></div>
<div class="feature"><strong><a href="vha-sandbox/">2 · VHA Lighthouse sandbox</a></strong><p>API access and verification templates for sandbox reads.</p></div>
<div class="feature"><strong><a href="supabase/">3 · Supabase</a></strong><p>PostgreSQL synthetic CDW, CRM and RAG inspection.</p></div>
<div class="feature"><strong><a href="ibm-orchestrate/">4 · IBM watsonx Orchestrate</a></strong><p>Evaluation through the ADK CLI.</p></div>
<div class="feature"><strong><a href="deepeval/">5 · DeepEval</a></strong><p>Agent outcome grading in an isolated environment.</p></div>
<div class="feature"><strong><a href="phoenix/">6 · Phoenix tracing</a></strong><p>Optional tracing and visual inspection.</p></div>
<div class="feature"><strong><a href="release-checklist/">7 · Release & evidence checklist</a></strong><p>What to record before claiming results.</p></div>
</div>

Start with [Local MCP server](local-mcp-server.md).
