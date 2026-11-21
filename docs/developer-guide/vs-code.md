# Run the MCP server on your computer with VS Code

Use this guide if you chose **On my computer with VS Code**. First, you’ll ask the server which sample appointments fit a Primary Care follow-up. Then you’ll use your own VA Facilities sandbox key to look up a facility in Topeka. You can finish the first checkpoint before requesting a key. Neither checkpoint requires IBM, LiveKit, Deepgram or Supabase.

## Checkpoint 1 · Send a scheduling request

### Open your own copy of the submission

1. Install [Visual Studio Code](https://code.visualstudio.com/download), [Git](https://git-scm.com/downloads) and [uv](https://docs.astral.sh/uv/getting-started/installation/) for your operating system. Open or restart VS Code after installation. The setup command below lets uv obtain Python 3.12 if needed.
2. In VS Code, press **Ctrl+Shift+P** on Windows/Linux or **Command+Shift+P** on macOS. Type **Git: Clone**, select that command, and paste this repository URL:

   `https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git`
3. Choose a parent folder where you keep projects, then select **Open** when the clone completes. If you already cloned this submission, use **File → Open Folder** and select **veteran-access-bridge-mcp-server**.
4. Select **Terminal → New Terminal**. Commands below go in this panel at the bottom of VS Code. The first checkpoint uses identical commands on Windows, macOS and Linux.

### Check the folder and install the server

```text
git branch --show-current
git rev-parse --short HEAD
```

A fresh clone should show **main** and a short commit ID. Save the ID with your results. If Git reports that this is not a repository, reopen the cloned folder and create a new terminal.

```text
uv sync --locked --group dev --python 3.12
```

Wait for the prompt to return. The first run creates a **.venv** folder and installs packages. If your terminal cannot find `uv`, close and reopen VS Code after installing it, then try `uv --version`.

### Discover tools and read the sample encounter

```text
uv run --no-sync python scripts/list_local_mcp_tools.py
```

Find **get_scheduling_encounter** in the list. The default configuration reports **21 tools advertised by this configuration**. The client starts the MCP server for you and closes it when the command finishes.

```text
uv run --no-sync python scripts/read_scheduling_encounter.py DEMO-PC-5000999-001
```

This sample patient is established and requests a 30-minute, in-person Primary Care follow-up. Find these three IDs in the terminal output:

| Sample slot | What the server decided |
|---|---|
| `VISTA-SLOT-PC-5000999-001` | Eligible for this request. |
| `VISTA-SLOT-PC-5000999-002` | Excluded. The new-patient slot conflicts with the visit intent, patient classification and template. |
| `FEHR-SLOT-PC-5000999-001` | Eligible for this request. |

**Your first checkpoint:** Three sample slots checked, two qualify. The final fields show `read_only: true` and `booking_created: false`. This request used files in your clone. To verify an external connection, continue below.

## Checkpoint 2 · Connect to the VA Facilities sandbox

### Request your own key

Open the [VA Facilities sandbox access form](https://developer.va.gov/explore/api/va-facilities/sandbox-access). Enter your name, email, organization and a brief description of how you’ll use the API. For example: “I’m testing a scheduling prototype that looks up public facility information by station ID.” Review the terms and submit the form if you agree. Continue once you have your key.

### Enter the key privately in the VS Code terminal

Choose the instructions for your terminal. Keep it open through both lookups. These settings apply to programs started from this terminal session. You do not need to create a GitHub secret or edit a project file to store the key.

**Windows · PowerShell.** Paste the block. When prompted, paste your key and press Enter. The prompt conceals the value.

```powershell
$secret = Read-Host "VA Facilities sandbox key" -AsSecureString
$env:VA_FACILITIES_API_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
$env:VA_SANDBOX_ENABLED = "true"
$env:VA_FACILITIES_READ_ENABLED = "true"
if ($env:VA_FACILITIES_API_KEY) { "Key available" } else { "Key missing" }
```

**macOS or Linux · Bash.** Type `bash` and press Enter first, including on a Mac that opens zsh by default. Run the following **one line at a time**. After the first line, paste your key at the hidden prompt and press Enter.

```bash
read -rsp "VA Facilities sandbox key: " VA_FACILITIES_API_KEY
printf '\n'
export VA_FACILITIES_API_KEY
export VA_SANDBOX_ENABLED=true VA_FACILITIES_READ_ENABLED=true
if [ -n "${VA_FACILITIES_API_KEY:-}" ]; then echo "Key available"; else echo "Key missing"; fi
```

**Key available** confirms the terminal received a value. The next request checks whether VA accepts it. The first enablement setting allows VA sandbox reads. The second turns on the Facilities adapter.

### Test the key directly against VA

Run this single command in the same terminal on either platform:

```text
uv run --no-sync python -c "import os,httpx; r=httpx.get('https://sandbox-api.va.gov/services/va_facilities/v1/facilities/vha_589A5',headers={'apikey':os.environ['VA_FACILITIES_API_KEY']},timeout=15); print('HTTP',r.status_code); r.raise_for_status(); f=r.json()['data']; print('Facility ID:',f['id']); print('Facility name:',f['attributes']['name'])"
```

Look for **HTTP 200**, **vha_589A5**, and the name VA returned. Keep the name for comparison. If you see 401 or 403, check the key and its sandbox access before trying MCP. [VA Facilities API reference](https://developer.va.gov/explore/facilities/docs/facilities)

### Ask the existing MCP tool for the same facility

In VS Code choose **File → New Text File**. Paste the following small client and save it as **review_facility.py** inside the **.venv** folder created in checkpoint 1. This is a disposable example for your local environment. Its settings come from the terminal.

```python
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def lookup():
    settings = {"VAB_MCP_TRANSPORT": "stdio"}
    for name in ("VA_SANDBOX_ENABLED", "VA_FACILITIES_READ_ENABLED", "VA_FACILITIES_API_KEY"):
        settings[name] = os.environ.get(name, "")
    server = StdioServerParameters(
        command=sys.executable, args=["-m", "veteran_access_bridge.mcp.app"], env=settings
    )
    async with stdio_client(server) as streams, ClientSession(*streams) as session:
        await session.initialize()
        reply = await session.call_tool("get_va_sandbox_health_facility", {"facility_id": "vha_589A5"})
        if reply.isError:
            raise SystemExit("MCP tool call failed. Check the server messages above.")
        result = reply.structuredContent or json.loads(reply.content[0].text)
        for field in ("status", "facility_id", "name", "source", "source_verified"):
            print(f"{field}: {json.dumps(result.get(field))}")

asyncio.run(lookup())
```

Return to the same terminal, still in the repository’s top-level folder, and run:

```text
uv run --no-sync python .venv/review_facility.py
```

| Check | Direct VA result | Expected MCP result with a working key |
|---|---|---|
| Successful read | HTTP 200 | `status: "AVAILABLE"` |
| Same record | ID `vha_589A5` and VA’s returned name | Same facility ID and name |
| Where the data came from | VA sandbox endpoint | `source: "VA_FACILITIES_API_SANDBOX"` and `source_verified: true` |

**Your second checkpoint:** Count the connection as verified when both results identify the same facility and MCP reports the verified VA source. A facility lookup supplies location metadata. Patient assignment, appointment inventory and booking require separate checks.

**If VA succeeds but MCP says UNAVAILABLE**, make sure the two enablement settings and the key were set in the terminal that launched the client. If the key is missing, expect `source: "none_configured"` and `source_verified: false`. If Python cannot find the example, confirm its filename and folder using the VS Code Explorer.

**Finished?** Use the trash-can icon in the terminal panel to terminate that session and discard its temporary environment. The [scheduling answer key](local-mcp-server.md#compare-with-the-answer-key) gives you more local checks to try.
