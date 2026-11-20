"""MCP tool: validate_booking_preconditions.

Read-only gate. Checks all booking preconditions without writing any state.
Returns a BookingPreconditionResult. Does not reserve slots, create BookingRecord,
or append lifecycle events.

The actual atomic commit (simulated_commit) is a service-layer-only operation
and is never called by the MCP directly.

Shared process state imported from mcp/state.py.
Tests inject fresh instances via run() parameter interface.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from fastmcp import FastMCP

from veteran_access_bridge.adapters.eps import SyntheticEPSAdapter
from veteran_access_bridge.adapters.hsrm import SyntheticHSRMAdapter
from veteran_access_bridge.domain.models import (
    ActorRole,
    AppointmentIntent,
    EPSSlotRecord,
    HSRMAuthorizationRecord,
)
from veteran_access_bridge.mcp.durable_runtime import (
    read_case_from_supabase,
    scheduling_mode,
)
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.state import booking_store as _booking_store
from veteran_access_bridge.mcp.state import confirmation_store as _confirmation_store
from veteran_access_bridge.mcp.state import event_store as _event_store
from veteran_access_bridge.mcp.state import selection_store as _selection_store
from veteran_access_bridge.services.booking import (
    BookingStore,
    validate_booking_preconditions,
)
from veteran_access_bridge.services.confirmation import ConfirmationStore
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.selection import SelectionStore

# Module-level default adapters (shared singletons for MCP usage).
_hsrm_adapter = SyntheticHSRMAdapter()
_eps_adapter = SyntheticEPSAdapter()


def run(
    case_id: str,
    option_id: str,
    slot_id: str,
    source_system: str,
    intended_service: str,
    appointment_intent: str,
    actor_id: str,
    idempotency_key: str,
    *,
    event_store: CaseEventStore | None = None,
    confirmation_store: ConfirmationStore | None = None,
    selection_store: SelectionStore | None = None,
    booking_store: BookingStore | None = None,
    hsrm_record: Optional[HSRMAuthorizationRecord] = None,
    eps_slot: Optional[EPSSlotRecord] = None,
) -> dict[str, Any]:
    """Testable inner function; MCP tool wrapper calls this."""
    if scheduling_mode() == "supabase_test":
        case = read_case_from_supabase(case_id)
        return {
            "case_id": case_id,
            "option_id": option_id,
            "slot_id": slot_id,
            "synthetic": True,
            "read_only": True,
            "creates_booking": False,
            "booking_ready": False,
            "authorization_granted": False,
            "reason": "PRIVATE_SIGNED_VERIFICATION_REQUIRED",
            "case_found": case["found"],
            "persistence": "supabase_test",
        }
    es = event_store if event_store is not None else _event_store
    cs = confirmation_store if confirmation_store is not None else _confirmation_store
    ss = selection_store if selection_store is not None else _selection_store
    bs = booking_store if booking_store is not None else _booking_store

    # Coerce intent string to enum.
    try:
        intent = AppointmentIntent(appointment_intent)
    except ValueError:
        allowed = [i.value for i in AppointmentIntent]
        raise ValueError(
            f"Invalid appointment_intent {appointment_intent!r}. Allowed: {allowed}."
        )

    # For MCP usage, look up HSRM/EPS records if not injected.
    if hsrm_record is None:
        hsrm_record = _hsrm_adapter.get_authorization_for_option(option_id)
    if eps_slot is None:
        eps_slot = _eps_adapter.get_slot(slot_id)

    result = validate_booking_preconditions(
        case_id=case_id,
        option_id=option_id,
        slot_id=slot_id,
        source_system=source_system,
        intended_service=intended_service,
        appointment_intent=intent,
        actor_role=ActorRole.SCHEDULER,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        event_store=es,
        confirmation_store=cs,
        selection_store=ss,
        booking_store=bs,
        hsrm_record=hsrm_record,
        eps_slot=eps_slot,
    )

    payload = to_jsonable(result)
    payload["synthetic"] = True
    payload["creates_booking"] = False
    return payload


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="validate_booking_preconditions",
        annotations={
            "title": "Validate Booking Preconditions",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def validate_booking_preconditions_tool(
        case_id: Annotated[str, "Approved synthetic scheduling case ID."],
        option_id: Annotated[str, "Option ID being booked."],
        slot_id: Annotated[str, "Specific slot identifier (EPS slot or VA slot)."],
        source_system: Annotated[str, "Source system (e.g. VISTA_ISS, EPS)."],
        intended_service: Annotated[str, "Specialty/service (e.g. CARDIOLOGY)."],
        appointment_intent: Annotated[
            Literal["INITIAL_CONSULT", "FOLLOW_UP"],
            "Explicit appointment intent. FOLLOW_UP fails closed for the "
            "EPS initial-consult path.",
        ],
        actor_id: Annotated[str, "Opaque Scheduler identifier (synthetic/demo only)."],
        idempotency_key: Annotated[
            str,
            "Caller-supplied deduplication key for this booking attempt.",
        ],
    ) -> dict[str, Any]:
        """Read-only check of all booking preconditions.

        Validates lifecycle state, Veteran confirmation, Scheduler role,
        HSRM authorization (Community Care), EPS slot availability (Community Care),
        appointment intent, and idempotency. Does not write any state.
        A passed result does not constitute a booking commitment.
        """
        return run(
            case_id,
            option_id,
            slot_id,
            source_system,
            intended_service,
            appointment_intent,
            actor_id,
            idempotency_key,
        )
