"""MCP tool: prepare_scheduling_handoff.

Preparatory — not read-only. Creates a SchedulingHandoff review artifact.
Idempotent: identical inputs produce the same handoff_id and no duplicate event.
Does not select, verify, authorize, or book any option.

Shared process state (event_store, handoff_store) is imported from
mcp/state.py. Tests inject fresh instances via the run() parameter interface.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.cases import demo_as_of, load_demo_case
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.state import event_store as _event_store
from veteran_access_bridge.mcp.state import handoff_store as _handoff_store
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.handoff import (
    HandoffStore,
    prepare_scheduling_handoff,
)
from veteran_access_bridge.services.search import search_availability


def run(
    case_id: str,
    *,
    event_store: CaseEventStore | None = None,
    handoff_store: HandoffStore | None = None,
) -> dict[str, Any]:
    """Testable inner function; MCP tool wrapper calls this."""
    es = event_store if event_store is not None else _event_store
    hs = handoff_store if handoff_store is not None else _handoff_store

    patient, consult = load_demo_case(case_id)
    search_result = search_availability(patient, consult, _as_of=demo_as_of())

    handoff = prepare_scheduling_handoff(
        case_id=case_id,
        search_result=search_result,
        event_store=es,
        handoff_store=hs,
        _as_of=demo_as_of(),
    )

    payload = to_jsonable(handoff)
    payload["synthetic"] = True
    payload["creates_booking"] = False
    payload["creates_selection"] = False
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="prepare_scheduling_handoff",
        annotations={
            "title": "Prepare Scheduling Handoff",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def prepare_scheduling_handoff_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
    ) -> dict[str, Any]:
        """Prepare a governed scheduling handoff artifact for scheduler review.

        Filters available options to those viable for scheduler review and records
        a HANDOFF_PREPARED lifecycle event. Does not select, verify, authorize, or
        book any option. Idempotent: repeated calls with the same case return the
        same handoff_id without appending a duplicate event.
        """
        return run(case_id)
