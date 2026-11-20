"""M6.3c governed lifecycle projection tests."""

from datetime import datetime, timedelta, timezone

from veteran_access_bridge.domain.models import (
    ActorRole,
    AppointmentIntent,
    BookingRecord,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    ConfirmationRequest,
    OptionReadiness,
    OptionSelectionRecord,
    VerificationOutcome,
    VerificationResult,
    VeteranConfirmationRecord,
    VeteranResponse,
)
from veteran_access_bridge.services.booking import BookingStore
from veteran_access_bridge.services.confirmation import ConfirmationStore
from veteran_access_bridge.services.encounter_lifecycle import (
    project_scheduling_decision,
)
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.selection import SelectionStore
from veteran_access_bridge.services.verification import VerificationStore

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
CASE = "DEMO-CARD-M63C-001"
OPTION = "OPT-VISTA-M63C-001"
HANDOFF = "handoff-m63c-001"
SELECTION = "sel-m63c-001"


def _append(
    store: CaseEventStore,
    *,
    from_state: CaseLifecycleState,
    to_state: CaseLifecycleState,
    event_type: CaseEventType,
    key: str,
    payload: dict | None = None,
    role: ActorRole = ActorRole.SYSTEM,
) -> None:
    store.append(
        CaseEvent(
            event_id=f"evt-{key}",
            case_id=CASE,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            actor_role=role,
            actor_id=role.value.lower(),
            occurred_at=T0,
            idempotency_key=f"idem-{key}",
            payload=payload or {},
        )
    )


def _seed_to_human_review(store: CaseEventStore) -> None:
    _append(
        store,
        from_state=CaseLifecycleState.REQUEST_RECEIVED,
        to_state=CaseLifecycleState.READY_TO_SEARCH,
        event_type=CaseEventType.WORKFLOW_GATE_EVALUATED,
        key="ready",
    )
    _append(
        store,
        from_state=CaseLifecycleState.READY_TO_SEARCH,
        to_state=CaseLifecycleState.VA_OPTIONS_AVAILABLE,
        event_type=CaseEventType.SEARCH_EXECUTED,
        key="search",
    )
    _append(
        store,
        from_state=CaseLifecycleState.VA_OPTIONS_AVAILABLE,
        to_state=CaseLifecycleState.READY_FOR_HANDOFF,
        event_type=CaseEventType.OPTIONS_ASSESSED,
        key="assessed",
    )
    _append(
        store,
        from_state=CaseLifecycleState.READY_FOR_HANDOFF,
        to_state=CaseLifecycleState.HUMAN_REVIEW,
        event_type=CaseEventType.HANDOFF_PREPARED,
        key="handoff",
        payload={"handoff_id": HANDOFF},
    )


def _selection_store() -> SelectionStore:
    store = SelectionStore()
    store.put(
        OptionSelectionRecord(
            selection_id=SELECTION,
            case_id=CASE,
            handoff_id=HANDOFF,
            option_id=OPTION,
            readiness_at_selection=OptionReadiness.AVAILABLE,
            requires_verification=False,
            selected_at=T0,
            selected_by_role=ActorRole.SCHEDULER,
            selected_by_id="scheduler-1",
            idempotency_key="selection-key",
        )
    )
    return store


def test_projection_is_read_only_and_preserves_handoff_reference():
    events = CaseEventStore()
    _seed_to_human_review(events)
    before = events.get_events(CASE)

    snapshot = project_scheduling_decision(CASE, events)

    after = events.get_events(CASE)
    assert before == after
    assert snapshot.lifecycle_state == CaseLifecycleState.HUMAN_REVIEW
    assert snapshot.latest_event_type == CaseEventType.HANDOFF_PREPARED
    assert snapshot.handoff_id == HANDOFF
    assert snapshot.event_count == 4
    assert snapshot.selection_id is None
    assert snapshot.booking_id is None


def test_projection_enriches_existing_selection_verification_and_confirmation():
    events = CaseEventStore()
    _seed_to_human_review(events)
    selections = _selection_store()
    verifications = VerificationStore()
    confirmations = ConfirmationStore()

    _append(
        events,
        from_state=CaseLifecycleState.HUMAN_REVIEW,
        to_state=CaseLifecycleState.OPTION_SELECTED,
        event_type=CaseEventType.OPTION_SELECTED,
        key="selected",
        payload={"selection_id": SELECTION, "option_id": OPTION},
        role=ActorRole.SCHEDULER,
    )
    _append(
        events,
        from_state=CaseLifecycleState.OPTION_SELECTED,
        to_state=CaseLifecycleState.VERIFIED_BOOKABLE,
        event_type=CaseEventType.VERIFICATION_PASSED,
        key="verified",
        payload={"selection_id": SELECTION, "option_id": OPTION},
    )
    verifications.put(
        VerificationResult(
            verification_id="ver-m63c-001",
            case_id=CASE,
            option_id=OPTION,
            source_system="VISTA_ISS",
            outcome=VerificationOutcome.VERIFIED,
            evidence_ref=None,
            verified_at=T0,
            requires_authorization=False,
            requires_human_review=False,
            idempotency_key="verify-key",
        )
    )

    request = ConfirmationRequest(
        confirmation_request_id="cr-m63c-001",
        case_id=CASE,
        option_id=OPTION,
        selection_id=SELECTION,
        requested_at=T0,
        requested_by_role=ActorRole.SYSTEM,
    )
    confirmations.put_request(request)
    _append(
        events,
        from_state=CaseLifecycleState.VERIFIED_BOOKABLE,
        to_state=CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
        event_type=CaseEventType.VETERAN_CONFIRMATION_REQUESTED,
        key="confirmation-requested",
        payload={"confirmation_request_id": request.confirmation_request_id},
    )

    confirmation = VeteranConfirmationRecord(
        confirmation_id="conf-m63c-001",
        confirmation_request_id=request.confirmation_request_id,
        case_id=CASE,
        option_id=OPTION,
        response=VeteranResponse.CONFIRMED,
        responded_at=T0,
        actor_role=ActorRole.VETERAN,
        actor_id="veteran-1",
        idempotency_key="confirmation-key",
    )
    confirmations.put_confirmation(confirmation)
    _append(
        events,
        from_state=CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
        to_state=CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
        event_type=CaseEventType.VETERAN_CONFIRMED,
        key="confirmed",
        payload={"confirmation_id": confirmation.confirmation_id},
        role=ActorRole.VETERAN,
    )

    snapshot = project_scheduling_decision(
        CASE,
        events,
        selection_store=selections,
        verification_store=verifications,
        confirmation_store=confirmations,
    )

    assert snapshot.lifecycle_state == CaseLifecycleState.PENDING_SCHEDULER_APPROVAL
    assert snapshot.handoff_id == HANDOFF
    assert snapshot.selection_id == SELECTION
    assert snapshot.selected_option_id == OPTION
    assert snapshot.verification_id == "ver-m63c-001"
    assert snapshot.verification_outcome == VerificationOutcome.VERIFIED
    assert snapshot.confirmation_request_id == "cr-m63c-001"
    assert snapshot.confirmation_id == "conf-m63c-001"
    assert snapshot.veteran_response == VeteranResponse.CONFIRMED


def test_projection_resolves_simulated_booking_without_creating_it():
    events = CaseEventStore()
    _seed_to_human_review(events)
    selections = _selection_store()
    confirmations = ConfirmationStore()
    bookings = BookingStore()

    _append(
        events,
        from_state=CaseLifecycleState.HUMAN_REVIEW,
        to_state=CaseLifecycleState.OPTION_SELECTED,
        event_type=CaseEventType.OPTION_SELECTED,
        key="selected-book",
    )
    _append(
        events,
        from_state=CaseLifecycleState.OPTION_SELECTED,
        to_state=CaseLifecycleState.VERIFIED_BOOKABLE,
        event_type=CaseEventType.VERIFICATION_PASSED,
        key="verified-book",
    )
    _append(
        events,
        from_state=CaseLifecycleState.VERIFIED_BOOKABLE,
        to_state=CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
        event_type=CaseEventType.VETERAN_CONFIRMATION_REQUESTED,
        key="request-book",
    )
    _append(
        events,
        from_state=CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
        to_state=CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
        event_type=CaseEventType.VETERAN_CONFIRMED,
        key="confirm-book",
        role=ActorRole.VETERAN,
    )

    booking = BookingRecord(
        booking_id="bk-m63c-001",
        case_id=CASE,
        option_id=OPTION,
        slot_id="VISTA-SLOT-M63C-001",
        patient_id="5000335",
        consult_id="CONSULT-M63C-001",
        handoff_id=HANDOFF,
        facility_name="Synthetic VA Medical Center",
        appointment_intent=AppointmentIntent.INITIAL_CONSULT,
        appointment_start=T0 + timedelta(days=7),
        appointment_end=T0 + timedelta(days=7, minutes=30),
        source_system="VISTA_ISS",
        booked_at=T0,
        booked_by_role=ActorRole.SCHEDULER,
        booked_by_id="scheduler-1",
        idempotency_key="booking-key",
    )
    bookings.put(booking)
    _append(
        events,
        from_state=CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
        to_state=CaseLifecycleState.BOOKED_SIMULATED,
        event_type=CaseEventType.BOOKED_SIMULATED,
        key="booked",
        payload={"booking_id": booking.booking_id, "option_id": OPTION},
        role=ActorRole.SCHEDULER,
    )

    before_events = events.get_events(CASE)
    before_bookings = len(bookings)

    snapshot = project_scheduling_decision(
        CASE,
        events,
        selection_store=selections,
        confirmation_store=confirmations,
        booking_store=bookings,
    )

    assert events.get_events(CASE) == before_events
    assert len(bookings) == before_bookings
    assert snapshot.lifecycle_state == CaseLifecycleState.BOOKED_SIMULATED
    assert snapshot.booking_id == booking.booking_id
