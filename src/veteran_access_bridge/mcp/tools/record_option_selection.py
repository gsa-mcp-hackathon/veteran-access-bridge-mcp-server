"""MCP tool: record_option_selection.

State-recording — not read-only. Records a Scheduler's option selection and
advances the case lifecycle to OPTION_SELECTED. Idempotent: same
idempotency_key + identical material fields → return existing record, one event.
Conflicting reuse of idempotency_key fails closed.

Selection does not mean authorization, verification, booking, or confirmation.

Shared process state imported from mcp/state.py.
Tests inject fresh instances via run() parameter interface.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.domain.models import ActorRole
from veteran_access_bridge.mcp.durable_runtime import require_private_durable_writer
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.state import event_store as _event_store
from veteran_access_bridge.mcp.state import handoff_store as _handoff_store
from veteran_access_bridge.mcp.state import selection_store as _selection_store
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.handoff import HandoffStore
from veteran_access_bridge.services.selection import (
    SelectionStore,
    record_option_selection,
)


def run(
    case_id: str,
    handoff_id: str,
    option_id: str,
    actor_id: str,
    idempotency_key: str,
    *,
    event_store: CaseEventStore | None = None,
    handoff_store: HandoffStore | None = None,
    selection_store: SelectionStore | None = None,
) -> dict[str, Any]:
    """Testable inner function; MCP tool wrapper calls this."""
    require_private_durable_writer()
    es = event_store if event_store is not None else _event_store
    hs = handoff_store if handoff_store is not None else _handoff_store
    ss = selection_store if selection_store is not None else _selection_store

    record = record_option_selection(
        case_id=case_id,
        handoff_id=handoff_id,
        option_id=option_id,
        actor_role=ActorRole.SCHEDULER,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        event_store=es,
        handoff_store=hs,
        selection_store=ss,
    )

    payload = to_jsonable(record)
    payload["synthetic"] = True
    payload["creates_booking"] = False
    payload["creates_confirmation"] = False
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="record_option_selection",
        annotations={
            "title": "Record Option Selection",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def record_option_selection_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
        handoff_id: Annotated[str, "Handoff ID from prepare_scheduling_handoff."],
        option_id: Annotated[str, "Option ID to select."],
        actor_id: Annotated[str, "Opaque Scheduler identifier (synthetic/demo only)."],
        idempotency_key: Annotated[
            str,
            "Caller-supplied deduplication key. Same key + same selection = no-op. "
            "Same key + different selection = error.",
        ],
    ) -> dict[str, Any]:
        """Record a Scheduler's option selection and advance to OPTION_SELECTED.

        Idempotent: repeated calls with the same idempotency_key and identical
        selection data return the existing record without appending a duplicate event.
        Conflicting reuse of idempotency_key (different option/case/actor) raises an
        error and writes no state. Does not book, authorize, verify, or confirm.
        """
        return run(case_id, handoff_id, option_id, actor_id, idempotency_key)
