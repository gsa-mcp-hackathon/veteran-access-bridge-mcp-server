# Connect Avery to your MCP server

Start with your active [IBM project and Orchestrate environment](avery-ibm-start.md). You need an HTTPS backend reachable from IBM. In VS Code on Windows use a WSL Bash terminal for these examples. Use a new agent in your own workspace.

1. Build and deploy the scheduling backend to your Code Engine project using the [backend deployment instructions](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/deploy/ibm/code-engine). Configure its Streamable HTTP transport and store `VAB_MCP_API_KEY` as a backend secret. Copy the resulting HTTPS application URL. In Bash, check the address:

    ```bash
    read -rp "Backend URL (without a trailing slash): " BACKEND_URL
    curl --fail --show-error "$BACKEND_URL/health"
    ```

2. In the Orchestrate workspace, configure an MCP connection with **bearer authentication**. Enter the backend’s MCP key privately. Using your activated Orchestrate CLI, run `orchestrate connections list` to confirm the connection exists. Register a **remote MCP toolkit** using your application URL followed by `/mcp/`, Streamable HTTP, and that connection. Run `orchestrate toolkits list` to find the toolkit. A healthy application plus a toolkit authorization error usually means the bearer value or connection environment differs.

3. Create a native agent in your workspace. Give it the [release scheduling instructions](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/deploy/ibm/orchestrate/avery-agent-scheduling-v13.md), add the [eight release guidelines](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/deploy/ibm/orchestrate/avery-guidelines-v1.json), and attach the tools from your toolkit using the [release inventory](https://github.com/wbgreen0405/veteran-access-bridge/blob/ea0880f/docs/evaluation/guidelines-and-tool-inventory-20261118.md). The release counted **29 advertised tools and 21 attached to Avery**. The earlier M6.4 YAML includes a shorter list. Configure the trusted application context required by the release instructions and deploy the agent to the environment your backend will call.

4. Run `orchestrate agents list` and identify your agent. Configure the backend’s `ORCHESTRATE_AGENT_ID`, `ORCHESTRATE_BASE_URL` and private `ORCHESTRATE_API_KEY` for this instance. Set `ORCHESTRATE_RUNTIME_MODE=remote` and roll out that backend configuration. Keep your instance and agent identifiers together when switching environments.

**Check during the first browser call:** look for an Orchestrate-selected verification tool call with matching backend evidence for that interaction. An application lookup alone establishes that the host called the server. An unscoped request should stop before protected data is returned.

??? info "Why use Orchestrate here?"
    Avery chooses how to respond and which attached tool to request. The backend checks identity, case scope and consent before changing a record. See [Engineering decisions](engineering-decisions.md).

Continue to [Set up LiveKit](livekit.md).
