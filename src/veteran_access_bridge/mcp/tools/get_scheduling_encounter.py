"""Read-only MCP wrapper for the unified M6.3 Scheduling Encounter."""

from __future__ import annotations

from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.cases import (
    demo_as_of,
    load_demo_encounter_case,
    load_demo_scheduling_context,
)
from veteran_access_bridge.mcp.durable_runtime import (
    read_case_from_supabase,
    scheduling_mode,
)
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.services.booking import BookingStore
from veteran_access_bridge.services.confirmation import ConfirmationStore
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.handoff import HandoffStore
from veteran_access_bridge.services.scheduling_encounter import (
    assemble_scheduling_encounter,
)
from veteran_access_bridge.services.selection import SelectionStore
from veteran_access_bridge.services.verification import VerificationStore


def run(
    case_id: str,
    *,
    event_store: CaseEventStore | None = None,
    handoff_store: HandoffStore | None = None,
    selection_store: SelectionStore | None = None,
    verification_store: VerificationStore | None = None,
    confirmation_store: ConfirmationStore | None = None,
    booking_store: BookingStore | None = None,
) -> dict[str, Any]:
    """Return one unified synthetic scheduling encounter without writing state."""
    if scheduling_mode() == "supabase_test":
        record = read_case_from_supabase(case_id, include_history=True)
        return {
            **record,
            "read_only": True,
            "booking_created": False,
            "community_care_authorization_granted": False,
            "eps_invoked": False,
            "durable_projection": True,
            "notes": "Persisted case projection; unverified external evidence excluded",
        }
    if event_store is None:
        from veteran_access_bridge.mcp import state

        event_store = state.event_store
        handoff_store = handoff_store or state.handoff_store
        selection_store = selection_store or state.selection_store
        verification_store = verification_store or state.verification_store
        confirmation_store = confirmation_store or state.confirmation_store
        booking_store = booking_store or state.booking_store

    patient, consult = load_demo_encounter_case(case_id)
    request, relationship = load_demo_scheduling_context(case_id)

    encounter = assemble_scheduling_encounter(
        request=request,
        patient=patient,
        consult=consult,
        relationship=relationship,
        as_of=demo_as_of(),
        event_store=event_store,
        handoff_store=handoff_store,
        selection_store=selection_store,
        verification_store=verification_store,
        confirmation_store=confirmation_store,
        booking_store=booking_store,
    )

    payload = to_jsonable(encounter)
    payload.update(
        {
            "case_id": case_id,
            "synthetic": True,
            "read_only": True,
            "preferences_create_eligibility": False,
            "community_care_authorization_granted": False,
            "eps_invoked": False,
            "booking_created": False,
        }
    )
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="get_scheduling_encounter",
        annotations={
            "title": "Get Governed Scheduling Encounter",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def get_scheduling_encounter_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
    ) -> dict[str, Any]:
        """Assemble request, classification, capacity, access standard, preferences,
        and current governed lifecycle state in one read-only encounter.
        """
        return run(case_id)
