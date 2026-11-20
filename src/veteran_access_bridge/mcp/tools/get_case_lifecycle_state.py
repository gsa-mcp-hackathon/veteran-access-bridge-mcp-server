"""MCP tool: get_case_lifecycle_state.

Read-only. Returns the current lifecycle state and full event history for a
synthetic scheduling case.

Returns:
    found=True  → current_state, event_count, last_event_at, event_history
    found=False → error message for unknown case_id

Does not mutate lifecycle state. Does not retrieve PHI.
Shared process state (event_store) is imported from mcp/state.py.
Tests inject fresh instances via the run() parameter interface.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.durable_runtime import (
    read_case_from_supabase,
    scheduling_mode,
)
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.state import event_store as _event_store
from veteran_access_bridge.services.events import CaseEventStore


def run(
    case_id: str,
    *,
    event_store: CaseEventStore | None = None,
    include_history: bool = False,
) -> dict[str, Any]:
    """Testable inner function; MCP tool wrapper calls this."""
    if scheduling_mode() == "supabase_test":
        return read_case_from_supabase(case_id, include_history=include_history)
    es = event_store if event_store is not None else _event_store

    record = es.get_lifecycle_record(case_id)
    if record is None:
        return {
            "found": False,
            "case_id": case_id,
            "error": f"No lifecycle history found for case_id {case_id!r}.",
            "synthetic": True,
        }

    result: dict[str, Any] = {
        "found": True,
        "synthetic": True,
        **to_jsonable(record),
    }

    if include_history:
        events = es.get_events(case_id)
        result["event_history"] = [to_jsonable(e) for e in events]

    return result


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_case_lifecycle_state",
        annotations={
            "title": "Get Case Lifecycle State",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_case_lifecycle_state_tool(
        case_id: Annotated[str, "Synthetic scheduling case ID."],
        include_history: Annotated[
            bool,
            "When true, include the full ordered event history in the response. "
            "Default false — returns current state summary only.",
        ] = False,
    ) -> dict[str, Any]:
        """Return the current lifecycle state for a synthetic scheduling case.

        Read-only. Returns:
        - current_state: the most recent lifecycle state
        - last_event_type: the event that produced the current state
        - last_event_at: ISO 8601 timestamp of the last event
        - event_count: total number of lifecycle events recorded
        - event_history (if include_history=true): full ordered event list

        Returns found=false with an error message if the case_id is unknown.
        Does not mutate lifecycle state. Does not expose PHI.
        """
        return run(case_id, include_history=include_history)
