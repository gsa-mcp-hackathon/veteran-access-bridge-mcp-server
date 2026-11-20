#!/usr/bin/env python
"""watsonx Orchestrate local MCP toolkit entrypoint."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from veteran_access_bridge.mcp.app import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="stdio")
