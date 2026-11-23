# Run over HTTP and connect services

!!! info "VS Code or Codespaces: same deployed architecture"
    VS Code is the recommended development environment; Codespaces is optional. Neither dictates whether IBM, Supabase, LiveKit or Deepgram is used. For secret placement, see [Configuration and secrets](configuration-and-secrets.md).

!!! warning "HTTP health is not patient or booking authorization"
    A healthy endpoint and valid MCP bearer credential establish service connectivity—not verified identity, trusted case scope, consent, slot freshness or authority to create a synthetic booking.


## Try the remote transport on your own computer

Complete the [local setup](local-mcp-server.md) first. With Docker running, use Bash in the repository root. These commands build the submitted code and bind the service to your computer. The bearer key exists in your terminal and container for this run.

```bash
docker build -f deploy/ibm/Dockerfile -t vab-mcp:review .
export VAB_MCP_API_KEY="$(uv run --no-sync python -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker run -d --rm --name vab-mcp-review -p 127.0.0.1:8080:8080 \
  -e VAB_MCP_TRANSPORT=streamable-http -e VAB_MCP_API_KEY vab-mcp:review
curl --fail --retry 10 --retry-all-errors --retry-delay 1 http://127.0.0.1:8080/health
uv run --no-sync python scripts/read_scheduling_encounter.py --local-http --list-tools
```

The health response shows the process is reachable. The inventory verifies authenticated MCP discovery. Try the same command without `--list-tools` to request the encounter. With only the container bearer key, expect **Trusted MCP session scope required** and a nonzero exit. A case ID and server credential alone cannot authorize remote access to a patient. Use the local fixture walkthrough for a successful read, or the connected application to establish an authorized session. For another MCP client, choose **Streamable HTTP**, enter `http://127.0.0.1:8080/mcp/` and set the Authorization header to `Bearer` followed by a space and your generated key. When finished, run `docker stop vab-mcp-review` and `unset VAB_MCP_API_KEY`.

## Reproduce the connected voice product

Before creating cloud resources for a fresh installation, read the [Supabase project restriction](supabase.md). The submitted backend requires an approved project binding for hosted database access.

**Installation order:** [Supabase](supabase.md) → [VA access](vha-sandbox.md) → [IBM hosting](avery-ibm-start.md) → [Avery and the toolkit](avery-agent.md) → [LiveKit](livekit.md) → [Deepgram and the worker](deepgram.md) → [Browser call and wrap-up](browser-call.md). On Windows, open a WSL window in VS Code to follow the Bash examples.

The local encounter uses bundled data. The recorded browser call also uses a database, VA sandbox reads, an IBM agent, a voice worker and a separate browser application. Bring accounts for the layers you intend to exercise. Use test data throughout.

| Layer | Configure in your environment | Check before continuing |
|---|---|---|
| VA reads | Request access for the APIs you use. Set the Facilities sandbox key and the patient or clinical API credentials and scopes for the chosen endpoint. [VA setup](vha-sandbox.md) | Read a known sandbox facility and authorized test record. A facility lookup alone establishes only facility access. |
| Supabase | Create a dedicated test project, apply the [database setup](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/db), and load synthetic fixtures. Give the backend its restricted connection via `VAB_SUPABASE_TEST_DATABASE_URL`. Configure `VAB_KB_DATABASE_URL` for database-backed knowledge reads. [Supabase guide](supabase.md) | Confirm the intended schema, case and inventory using the test role before enabling writes. |
| IBM | With an existing IBM account, select your own project and Orchestrate instance. Starting fresh, provision Code Engine and watsonx Orchestrate first. Deploy the backend using the [Code Engine guide](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/deploy/ibm/code-engine), connect your authenticated MCP endpoint and attach the toolkit to your agent. Configure its base URL, agent ID and API key on the backend. [Orchestrate guide](avery-agent.md) | Verify tool discovery and correlate one agent-selected read with backend evidence. |
| LiveKit and Deepgram | Create a LiveKit project and Deepgram key. Set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `DEEPGRAM_API_KEY` and `VAB_VOICE_BACKEND_URL` for the worker. Install with `uv sync --locked --group dev --extra voice`, then run `bash scripts/run-voice-worker-codespace.sh` in Bash. | Check that the worker registers in the intended project and that a test caller can hear and be heard. |
| Browser and protected booking | Follow the [companion frontend setup](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/frontend). Point its server-side connections at your backend and LiveKit project. Configure the trusted worker and booking credentials for your own environment before testing writes. | Start **Call in Browser**. Verify the identity step, tool trace, local-time calendar and persisted receipt. End the call and inspect the wrap-up and letter. |

The repository's [.env.example](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/.env.example) lists settings by component. Use your own agent ID and endpoints. Store values in Codespaces secrets or your deployment's secret store and grant them to the processes that need them. Browser users should receive short-lived session access.

## Troubleshooting

| Symptom | First check |
|---|---|
| Docker cannot reach the engine | Start Docker Desktop or the Linux daemon, then rerun the build. |
| Health succeeds but MCP returns 401 | Check that the client and container use the same locally generated bearer key. |
| Local call works but hosted data is absent | Check the selected adapter, test dataset and service credentials. |
| Voice connects but booking is refused | Inspect the worker identity, case binding and consent checks. A successful audio session alone provides no booking authority. |

[Review the evaluation evidence](../evaluation/reviewer-index.md) · [Developer guide](index.md)

For documented failure symptoms, see [Troubleshooting and validation checkpoints](troubleshooting.md). For technology rationale, see [Engineering decisions](engineering-decisions.md).
