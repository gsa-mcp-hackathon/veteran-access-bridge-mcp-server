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
<p>Run the MCP server, test scheduling with example data, or build the full Avery voice scheduling experience.</p>
</header>

<h2 class="start-question">What do you want to do?</h2>

<div class="start-paths">
<section class="start-card">
<header><img class="guide-symbol" src="../assets/guide/terminal.png" alt=""><div><h3>I want to run the MCP server and try a scheduling request.</h3>
<p>Use the included test data to run the server and send a scheduling request end-to-end. No IBM account required.</p></div></header>
<div class="start-body"><h4>Choose where to run it:</h4>
<div class="start-choices">
<details name="mcp-start"><summary><img class="guide-symbol" src="../assets/guide/github.png" alt=""><span>In my browser with GitHub Codespaces</span></summary>
<div><strong>Start in GitHub</strong><ol><li>Sign in to GitHub and open the <a href="https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server">submission repository</a>.</li><li>Select <b>Code → Codespaces → Create codespace on main</b>. GitHub opens a development environment in your browser.</li><li>When setup finishes, open <b>Terminal → New Terminal</b>. The terminal is where you enter the commands in the guide.</li></ol><a href="codespaces/">Follow the Codespaces walkthrough →</a></div></details>
<details name="mcp-start"><summary><img class="guide-symbol" src="../assets/guide/vscode.png" alt=""><span>On my computer with VS Code</span></summary>
<div><strong>Start on your computer</strong><ol><li>Install <a href="https://code.visualstudio.com/download">VS Code</a>, <a href="https://git-scm.com/downloads">Git</a>, <a href="https://www.python.org/downloads/">Python 3.12</a> and <a href="https://docs.astral.sh/uv/getting-started/installation/">uv</a>, the project's package manager.</li><li>Open VS Code, choose <b>Terminal → New Terminal</b> and copy the repository to your computer:</li></ol>
<pre><code>git clone https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git</code></pre>
<p>Choose <b>File → Open Folder</b>, select <b>veteran-access-bridge-mcp-server</b>, then open a new terminal in that folder.</p><a href="vs-code/">Follow the VS Code walkthrough →</a></div></details>
</div></div><footer><img class="guide-symbol" src="../assets/guide/quick.png" alt=""><b>Quick start</b><span>·</span>Run with the included sample data.</footer></section>

<section class="start-card start-voice">
<header><img class="guide-symbol" src="../assets/guide/waveform.png" alt=""><div><h3>I want to build the full Avery voice scheduling experience.</h3>
<p>Connect the MCP server to the services behind the call to run Avery — a conversational voice scheduling experience.</p></div></header>
<div class="start-body"><h4>Full setup uses these services:</h4>
<div class="start-services"><span><img class="guide-symbol" src="../assets/guide/ibm.png" alt="">IBM Cloud</span><span><img class="guide-symbol" src="../assets/guide/livekit.png" alt="">LiveKit</span><span><img class="guide-symbol" src="../assets/guide/deepgram.png" alt="">Deepgram</span><span><img class="guide-symbol" src="../assets/guide/supabase.png" alt="">Supabase</span><span><img class="guide-symbol" src="../assets/guide/va.png" alt="">VA Sandbox</span></div>
<h4>Choose your path:</h4>
<div class="start-choices">
<details name="avery-start"><summary><img class="guide-symbol" src="../assets/guide/cloud.png" alt=""><span>I already have IBM Cloud</span></summary>
<div><strong>Check what is provisioned</strong><ol><li>Open your <a href="https://cloud.ibm.com/resources">IBM Cloud resource list</a>. Find your <b>watsonx Orchestrate</b> instance. This is where Avery and its tools are configured.</li><li>Open <a href="https://cloud.ibm.com/codeengine/projects">Code Engine projects</a> and identify the project for the scheduling backend. If either service is missing, provision it in your own account.</li><li>Prepare the test database, VA access and voice services before attempting the browser call.</li></ol><a href="connected-product/#reproduce-the-connected-voice-product">Connect your services and check each layer →</a></div></details>
<details name="avery-start"><summary><img class="guide-symbol" src="../assets/guide/rocket.png" alt=""><span>I’m starting from scratch</span></summary>
<div><strong>Start with the service accounts</strong><ol><li><a href="https://cloud.ibm.com/registration">Create an IBM Cloud account</a>. Set up Code Engine to host the backend and watsonx Orchestrate to run Avery.</li><li><a href="supabase/">Prepare Supabase</a>. Create a test database, apply the project schema and load synthetic cases and appointment slots before the first call.</li><li><a href="vha-sandbox/">Set up VA sandbox access</a> for the patient and facility reads.</li><li>Create a <a href="https://cloud.livekit.io/">LiveKit project</a> for the browser call and a <a href="https://console.deepgram.com/">Deepgram key</a> for speech. Connect the voice worker and browser app to your backend.</li></ol><a href="connected-product/#reproduce-the-connected-voice-product">Open the configuration and verification guide →</a></div></details>
</div></div><footer><img class="guide-symbol" src="../assets/guide/setup.png" alt=""><b>Full setup</b><span>·</span>Configure services, deploy, and run the voice experience.</footer></section></div>

<nav class="start-resources" aria-label="Developer resources">
<div><img class="guide-symbol" src="../assets/guide/layers.png" alt=""><strong>What’s included</strong><a href="../mcp-implementation/">MCP server</a><a href="local-mcp-server/">Test data</a><a href="connected-product/">Deployment guides</a><a href="deepeval/">Evaluation (DeepEval)</a><a href="phoenix/">Tracing (Phoenix)</a></div>
<div><img class="guide-symbol" src="../assets/guide/book.png" alt=""><strong>Other resources:</strong><a href="../solution-architecture/">Architecture →</a><a href="../mcp-implementation/#representative-mcp-contracts">API Reference →</a></div>
</nav></div>
