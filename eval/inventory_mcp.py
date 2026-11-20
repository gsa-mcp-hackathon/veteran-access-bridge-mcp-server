"""Capture actual registered MCP schemas without opening a network listener."""

import asyncio
import json
from pathlib import Path

from fastmcp import Client

from veteran_access_bridge.mcp.app import mcp


async def main():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    data = [tool.model_dump(mode="json") for tool in tools]
    out = Path("eval/results/20261114-baseline/tool-inventory.json")
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    for tool in data:
        print(tool["name"], tool.get("annotations"), tool["inputSchema"])


if __name__ == "__main__":
    asyncio.run(main())
