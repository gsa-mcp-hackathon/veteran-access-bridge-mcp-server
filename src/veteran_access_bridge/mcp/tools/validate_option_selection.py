"""MCP tool: validate_option_selection.

Read-only. Validates that a specific option from a prepared handoff may be
selected by the Scheduler. Does not advance lifecycle state. Returns a
structured OptionSelectionValidation result.

Shared process state imported from mcp/state.py.
Tests inject fresh instances via run() parameter interface.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.state import event_store as _event_store
from veteran_access_bridge.mcp.state import handoff_store as _handoff_store
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.handoff import HandoffStore
from veteran_access_bridge.services.selection import validate_option_selection


def run(
    case_id: str,
    handoff_id: str,
    option_id: str,
    *,
    event_store: CaseEventStore | None = None,
    handoff_store: HandoffStore | None = None,
) -> dict[str, Any]:
    """Testable inner function; MCP tool wrapper calls this."""
    es = event_store if event_store is not None else _event_store
    hs = handoff_store if handoff_store is not None else _handoff_store

    result = validate_option_selection(case_id, handoff_id, option_id, es, hs)
    payload = to_jsonable(result)
    payload["case_id"] = case_id
    payload["handoff_id"] = handoff_id
    payload["option_id"] = option_id
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="validate_option_selection",
        annotations={
            "title": "Validate Option Selection",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def validate_option_selection_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
        handoff_id: Annotated[str, "Handoff ID from prepare_scheduling_handoff."],
        option_id: Annotated[str, "Option ID to validate for selection."],
    ) -> dict[str, Any]:
        """Validate that an option from a prepared handoff may be selected.

        Read-only. Returns a structured validation result with valid=True/False,
        the option details on success, and a reason string on failure.
        Does not advance lifecycle state. Safe to call before record_option_selection.
        """
        return run(case_id, handoff_id, option_id)
