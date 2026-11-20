"""List the tools advertised by the installed server over stdio."""

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    async with stdio_client(StdioServerParameters(command="veteran-access-mcp")) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            page = await session.list_tools()
            tools = list(page.tools)
            while page.nextCursor:
                page = await session.list_tools(cursor=page.nextCursor)
                tools.extend(page.tools)
            for tool in sorted(tools, key=lambda item: item.name):
                print(tool.name)
            print(f"{len(tools)} tools advertised by this configuration")


if __name__ == "__main__":
    asyncio.run(main())
