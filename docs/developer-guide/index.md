---
title: Developer Guide
hide:
  - toc
---

<link rel="stylesheet" href="../stylesheets/developer-landing.css">

<div class="vab-start">
<header class="start-hero">
<p class="start-kicker">Developer Guide</p>
<h1>Veteran Access Bridge</h1>
<p>Try a Primary Care scheduling request with the included test data, or set up Avery to take a browser call and record a test appointment.</p>
</header>

<h2 class="start-question">What do you want to do?</h2>

<div class="start-paths">
<section class="start-card">
<header><span class="start-icon" aria-hidden="true">›_</span><div><h3>Run the MCP server</h3>
<p>Ask which Primary Care appointment slots a test patient can use. See which slots qualify and why the server rules one out.</p></div></header>
<div class="start-body"><h4>What you need</h4>
<p>The repository includes the sample patient and appointment slots. For this first request, you can skip IBM Cloud and Supabase setup.</p>
<h4>Choose where to run it</h4>
<div class="start-choices">
<details name="mcp-start"><summary>In my browser with GitHub Codespaces</summary>
<div><strong>Start in GitHub</strong><ol><li>Sign in to GitHub and open the <a href="https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server">submission repository</a>.</li><li>Select <b>Code → Codespaces → Create codespace on main</b>. GitHub opens a development environment in your browser.</li><li>When setup finishes, open <b>Terminal → New Terminal</b>. The terminal is where you enter the commands in the guide.</li></ol><a href="local-mcp-server/#install-and-discover">Install the server and send your first request →</a></div></details>
<details name="mcp-start"><summary>On my computer with VS Code</summary>
<div><strong>Start on your computer</strong><ol><li>Install <a href="https://code.visualstudio.com/download">VS Code</a>, <a href="https://git-scm.com/downloads">Git</a>, <a href="https://www.python.org/downloads/">Python 3.12</a> and <a href="https://docs.astral.sh/uv/getting-started/installation/">uv</a>, the project's package manager.</li><li>Open VS Code, choose <b>Terminal → New Terminal</b> and copy the repository to your computer:</li></ol>
<pre><code>git clone https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git</code></pre>
<p>Choose <b>File → Open Folder</b>, select <b>veteran-access-bridge-mcp-server</b>, then open a new terminal in that folder.</p><a href="local-mcp-server/#install-and-discover">Install the server and send your first request →</a></div></details>
</div></div></section>

<section class="start-card start-voice">
<header><span class="start-icon start-wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span><div><h3>Build your own Avery voice agent</h3>
<p>Call Avery from your browser, schedule a test appointment, then check the saved booking, CRM note, and confirmation letter.</p></div></header>
<div class="start-body"><h4>Services for the full call</h4>
<ul class="start-services"><li>IBM Cloud + watsonx Orchestrate</li><li>Supabase</li><li>LiveKit</li><li>Deepgram</li><li>VA sandbox APIs</li></ul>
<h4>Choose your starting point</h4>
<div class="start-choices">
<details name="avery-start"><summary>I already have an IBM Cloud account</summary>
<div><strong>Check what is provisioned</strong><ol><li>Open your <a href="https://cloud.ibm.com/resources">IBM Cloud resource list</a>. Find your <b>watsonx Orchestrate</b> instance. This is where Avery and its tools are configured.</li><li>Open <a href="https://cloud.ibm.com/codeengine/projects">Code Engine projects</a> and identify the project for the scheduling backend. If either service is missing, provision it in your own account.</li><li>Prepare the test database, VA access and voice services before attempting the browser call.</li></ol><a href="connected-product/#reproduce-the-connected-voice-product">Connect your services and check each layer →</a></div></details>
<details name="avery-start"><summary>Help me set everything up</summary>
<div><strong>Start with the service accounts</strong><ol><li><a href="https://cloud.ibm.com/registration">Create an IBM Cloud account</a>. Set up Code Engine to host the backend and watsonx Orchestrate to run Avery.</li><li><a href="supabase/">Prepare Supabase</a>. Create a test database, apply the project schema and load synthetic cases and appointment slots before the first call.</li><li><a href="vha-sandbox/">Set up VA sandbox access</a> for the patient and facility reads.</li><li>Create a <a href="https://cloud.livekit.io/">LiveKit project</a> for the browser call and a <a href="https://console.deepgram.com/">Deepgram key</a> for speech. Connect the voice worker and browser app to your backend.</li></ol><a href="connected-product/#reproduce-the-connected-voice-product">Open the configuration and verification guide →</a></div></details>
</div></div></section></div>

<nav class="start-resources" aria-label="Developer resources">
<a href="../solution-architecture/"><b>Architecture</b><span>How the parts connect</span></a>
<a href="../mcp-implementation/"><b>MCP Tool Reference</b><span>Tool groups and example requests</span></a>
<a href="../evaluation/reviewer-index/"><b>Evaluation Results</b><span>Tests and recorded evidence</span></a>
<a href="phoenix/"><b>Tracing</b><span>Inspect calls with Phoenix</span></a>
</nav></div>
