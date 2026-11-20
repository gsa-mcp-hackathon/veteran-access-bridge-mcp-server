# IBM Cloud Deployment

Veteran Access Bridge targets IBM Cloud Code Engine as a single HTTPS application
serving the demo UI, REST API, and MCP endpoint on one container and one port.

## Deployment paths

```text
LOCAL DEV          stdio MCP          deploy/ibm/local-mcp-toolkit/
CONTAINER DEMO     HTTP               deploy/ibm/Dockerfile
REMOTE AGENT       streamable-http    deploy/ibm/code-engine/ + orchestrate/
PRODUCTION         not implemented    requires VA security review
```

## Quick reference

| Guide | Purpose |
|---|---|
| `local-mcp-toolkit/README.md` | Local stdio MCP with Orchestrate |
| `code-engine/README.md` | Build, push, and deploy to Code Engine |
| `orchestrate/README.md` | Connect Orchestrate to remote MCP endpoint |
| `Dockerfile` | IBM-targeted production container image |
| `.dockerignore` | Container build exclusions |

See `docs/deployment/ibm-watsonx-orchestrate.md` for the full four-tier reference.
