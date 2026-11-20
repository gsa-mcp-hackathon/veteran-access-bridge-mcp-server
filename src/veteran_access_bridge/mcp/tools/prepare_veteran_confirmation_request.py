"""MCP tool: prepare_veteran_confirmation_request.

Preparatory — not read-only. Advances VERIFIED_BOOKABLE → PENDING_VETERAN_CONFIRMATION
and creates a ConfirmationRequest artifact for the Veteran to review.

Actor is always SYSTEM — no role parameter. The scheduling decision was already
captured at record_option_selection (SCHEDULER); verification was performed at
record_verification_result (SCHEDULER). This step is a mechanical pipeline handoff.

Idempotent: same case_id + selection_id + option_id always produces the same
confirmation_request_id. Repeated calls return the existing request with no
duplicate event.

Preparation does not constitute Veteran consent.

Shared process state imported from mcp/state.py.
Tests inject fresh instances via run() parameter interface.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.state import confirmation_store as _confirmation_store
from veteran_access_bridge.mcp.state import event_store as _event_store
from veteran_access_bridge.mcp.state import selection_store as _selection_store
from veteran_access_bridge.services.confirmation import (
    ConfirmationStore,
    prepare_veteran_confirmation_request,
)
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.selection import SelectionStore


def run(
    case_id: str,
    option_id: str,
    selection_id: str,
    *,
    event_store: CaseEventStore | None = None,
    selection_store: SelectionStore | None = None,
    confirmation_store: ConfirmationStore | None = None,
) -> dict[str, Any]:
    """Testable inner function; MCP tool wrapper calls this."""
    es = event_store if event_store is not None else _event_store
    ss = selection_store if selection_store is not None else _selection_store
    cs = confirmation_store if confirmation_store is not None else _confirmation_store

    request = prepare_veteran_confirmation_request(
        case_id=case_id,
        option_id=option_id,
        selection_id=selection_id,
        event_store=es,
        selection_store=ss,
        confirmation_store=cs,
    )

    payload = to_jsonable(request)
    payload["synthetic"] = True
    payload["creates_booking"] = False
    payload["is_veteran_consent"] = False
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="prepare_veteran_confirmation_request",
        annotations={
            "title": "Prepare Veteran Confirmation Request",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def prepare_veteran_confirmation_request_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
        option_id: Annotated[str, "Option ID of the verified/bookable option."],
        selection_id: Annotated[
            str,
            "Selection ID from record_option_selection. "
            "Scopes the confirmation request to this specific selection "
            "lifecycle path.",
        ],
    ) -> dict[str, Any]:
        """Prepare a Veteran confirmation request.

        Advances the case to PENDING_VETERAN_CONFIRMATION.

        Creates a ConfirmationRequest artifact for the Veteran to review.
        This is a mechanical system step — preparation is not Veteran consent.
        Idempotent: repeated calls with the same inputs return the existing request
        without appending a duplicate event. Does not book, authorize, or confirm.
        """
        return run(case_id, option_id, selection_id)
