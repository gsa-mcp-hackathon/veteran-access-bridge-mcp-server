"""Read one synthetic encounter through the installed MCP server."""
import argparse
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


async def read(streams, case_id):
    async with ClientSession(*streams[:2]) as session:
        await session.initialize()
        reply = await session.call_tool("get_scheduling_encounter", {"case_id": case_id})
        if reply.isError:
            for part in reply.content:
                if part.type == "text":
                    print(part.text, file=sys.stderr)
            return 1
        data = reply.structuredContent or json.loads(reply.content[0].text)
        fields = ("patient_classification", "slot_eligibility", "read_only", "booking_created")
        print(json.dumps({key: data[key] for key in fields}, indent=2))
        return 0


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id", nargs="?", default="DEMO-PC-5000999-001")
    parser.add_argument("--local-http", action="store_true", help="Use the container on localhost:8080")
    args = parser.parse_args()
    if args.local_http:
        key = os.environ.get("VAB_MCP_API_KEY")
        if not key:
            parser.error("Set VAB_MCP_API_KEY to your local container's key.")
        async with streamablehttp_client("http://127.0.0.1:8080/mcp/", headers={"Authorization": f"Bearer {key}"}) as streams:
            return await read(streams, args.case_id)
    server = StdioServerParameters(command=sys.executable, args=["-m", "veteran_access_bridge.mcp.app"], env={"VAB_MCP_TRANSPORT": "stdio"})
    async with stdio_client(server) as streams:
        return await read(streams, args.case_id)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
