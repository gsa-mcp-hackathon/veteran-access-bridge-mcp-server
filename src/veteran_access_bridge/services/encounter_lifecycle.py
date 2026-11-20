"""M6.3c read-only projection of the governed scheduling lifecycle.

This module never advances lifecycle state. It only reads the existing event
and artifact stores so SchedulingEncounter can expose one coherent snapshot of
handoff, selection, verification, Veteran confirmation, and simulated booking.
"""

from __future__ import annotations

from dataclasses import dataclass

from veteran_access_bridge.domain.models import (
    CaseEventType,
    CaseLifecycleState,
    VerificationOutcome,
    VeteranResponse,
)
from veteran_access_bridge.services.booking import BookingStore
from veteran_access_bridge.services.confirmation import ConfirmationStore
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.handoff import HandoffStore
from veteran_access_bridge.services.selection import SelectionStore
from veteran_access_bridge.services.verification import VerificationStore


@dataclass(frozen=True)
class SchedulingDecisionSnapshot:
    """Read-only references to the persisted governed scheduling artifacts."""

    lifecycle_state: CaseLifecycleState | None
    latest_event_type: CaseEventType | None
    event_count: int
    handoff_id: str | None = None
    selection_id: str | None = None
    selected_option_id: str | None = None
    verification_id: str | None = None
    verification_outcome: VerificationOutcome | None = None
    confirmation_request_id: str | None = None
    confirmation_id: str | None = None
    veteran_response: VeteranResponse | None = None
    booking_id: str | None = None
    synthetic: bool = True


def _latest_payload_value(
    event_store: CaseEventStore,
    case_id: str,
    key: str,
) -> str | None:
    for event in reversed(event_store.get_events(case_id)):
        if event.payload and event.payload.get(key) is not None:
            return str(event.payload[key])
    return None


def project_scheduling_decision(
    case_id: str,
    event_store: CaseEventStore,
    *,
    handoff_store: HandoffStore | None = None,
    selection_store: SelectionStore | None = None,
    verification_store: VerificationStore | None = None,
    confirmation_store: ConfirmationStore | None = None,
    booking_store: BookingStore | None = None,
) -> SchedulingDecisionSnapshot:
    """Project the current lifecycle/artifact state without writing anything.

    Stores are optional because an encounter may be assembled before all later
    lifecycle services are active. Event history remains the authoritative
    persisted lifecycle position; artifact stores enrich the snapshot when
    supplied.
    """
    lifecycle = event_store.get_lifecycle_record(case_id)

    if lifecycle is None:
        return SchedulingDecisionSnapshot(
            lifecycle_state=None,
            latest_event_type=None,
            event_count=0,
        )

    handoff_id = _latest_payload_value(event_store, case_id, "handoff_id")
    selection = selection_store.get_for_case(case_id) if selection_store else None
    verification = (
        verification_store.get_for_case(case_id) if verification_store else None
    )
    confirmation_request = (
        confirmation_store.get_request_for_case(case_id)
        if confirmation_store
        else None
    )
    confirmation = (
        confirmation_store.get_confirmation_for_case(case_id)
        if confirmation_store
        else None
    )

    # A selection carries the handoff reference even if the caller omitted the
    # HandoffStore. Event evidence wins only when no selection exists yet.
    if selection is not None:
        handoff_id = selection.handoff_id

    # If a HandoffStore was supplied, never surface a dangling handoff ID as a
    # resolved artifact reference.
    if handoff_id is not None and handoff_store is not None:
        if handoff_store.get(handoff_id) is None:
            handoff_id = None

    booking_id = _latest_payload_value(event_store, case_id, "booking_id")
    if booking_id is not None and booking_store is not None:
        booking = booking_store.get(booking_id)
        if booking is None or booking.case_id != case_id:
            booking_id = None

    return SchedulingDecisionSnapshot(
        lifecycle_state=lifecycle.current_state,
        latest_event_type=lifecycle.last_event_type,
        event_count=lifecycle.event_count,
        handoff_id=handoff_id,
        selection_id=(selection.selection_id if selection else None),
        selected_option_id=(selection.option_id if selection else None),
        verification_id=(verification.verification_id if verification else None),
        verification_outcome=(verification.outcome if verification else None),
        confirmation_request_id=(
            confirmation_request.confirmation_request_id
            if confirmation_request
            else None
        ),
        confirmation_id=(confirmation.confirmation_id if confirmation else None),
        veteran_response=(confirmation.response if confirmation else None),
        booking_id=booking_id,
    )
