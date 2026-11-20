"""MCP tool: get_scheduling_handoff.

Read-only. Returns the persisted SchedulingHandoff document by handoff_id.
Does not mutate lifecycle state. Unknown handoff_id fails cleanly.

Shared process state (handoff_store) is imported from mcp/state.py.
Tests inject fresh instances via the run() parameter interface.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.state import handoff_store as _handoff_store
from veteran_access_bridge.services.handoff import HandoffStore


def run(
    handoff_id: str,
    *,
    handoff_store: HandoffStore | None = None,
) -> dict[str, Any]:
    """Testable inner function; MCP tool wrapper calls this."""
    hs = handoff_store if handoff_store is not None else _handoff_store

    handoff = hs.get(handoff_id)
    if handoff is None:
        return {
            "found": False,
            "handoff_id": handoff_id,
            "error": f"No handoff found for handoff_id {handoff_id!r}.",
            "synthetic": True,
        }

    payload = to_jsonable(handoff)
    payload["found"] = True
    payload["synthetic"] = True
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_scheduling_handoff",
        annotations={
            "title": "Get Scheduling Handoff",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_scheduling_handoff_tool(
        handoff_id: Annotated[
            str,
            "Handoff ID returned by prepare_scheduling_handoff.",
        ],
    ) -> dict[str, Any]:
        """Retrieve a previously prepared scheduling handoff document by ID.

        Read-only. Does not mutate lifecycle state. Returns an error payload if
        the handoff_id is not found.
        """
        return run(handoff_id)
