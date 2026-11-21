# Configuration and secrets: where each value belongs

Start with the [repository's `.env.example`](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/.env.example) and configure **only the services in your selected path**.

!!! info "VS Code is the recommended development environment"
    VS Code runs on your computer. Codespaces is an optional hosted editor. IBM Code Engine, Orchestrate, Supabase, LiveKit and Deepgram are external services—not requirements for the local fixture-based MCP walkthrough.

!!! warning "Never publish credentials"
    Do not commit `.env` files, private keys, JWTs, database passwords, or API keys. Use an approved local secret mechanism for VS Code, GitHub Codespaces secrets for Codespaces, and deployment-specific secret storage for hosted services. Never copy server-side credentials into browser JavaScript or public frontend build variables.

## Select your environment

| Environment | Configuration location | Who can read it? |
|---|---|---|
| VS Code/local Python | Approved local environment or ignored `.env` **only if loaded by the application** | Only the local process configured to receive it |
| GitHub Codespaces | Personal or repository Codespaces secrets with correct repo access | The running Codespace process after injection/restart |
| IBM Code Engine | Secret references and nonsecret application environment values | Deployed backend or worker process |
| Watsonx Orchestrate | Orchestrate environment/connection configuration | Authorized agent and toolkit runtime |
| Browser frontend | Public configuration and short-lived server-issued session data | Assume anything bundled into browser code is visible to its users |

## Which settings are needed?

| Setting | Source | Recipient | Verify without revealing the value |
|---|---|---|---|
| `VAB_MCP_TRANSPORT` | Project config | MCP process | Check stdio for local mode or authenticated HTTP discovery for remote mode |
| `VAB_MCP_API_KEY` | Strong randomly generated service credential | Remote MCP process and authorized MCP client connection | Correct credential discovers tools; invalid credential is denied |
| `VA_FACILITIES_API_KEY` | VA Facilities sandbox approval | Backend or local MCP VA adapter | Direct VA Facilities read, then matching MCP read |
| `ORCHESTRATE_BASE_URL` | Your IBM Orchestrate instance | Backend runtime | Confirm the instance and agent API are reachable |
| `ORCHESTRATE_AGENT_ID` | Your deployed agent | Backend runtime | Verify the agent selected a tool in the actual target environment |
| `ORCHESTRATE_API_KEY` | Authorized IBM credential | Backend secret storage | Verify API access without printing the key |
| `LIVEKIT_URL` | Your LiveKit project | Worker and authorized backend | Confirm the worker joins the expected project/session |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | LiveKit project credentials | Trusted server-side worker/backend only | Issue a controlled test session token and establish a connection |
| `DEEPGRAM_API_KEY` | Deepgram console | Voice worker secret storage | Validate two-way speech during a synthetic call |
| `VAB_VOICE_BACKEND_URL` | Your backend URL | Voice worker | Check worker-to-backend connectivity and correlated request logs |
| `VAB_SUPABASE_TEST_DATABASE_URL` | Approved synthetic test database | Backend restricted DB connection | Confirm database identity, role and known synthetic case |
| `VAB_TRUSTED_HOST_PUBLIC_KEY_PATH` | Approved trusted host issuer setup | Backend validation service | Confirm signed scope assertions pass and invalid assertions fail |

Other advanced settings in `.env.example` may require matching worker, backend and policy configuration; they are **not** instructions to turn on booking features by default. Optional knowledge-store configuration (`VAB_KB_DATABASE_URL`) is documented in the [connected-services guide](connected-product.md).

## Why a secret can be present but not work

??? tip "Codespaces secret missing"
    Confirm the name, repository access and Codespace restart. A secret saved in GitHub settings is not automatically placed in every terminal or deployment.

??? tip "IBM CLI login succeeds but the agent request fails"
    IBM Cloud SSO, Orchestrate environment activation, agent runtime API credentials and Code Engine application secrets have different scopes and lifetimes. Validate the failing connection independently.

??? tip "Local `.env` was edited but the server ignores the change"
    Verify the app actually loads the `.env` file or that variables were exported to the process. Restart the correct process; do not assume a file is automatically read by all tools.

??? warning "Remote MCP returns a scope-related denial"
    A valid MCP bearer key is service authentication only. It does not supply patient identity, case scope or booking approval. Do not bypass the trusted-host safeguards to make a demo pass.

[Run MCP locally](local-mcp-server.md) · [Review recovery steps](troubleshooting.md)
