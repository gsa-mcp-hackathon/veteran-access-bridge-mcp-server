# Build and deployment entry points

| Component | Original release files | Purpose |
| --- | --- | --- |
| MCP backend | [IBM image](ibm/Dockerfile) and [Code Engine guide](ibm/code-engine/README.md) | Serves the API and MCP transport. |
| Voice worker | [Worker image](ibm/avery-worker/Dockerfile) | Runs the LiveKit worker as a separate process. |
| IBM agent | [Agent guide](../agents/README.md) and [Orchestrate history](ibm/orchestrate/README.md) | Identifies the demonstrated agent and distinguishes older toolkit configurations. |
| Local toolkit and experiments | [Local toolkit](ibm/local-mcp-toolkit/README.md) and [answer preparation](ibm/evaluation/answer-preparation-candidate.md) | Preserved for reproducing earlier development and evaluation work. |

From the repository root, build the images without deploying them:

```bash
docker build -f deploy/ibm/Dockerfile -t vab-mcp:local .
docker build -f deploy/ibm/avery-worker/Dockerfile -t vab-voice:local .
```

Use [.env.example](../.env.example) for configuration names. Hosted scripts include original account, application or region defaults. Inspect their targets before use. For credential-free review start with the [local server](../docs/developer-guide/local-mcp-server.md).
