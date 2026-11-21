# Prerequisites and requirements

Choose the outcome you want before setting up accounts.

| What you want to try | What to have ready |
|---|---|
| Inspect MCP tools and run a sample scheduling request | Git, uv and Python 3.12 in VS Code, or a GitHub account with Codespaces access. The repository supplies the example records. |
| Look up a facility through the VA API | Complete the local setup and obtain your own VA Facilities sandbox API key. |
| Run Avery and speak to the agent | An IBM Cloud account with Code Engine and watsonx Orchestrate access, an authorized test database with synthetic scheduling inventory, VA credentials for the enabled reads, a LiveKit project, a Deepgram key and the companion browser app. Use a browser with microphone access. |

**For a first run**, choose [VS Code](vs-code.md) or [GitHub Codespaces](codespaces.md). Then [discover the tools](local-mcp-server.md#install-and-discover) and [send a scheduling request](local-mcp-server.md#ask-for-a-scheduling-encounter).

**For the full call**, read the [setup overview](connected-product.md#reproduce-the-connected-voice-product) and the [Supabase project restriction](supabase.md) before provisioning services. For the system design and authorization rules, see [System architecture](../solution-architecture.md) and [Security and governance](../security-governance.md).
