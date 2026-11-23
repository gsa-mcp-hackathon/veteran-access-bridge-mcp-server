# Backend release contents

Source snapshot: [ea0880f](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server). The [file inventory](source-inventory.csv) maps each tracked source path to its submission location or explains why it stays upstream.

| To reproduce or inspect | Begin here |
| --- | --- |
| Local MCP tool discovery and fixture checks | [Local setup](../docs/developer-guide/local-mcp-server.md) and [backend tests](../tests/README.md) |
| Hosted scheduling and CRM schema | [Database setup order](../db/README.md) |
| Avery's agent and instructions | [Agent guide](../agents/README.md) |
| Backend and voice-worker images | [Deployment entry points](../deploy/README.md) |
| A fresh Primary Care gold evaluation | [Reviewer command](../eval/primary-care/README.md) |
| Recorded results and proposed caller scenarios | [Evaluation guide](../eval/README.md) |
| The browser interface used in the demo | [Companion frontend at its release revision](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/frontend) |

The GSA repository maintains its own Pages content, CI and reviewer navigation. Development archives, old presentation drafts, private-environment run histories and publisher workflows stay in the pinned source. The locally reproducible checks do not require hosting credentials. A hosted rehearsal additionally needs the documented service connections, authorized credentials and provisioned fixtures.
