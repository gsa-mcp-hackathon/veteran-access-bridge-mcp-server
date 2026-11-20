"""MCP wrapper for the existing multi-source availability search service."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.cases import demo_as_of, load_demo_case
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.services.search import search_availability


def run(case_id: str) -> dict[str, Any]:
    patient, consult = load_demo_case(case_id)
    result = search_availability(patient, consult, _as_of=demo_as_of())
    payload = to_jsonable(result)
    payload["case_id"] = case_id
    payload["synthetic"] = True
    payload["creates_scheduling_handoff"] = False
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="search_availability",
        annotations={
            "title": "Search Scheduling Availability",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def search_availability_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
    ) -> dict[str, Any]:
        """Search all synthetic sources after deterministic workflow gating."""
        return run(case_id)
