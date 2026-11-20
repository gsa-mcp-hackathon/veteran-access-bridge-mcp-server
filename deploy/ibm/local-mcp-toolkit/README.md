# watsonx Orchestrate — Veteran Access local MCP toolkit

This kit adapts the GSA-TTS hackathon template's lowest-overhead IBM deployment path.

It stages the existing `veteran_access_bridge` Python package next to a tiny `server.py` entrypoint and registers it as a **local MCP toolkit**. Orchestrate runs the server over stdio. There is no HTTP endpoint, container, or registry in this first deployment path.

## Prerequisites

- Python 3.11–3.14 for the watsonx Orchestrate ADK
- A watsonx Orchestrate SaaS instance
- IBM watsonx Orchestrate ADK

```powershell
python -m pip install --upgrade ibm-watsonx-orchestrate
orchestrate --version
```

## Configure

Copy the example:

```powershell
Copy-Item deploy\ibm\local-mcp-toolkit\.env.example deploy\ibm\local-mcp-toolkit\.env
```

Set the non-secret values in the local `.env` file. Keep the API key out of files:

```powershell
$env:WXO_API_KEY = "<your Orchestrate API key>"
```

Then load the other settings into the current shell, or set them directly:

```powershell
$env:WXO_ENV_NAME = "veteran-access-hackathon"
$env:WXO_INSTANCE_URL = "<your instance URL>"
$env:TOOLKIT_NAME = "veteran_access_mcp_local"
```

## Register

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\ibm\local-mcp-toolkit\register-toolkit.ps1
```

The script:

1. validates the required configuration;
2. confirms the Orchestrate CLI is available;
3. activates or creates the selected Orchestrate environment;
4. stages only the Veteran Access package and runtime requirements;
5. imports the toolkit;
6. removes the temporary staging directory.

## Local entrypoint smoke test

```powershell
python deploy\ibm\local-mcp-toolkit\server.py
```

The process should start and wait for MCP stdio input. Use Ctrl+C to stop it.

## Next step

In the watsonx Orchestrate UI, build the **Veteran Access Agent**, add the toolkit tools, and test the cardiology demo flow.

The current toolkit remains synthetic-only and does not perform real appointment booking.
