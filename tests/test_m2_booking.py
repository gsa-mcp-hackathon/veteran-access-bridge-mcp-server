"""M2-7 Booking gate tests.

Covers all 25 required tests plus the additional refinement tests:
1.  VA valid booking preconditions pass
2.  Federal EHR valid booking preconditions pass
3.  Community INITIAL_CONSULT + active HSRM auth + valid EPS slot passes
4.  Community missing HSRM authorization fails closed
5.  Community expired HSRM authorization fails closed
6.  Community service/scope mismatch fails closed
7.  Community provider/referral mismatch fails closed
8.  EPS stale/unavailable slot fails closed (preconditions)
9.  EPS slot no longer available at commit time fails closed
10. FOLLOW_UP intent through EPS fails closed
11. Veteran not confirmed fails closed
12. Wrong lifecycle state fails closed
13. Non-SCHEDULER actor fails closed
14. Double-booking: second slot reservation rejected
15. Same idempotency key + same material → existing BookingRecord returned
16. Same idempotency key + different material → IdempotencyConflictError
17. Failed commit writes neither reservation nor BOOKED_SIMULATED event
18. Successful commit creates exactly one reservation
19. Successful commit creates exactly one BookingRecord
20. Successful commit appends exactly one BOOKED_SIMULATED event
21. BookingRecord and BOOKED_SIMULATED event cannot diverge
22. HSRM authorization and EPS availability are independently checked
23. EPS availability is never treated as authorization
24. HSRM authorization is never treated as proof slot is still available
25. Full regression suite

R3 refinement tests:
26. PENDING_SCHEDULER_APPROVAL without explicit Scheduler actor fails
27. SYSTEM actor cannot commit
28. VETERAN actor cannot commit

R2 refinement tests:
29. Community BookingRecord contains both HSRM and EPS provenance
30. referral/authorization ID carried into EPS booking matches HSRM record
31. Mismatched authorization/referral context fails atomically
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from veteran_access_bridge.domain.models import (
    ActorRole,
    AppointmentIntent,
    BookingPreconditionResult,
    BookingRecord,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    EPSSlotRecord,
    HSRMAuthorizationRecord,
    HSRMAuthorizationStatus,
    OptionReadiness,
    OptionSelectionRecord,
    VeteranConfirmationRecord,
    VeteranResponse,
)
from veteran_access_bridge.services.booking import (
    BookingStore,
    SlotReservationStore,
    simulated_commit,
    validate_booking_preconditions,
)
from veteran_access_bridge.services.confirmation import ConfirmationStore, ConfirmationRequest
from veteran_access_bridge.services.events import (
    CaseEventStore,
    IdempotencyConflictError,
)
from veteran_access_bridge.services.selection import SelectionStore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 10, 25, 10, 0, 0, tzinfo=timezone.utc)
_T_FUTURE = datetime(2027, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
_T_PAST = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

_CASE = "DEMO-CARD-5000335-001"
_PATIENT = "5000335"
_CONSULT = "CONSULT-CARD-5000335-001"
_HANDOFF_ID = "handoff-test-001"
_SCHED_ID = "sched-demo-001"
_OPTION_VA = "OPT-VA-001"
_OPTION_FED = "OPT-FED-001"
_OPTION_CC = "OPT-CC-001"
_SLOT_VA = "SLOT-VA-001"
_SLOT_FED = "SLOT-FED-001"
_SLOT_CC = "EPS-SLOT-CC-001"
_PROVIDER_CC = "PROV-CC-001"
_IDEM_KEY = f"{_CASE}:book:{_OPTION_VA}"
_IDEM_KEY_CC = f"{_CASE}:book:{_OPTION_CC}"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _fresh_stores():
    return (
        CaseEventStore(),
        SelectionStore(),
        ConfirmationStore(),
        BookingStore(),
        SlotReservationStore(),
    )


def _selection(option_id: str, source: str = "VISTA_ISS") -> OptionSelectionRecord:
    return OptionSelectionRecord(
        selection_id="sel-abc123",
        case_id=_CASE,
        handoff_id=_HANDOFF_ID,
        option_id=option_id,
        readiness_at_selection=OptionReadiness.AVAILABLE,
        requires_verification=False,
        selected_at=_T0,
        selected_by_role=ActorRole.SCHEDULER,
        selected_by_id=_SCHED_ID,
        idempotency_key="sel-idem-001",
    )


def _confirmation_request(option_id: str = _OPTION_VA) -> ConfirmationRequest:
    import hashlib
    raw = f"confirmation:{_CASE}:sel-abc123:{option_id}"
    cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    return ConfirmationRequest(
        confirmation_request_id=cr_id,
        case_id=_CASE,
        option_id=option_id,
        selection_id="sel-abc123",
        requested_at=_T0,
        requested_by_role=ActorRole.SYSTEM,
    )


def _confirmation_record(
    response: VeteranResponse = VeteranResponse.CONFIRMED,
    option_id: str = _OPTION_VA,
    idem_key: str = "vet-conf-001",
) -> VeteranConfirmationRecord:
    raw = f"confirmation:{_CASE}:sel-abc123:{option_id}"
    cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    conf_id = "conf-" + hashlib.sha256(idem_key.encode()).hexdigest()[:16]
    return VeteranConfirmationRecord(
        confirmation_id=conf_id,
        confirmation_request_id=cr_id,
        case_id=_CASE,
        option_id=option_id,
        response=response,
        responded_at=_T0,
        actor_role=ActorRole.VETERAN,
        actor_id="veteran-5000335",
        idempotency_key=idem_key,
    )


def _hsrm_record(
    authorization_id: str = "HSRM-AUTH-CC-001",
    status: HSRMAuthorizationStatus = HSRMAuthorizationStatus.ACTIVE,
    service: str = "CARDIOLOGY",
    provider_id: str | None = _PROVIDER_CC,
    expiration: datetime = _T_FUTURE,
) -> HSRMAuthorizationRecord:
    return HSRMAuthorizationRecord(
        authorization_id=authorization_id,
        referral_id="HSRM-REF-CC-001",
        case_id=_CASE,
        option_id=_OPTION_CC,
        authorized_service=service,
        status=status,
        effective_date=_T_PAST,
        expiration_date=expiration,
        retrieved_at=_T0,
        provenance_ref="HSRM-PROV-CC-001",
        authorized_provider_id=provider_id,
    )


def _eps_slot(
    slot_id: str = _SLOT_CC,
    available: bool = True,
    initial_consult_eligible: bool = True,
    provider_id: str = _PROVIDER_CC,
) -> EPSSlotRecord:
    return EPSSlotRecord(
        slot_id=slot_id,
        option_id=_OPTION_CC,
        provider_id=provider_id,
        provider_name="Dr. Community Cardiology",
        appointment_start=_T_FUTURE,
        appointment_end=_T_FUTURE,
        available=available,
        initial_consult_eligible=initial_consult_eligible,
        retrieved_at=_T0,
        provenance_ref="EPS-PROV-SLOT-001",
    )


def _seed_to_pending_approval(
    es: CaseEventStore,
    ss: SelectionStore,
    cs: ConfirmationStore,
    option_id: str = _OPTION_VA,
    source: str = "VISTA_ISS",
) -> None:
    """Seed full lifecycle from REQUEST_RECEIVED to PENDING_SCHEDULER_APPROVAL."""
    path = [
        (CaseLifecycleState.REQUEST_RECEIVED,          CaseLifecycleState.READY_TO_SEARCH,           CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
        (CaseLifecycleState.READY_TO_SEARCH,            CaseLifecycleState.VA_OPTIONS_AVAILABLE,      CaseEventType.SEARCH_EXECUTED,         "e-va"),
        (CaseLifecycleState.VA_OPTIONS_AVAILABLE,       CaseLifecycleState.READY_FOR_HANDOFF,         CaseEventType.OPTIONS_ASSESSED,        "e-rfh"),
        (CaseLifecycleState.READY_FOR_HANDOFF,          CaseLifecycleState.HUMAN_REVIEW,              CaseEventType.HANDOFF_PREPARED,        "e-hr"),
        (CaseLifecycleState.HUMAN_REVIEW,               CaseLifecycleState.OPTION_SELECTED,           CaseEventType.OPTION_SELECTED,         "e-os"),
        (CaseLifecycleState.OPTION_SELECTED,            CaseLifecycleState.VERIFIED_BOOKABLE,         CaseEventType.VERIFICATION_PASSED,     "e-vb"),
        (CaseLifecycleState.VERIFIED_BOOKABLE,          CaseLifecycleState.PENDING_VETERAN_CONFIRMATION, CaseEventType.VETERAN_CONFIRMATION_REQUESTED, "e-pvc"),
        (CaseLifecycleState.PENDING_VETERAN_CONFIRMATION, CaseLifecycleState.PENDING_SCHEDULER_APPROVAL, CaseEventType.VETERAN_CONFIRMED,   "e-psa"),
    ]
    for from_s, to_s, etype, eid in path:
        es.append(CaseEvent(
            event_id=eid, case_id=_CASE, event_type=etype,
            from_state=from_s, to_state=to_s,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            occurred_at=_T0, idempotency_key=eid,
        ))
    ss.put(_selection(option_id=option_id, source=source))
    req = _confirmation_request(option_id=option_id)
    cs.put_request(req)
    conf = _confirmation_record(option_id=option_id)
    cs.put_confirmation(conf)


def _commit_va(
    es: CaseEventStore,
    ss: SelectionStore,
    cs: ConfirmationStore,
    bs: BookingStore,
    rs: SlotReservationStore,
    slot_id: str = _SLOT_VA,
    idem_key: str = _IDEM_KEY,
) -> BookingRecord:
    return simulated_commit(
        case_id=_CASE, option_id=_OPTION_VA, slot_id=slot_id,
        source_system="VISTA_ISS", intended_service="CARDIOLOGY",
        appointment_intent=AppointmentIntent.INITIAL_CONSULT,
        patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
        facility_name="VA Medical Center Test",
        actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
        idempotency_key=idem_key,
        event_store=es, confirmation_store=cs, selection_store=ss,
        booking_store=bs, reservation_store=rs,
        _as_of=_T0,
    )


def _commit_cc(
    es: CaseEventStore,
    ss: SelectionStore,
    cs: ConfirmationStore,
    bs: BookingStore,
    rs: SlotReservationStore,
    hsrm: HSRMAuthorizationRecord | None = None,
    eps: EPSSlotRecord | None = None,
    idem_key: str = _IDEM_KEY_CC,
) -> BookingRecord:
    return simulated_commit(
        case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
        source_system="EPS", intended_service="CARDIOLOGY",
        appointment_intent=AppointmentIntent.INITIAL_CONSULT,
        patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
        facility_name="Community Cardiology Clinic",
        actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
        idempotency_key=idem_key,
        event_store=es, confirmation_store=cs, selection_store=ss,
        booking_store=bs, reservation_store=rs,
        hsrm_record=hsrm if hsrm is not None else _hsrm_record(),
        eps_slot=eps if eps is not None else _eps_slot(),
        _as_of=_T0,
    )


# ===========================================================================
# Tests 1–2: VA / Federal EHR valid path
# ===========================================================================

class TestVAFederalPath:
    """Tests 1–2: VA and Federal EHR booking preconditions pass."""

    @pytest.mark.parametrize("source,slot,option", [
        ("VISTA_ISS", _SLOT_VA, _OPTION_VA),
        ("FEDERAL_EHR", _SLOT_FED, _OPTION_FED),
    ])
    def test_va_federal_preconditions_pass(self, source, slot, option):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=option, source=source)

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=option, slot_id=slot,
            source_system=source, intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=f"bk-{option}",
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
        )

        assert result.passed is True
        assert result.hsrm_checked is False
        assert result.eps_checked is False

    @pytest.mark.parametrize("source,slot,option", [
        ("VISTA_ISS", _SLOT_VA, _OPTION_VA),
        ("FEDERAL_EHR", _SLOT_FED, _OPTION_FED),
    ])
    def test_va_federal_commit_succeeds(self, source, slot, option):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=option, source=source)

        record = simulated_commit(
            case_id=_CASE, option_id=option, slot_id=slot,
            source_system=source, intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
            facility_name="VA Medical Center",
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=f"bk-{option}",
            event_store=es, confirmation_store=cs, selection_store=ss,
            booking_store=bs, reservation_store=rs, _as_of=_T0,
        )

        assert isinstance(record, BookingRecord)
        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.BOOKED_SIMULATED


# ===========================================================================
# Test 3: Community INITIAL_CONSULT full pass
# ===========================================================================

class TestCommunityFullPass:
    """Test 3: Community INITIAL_CONSULT with active HSRM auth + valid EPS slot."""

    def test_community_preconditions_pass(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=_hsrm_record(), eps_slot=_eps_slot(),
        )

        assert result.passed is True
        assert result.hsrm_checked is True
        assert result.eps_checked is True

    def test_community_commit_advances_lifecycle(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        _commit_cc(es, ss, cs, bs, rs)

        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.BOOKED_SIMULATED


# ===========================================================================
# Tests 4–7: HSRM authorization failures
# ===========================================================================

class TestHSRMFailures:
    """Tests 4–7: HSRM authorization checks are independent."""

    def test_missing_hsrm_fails(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=None, eps_slot=_eps_slot(),
        )

        assert result.passed is False
        assert any("authorization" in f.lower() for f in result.failures)

    def test_expired_hsrm_fails(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=_hsrm_record(status=HSRMAuthorizationStatus.EXPIRED,
                                      expiration=_T_PAST),
            eps_slot=_eps_slot(),
        )

        assert result.passed is False

    def test_scope_mismatch_fails(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=_hsrm_record(service="DERMATOLOGY"),
            eps_slot=_eps_slot(),
        )

        assert result.passed is False
        assert any("mismatch" in f.lower() or "scope" in f.lower() or
                   "covers" in f.lower() for f in result.failures)

    def test_provider_mismatch_fails(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=_hsrm_record(provider_id="PROV-OTHER"),
            eps_slot=_eps_slot(provider_id=_PROVIDER_CC),
        )

        assert result.passed is False


# ===========================================================================
# Tests 8–9: EPS slot failures
# ===========================================================================

class TestEPSFailures:
    """Tests 8–9: EPS slot checks are independent of HSRM."""

    def test_eps_unavailable_slot_fails_preconditions(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=_hsrm_record(),
            eps_slot=_eps_slot(available=False),
        )

        assert result.passed is False
        assert any("not available" in f for f in result.failures)

    def test_eps_slot_unavailable_at_commit_fails(self):
        """Test 9: EPS slot no longer available at commit time fails."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        with pytest.raises(ValueError, match="no longer available"):
            _commit_cc(es, ss, cs, bs, rs,
                       eps=_eps_slot(available=False))


# ===========================================================================
# Test 10: FOLLOW_UP intent fails closed
# ===========================================================================

class TestFollowUpIntent:
    """Test 10: FOLLOW_UP intent cannot proceed via EPS initial-consult path."""

    def test_follow_up_fails_preconditions(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.FOLLOW_UP,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=_hsrm_record(), eps_slot=_eps_slot(),
        )

        assert result.passed is False
        assert any("FOLLOW_UP" in f for f in result.failures)

    def test_follow_up_fails_commit(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        with pytest.raises(ValueError, match="FOLLOW_UP"):
            simulated_commit(
                case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
                source_system="EPS", intended_service="CARDIOLOGY",
                appointment_intent=AppointmentIntent.FOLLOW_UP,
                patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
                facility_name="Community Clinic",
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                idempotency_key=_IDEM_KEY_CC,
                event_store=es, confirmation_store=cs, selection_store=ss,
                booking_store=bs, reservation_store=rs,
                hsrm_record=_hsrm_record(), eps_slot=_eps_slot(),
                _as_of=_T0,
            )

    def test_follow_up_never_silently_converted(self):
        """FOLLOW_UP must not silently succeed as INITIAL_CONSULT."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        with pytest.raises(ValueError):
            simulated_commit(
                case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
                source_system="EPS", intended_service="CARDIOLOGY",
                appointment_intent=AppointmentIntent.FOLLOW_UP,
                patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
                facility_name="Community Clinic",
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                idempotency_key=_IDEM_KEY_CC,
                event_store=es, confirmation_store=cs, selection_store=ss,
                booking_store=bs, reservation_store=rs,
                hsrm_record=_hsrm_record(), eps_slot=_eps_slot(),
                _as_of=_T0,
            )
        # No BOOKED_SIMULATED event must have been appended.
        event_types = [e.event_type for e in es.get_events(_CASE)]
        assert CaseEventType.BOOKED_SIMULATED not in event_types


# ===========================================================================
# Test 11: Veteran not confirmed fails
# ===========================================================================

class TestVeteranNotConfirmed:
    """Test 11: Booking fails if Veteran did not confirm."""

    def test_veteran_not_confirmed_fails_preconditions(self):
        es, ss, cs, bs, rs = _fresh_stores()
        # Seed lifecycle but store DECLINED response.
        _seed_to_pending_approval(es, ss, cs)
        # Override the confirmation with DECLINED.
        declined = _confirmation_record(response=VeteranResponse.DECLINED)
        cs2 = ConfirmationStore()
        cs2.put_request(_confirmation_request())
        cs2.put_confirmation(declined)

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_VA, slot_id=_SLOT_VA,
            source_system="VISTA_ISS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY,
            event_store=es, confirmation_store=cs2, selection_store=ss, booking_store=bs,
        )

        assert result.passed is False

    def test_no_veteran_confirmation_record_fails(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)
        empty_cs = ConfirmationStore()

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_VA, slot_id=_SLOT_VA,
            source_system="VISTA_ISS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY,
            event_store=es, confirmation_store=empty_cs, selection_store=ss,
            booking_store=bs,
        )

        assert result.passed is False


# ===========================================================================
# Test 12: Wrong lifecycle state fails
# ===========================================================================

class TestWrongLifecycleState:
    """Test 12: Wrong lifecycle state fails closed."""

    def test_verified_bookable_state_fails_commit(self):
        es, ss, cs, bs, rs = _fresh_stores()
        # Seed only to VERIFIED_BOOKABLE, not PENDING_SCHEDULER_APPROVAL.
        path = [
            (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH, CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
            (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseEventType.SEARCH_EXECUTED, "e-va"),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF, CaseEventType.OPTIONS_ASSESSED, "e-rfh"),
            (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW, CaseEventType.HANDOFF_PREPARED, "e-hr"),
            (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED, CaseEventType.OPTION_SELECTED, "e-os"),
            (CaseLifecycleState.OPTION_SELECTED, CaseLifecycleState.VERIFIED_BOOKABLE, CaseEventType.VERIFICATION_PASSED, "e-vb"),
        ]
        for from_s, to_s, etype, eid in path:
            es.append(CaseEvent(
                event_id=eid, case_id=_CASE, event_type=etype,
                from_state=from_s, to_state=to_s,
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                occurred_at=_T0, idempotency_key=eid,
            ))
        ss.put(_selection(option_id=_OPTION_VA))
        cs.put_request(_confirmation_request())
        cs.put_confirmation(_confirmation_record())

        with pytest.raises(ValueError, match="simulated_commit requires"):
            _commit_va(es, ss, cs, bs, rs)

    def test_wrong_state_no_event(self):
        es, ss, cs, bs, rs = _fresh_stores()
        # No lifecycle events at all.
        with pytest.raises(ValueError):
            _commit_va(es, ss, cs, bs, rs)


# ===========================================================================
# Tests 13, 26–28: Actor role guards
# ===========================================================================

class TestActorRoleGuard:
    """Tests 13, 26, 27, 28: Explicit SCHEDULER required."""

    @pytest.mark.parametrize("bad_role", [ActorRole.SYSTEM, ActorRole.VETERAN])
    def test_non_scheduler_fails_commit(self, bad_role):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)

        with pytest.raises(ValueError, match="Only ActorRole.SCHEDULER"):
            simulated_commit(
                case_id=_CASE, option_id=_OPTION_VA, slot_id=_SLOT_VA,
                source_system="VISTA_ISS", intended_service="CARDIOLOGY",
                appointment_intent=AppointmentIntent.INITIAL_CONSULT,
                patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
                facility_name="VA",
                actor_role=bad_role, actor_id="bad-actor",
                idempotency_key=_IDEM_KEY,
                event_store=es, confirmation_store=cs, selection_store=ss,
                booking_store=bs, reservation_store=rs, _as_of=_T0,
            )

    @pytest.mark.parametrize("bad_role", [ActorRole.SYSTEM, ActorRole.VETERAN])
    def test_non_scheduler_no_event(self, bad_role):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)
        count_before = len(es.get_events(_CASE))

        with pytest.raises(ValueError):
            simulated_commit(
                case_id=_CASE, option_id=_OPTION_VA, slot_id=_SLOT_VA,
                source_system="VISTA_ISS", intended_service="CARDIOLOGY",
                appointment_intent=AppointmentIntent.INITIAL_CONSULT,
                patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
                facility_name="VA",
                actor_role=bad_role, actor_id="bad-actor",
                idempotency_key=_IDEM_KEY,
                event_store=es, confirmation_store=cs, selection_store=ss,
                booking_store=bs, reservation_store=rs, _as_of=_T0,
            )

        assert len(es.get_events(_CASE)) == count_before

    def test_pending_approval_state_alone_insufficient(self):
        """Being in PENDING_SCHEDULER_APPROVAL does not constitute approval."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)

        with pytest.raises(ValueError, match="Only ActorRole.SCHEDULER"):
            simulated_commit(
                case_id=_CASE, option_id=_OPTION_VA, slot_id=_SLOT_VA,
                source_system="VISTA_ISS", intended_service="CARDIOLOGY",
                appointment_intent=AppointmentIntent.INITIAL_CONSULT,
                patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
                facility_name="VA",
                actor_role=ActorRole.SYSTEM,  # SYSTEM cannot commit
                actor_id="system",
                idempotency_key=_IDEM_KEY,
                event_store=es, confirmation_store=cs, selection_store=ss,
                booking_store=bs, reservation_store=rs, _as_of=_T0,
            )


# ===========================================================================
# Test 14: Double-booking protection
# ===========================================================================

class TestDoubleBooking:
    """Test 14: Second reservation for the same slot is rejected."""

    def test_second_reservation_rejected(self):
        # Use TWO separate cases sharing a slot — the slot itself is the
        # double-booking protection boundary.  We test this by asserting
        # the reservation store rejects a second attempt on the same slot_id.
        rs = SlotReservationStore()
        from veteran_access_bridge.domain.models import SlotReservation
        rsv1 = SlotReservation(
            reservation_id="rsv-001", slot_id=_SLOT_VA,
            case_id=_CASE, option_id=_OPTION_VA,
            booking_id="bk-001", reserved_at=_T0,
        )
        rs.reserve(rsv1)
        rsv2 = SlotReservation(
            reservation_id="rsv-002", slot_id=_SLOT_VA,
            case_id="OTHER-CASE", option_id=_OPTION_VA,
            booking_id="bk-002", reserved_at=_T0,
        )
        result = rs.reserve(rsv2)
        assert result is False

    def test_second_reservation_no_extra_event(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)
        _commit_va(es, ss, cs, bs, rs, idem_key="bk-001")
        count_after_first = len(es.get_events(_CASE))

        with pytest.raises(ValueError):
            simulated_commit(
                case_id=_CASE, option_id=_OPTION_VA, slot_id=_SLOT_VA,
                source_system="VISTA_ISS", intended_service="CARDIOLOGY",
                appointment_intent=AppointmentIntent.INITIAL_CONSULT,
                patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
                facility_name="VA",
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                idempotency_key="bk-002",
                event_store=es, confirmation_store=cs, selection_store=ss,
                booking_store=bs, reservation_store=rs, _as_of=_T0,
            )

        assert len(es.get_events(_CASE)) == count_after_first


# ===========================================================================
# Tests 15–16: Idempotency
# ===========================================================================

class TestIdempotency:
    """Tests 15–16: Booking idempotency."""

    def test_same_key_same_material_returns_existing(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)

        r1 = _commit_va(es, ss, cs, bs, rs)
        r2 = _commit_va(es, ss, cs, bs, rs)

        assert r1 is r2

    def test_same_key_same_material_no_duplicate_event(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)

        _commit_va(es, ss, cs, bs, rs)
        count_after_first = len(es.get_events(_CASE))
        _commit_va(es, ss, cs, bs, rs)

        assert len(es.get_events(_CASE)) == count_after_first

    def test_same_key_different_slot_raises(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)
        _commit_va(es, ss, cs, bs, rs, idem_key=_IDEM_KEY)

        with pytest.raises(IdempotencyConflictError):
            simulated_commit(
                case_id=_CASE, option_id=_OPTION_VA, slot_id="SLOT-DIFFERENT",
                source_system="VISTA_ISS", intended_service="CARDIOLOGY",
                appointment_intent=AppointmentIntent.INITIAL_CONSULT,
                patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
                facility_name="VA",
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                idempotency_key=_IDEM_KEY,
                event_store=es, confirmation_store=cs, selection_store=ss,
                booking_store=bs, reservation_store=rs, _as_of=_T0,
            )


# ===========================================================================
# Test 17: Failed commit is fully atomic
# ===========================================================================

class TestAtomicRollback:
    """Test 17: Failed commit writes neither reservation nor BOOKED_SIMULATED."""

    def test_follow_up_failure_no_reservation(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        with pytest.raises(ValueError):
            simulated_commit(
                case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
                source_system="EPS", intended_service="CARDIOLOGY",
                appointment_intent=AppointmentIntent.FOLLOW_UP,
                patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
                facility_name="Community Clinic",
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                idempotency_key=_IDEM_KEY_CC,
                event_store=es, confirmation_store=cs, selection_store=ss,
                booking_store=bs, reservation_store=rs,
                hsrm_record=_hsrm_record(), eps_slot=_eps_slot(),
                _as_of=_T0,
            )

        assert not rs.is_reserved(_SLOT_CC)
        assert len(bs) == 0
        event_types = [e.event_type for e in es.get_events(_CASE)]
        assert CaseEventType.BOOKED_SIMULATED not in event_types

    def test_hsrm_failure_no_reservation(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        with pytest.raises(ValueError, match="[Aa]uthorization|HSRM"):
            simulated_commit(
                case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
                source_system="EPS", intended_service="CARDIOLOGY",
                appointment_intent=AppointmentIntent.INITIAL_CONSULT,
                patient_id=_PATIENT, consult_id=_CONSULT, handoff_id=_HANDOFF_ID,
                facility_name="Community Clinic",
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                idempotency_key=_IDEM_KEY_CC,
                event_store=es, confirmation_store=cs, selection_store=ss,
                booking_store=bs, reservation_store=rs,
                hsrm_record=None,
                eps_slot=_eps_slot(),
                _as_of=_T0,
            )

        assert not rs.is_reserved(_SLOT_CC)
        assert len(bs) == 0


# ===========================================================================
# Tests 18–21: Atomicity of successful commit
# ===========================================================================

class TestAtomicSuccessfulCommit:
    """Tests 18–21: Successful commit creates exactly one of each artifact."""

    def test_exactly_one_reservation(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)
        _commit_va(es, ss, cs, bs, rs)
        assert len(rs) == 1

    def test_exactly_one_booking_record(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)
        _commit_va(es, ss, cs, bs, rs)
        assert len(bs) == 1

    def test_exactly_one_booked_simulated_event(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)
        _commit_va(es, ss, cs, bs, rs)
        booked_events = [
            e for e in es.get_events(_CASE)
            if e.event_type == CaseEventType.BOOKED_SIMULATED
        ]
        assert len(booked_events) == 1

    def test_booking_record_and_event_carry_same_booking_id(self):
        """BookingRecord and BOOKED_SIMULATED event cannot diverge."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)
        record = _commit_va(es, ss, cs, bs, rs)

        booked_events = [
            e for e in es.get_events(_CASE)
            if e.event_type == CaseEventType.BOOKED_SIMULATED
        ]
        assert booked_events[0].payload["booking_id"] == record.booking_id


# ===========================================================================
# Tests 22–24: Domain separation
# ===========================================================================

class TestDomainSeparation:
    """Tests 22–24: HSRM and EPS are independently checked."""

    def test_eps_failure_with_valid_hsrm_fails(self):
        """Test 22/24: Valid HSRM + unavailable EPS slot still fails."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=_hsrm_record(),          # valid HSRM
            eps_slot=_eps_slot(available=False),  # unavailable EPS
        )

        assert result.passed is False
        assert result.hsrm_checked is True
        assert result.eps_checked is True

    def test_hsrm_failure_with_valid_eps_fails(self):
        """Test 22/23: Unavailable HSRM + valid EPS slot still fails."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=_hsrm_record(status=HSRMAuthorizationStatus.EXPIRED,
                                      expiration=_T_PAST),
            eps_slot=_eps_slot(),  # valid EPS
        )

        assert result.passed is False

    def test_eps_availability_not_treated_as_authorization(self):
        """Test 23: An available EPS slot without HSRM auth must fail."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        result = validate_booking_preconditions(
            case_id=_CASE, option_id=_OPTION_CC, slot_id=_SLOT_CC,
            source_system="EPS", intended_service="CARDIOLOGY",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            idempotency_key=_IDEM_KEY_CC,
            event_store=es, confirmation_store=cs, selection_store=ss, booking_store=bs,
            hsrm_record=None,        # no HSRM
            eps_slot=_eps_slot(),    # EPS slot is available
        )

        # Available EPS slot alone must NOT make this pass.
        assert result.passed is False
        assert any("authorization" in f.lower() for f in result.failures)


# ===========================================================================
# Tests 29–31: R2 EPS/HSRM provenance in BookingRecord
# ===========================================================================

class TestR2EPSHSRMProvenance:
    """Tests 29–31: Community BookingRecord carries full HSRM + EPS provenance."""

    def test_community_booking_carries_hsrm_provenance(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")
        record = _commit_cc(es, ss, cs, bs, rs)

        assert record.authorization_id == "HSRM-AUTH-CC-001"
        assert record.referral_id == "HSRM-REF-CC-001"
        assert record.hsrm_provenance_ref == "HSRM-PROV-CC-001"

    def test_community_booking_carries_eps_provenance(self):
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")
        record = _commit_cc(es, ss, cs, bs, rs)

        assert record.eps_provenance_ref == "EPS-PROV-SLOT-001"
        assert record.provider_id == _PROVIDER_CC

    def test_referral_id_matches_validated_hsrm_record(self):
        """Referral ID carried into booking must match the validated HSRM record."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")
        hsrm = _hsrm_record(authorization_id="HSRM-AUTH-CC-001")
        record = _commit_cc(es, ss, cs, bs, rs, hsrm=hsrm)

        assert record.referral_id == hsrm.referral_id
        assert record.authorization_id == hsrm.authorization_id

    def test_mismatched_authorization_context_fails_atomically(self):
        """Test 31: HSRM/EPS provider mismatch fails; no reservation, no event."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs, option_id=_OPTION_CC, source="EPS")

        with pytest.raises(ValueError, match="[Pp]rovider|[Mm]ismatch"):
            _commit_cc(
                es, ss, cs, bs, rs,
                hsrm=_hsrm_record(provider_id="PROV-WRONG"),
                eps=_eps_slot(provider_id=_PROVIDER_CC),
            )

        assert not rs.is_reserved(_SLOT_CC)
        assert len(bs) == 0
        event_types = [e.event_type for e in es.get_events(_CASE)]
        assert CaseEventType.BOOKED_SIMULATED not in event_types

    def test_va_booking_has_no_hsrm_eps_fields(self):
        """VA bookings have None for authorization/EPS provenance fields."""
        es, ss, cs, bs, rs = _fresh_stores()
        _seed_to_pending_approval(es, ss, cs)
        record = _commit_va(es, ss, cs, bs, rs)

        assert record.authorization_id is None
        assert record.referral_id is None
        assert record.hsrm_provenance_ref is None
        assert record.eps_provenance_ref is None


# ===========================================================================
# BookingStore / SlotReservationStore unit tests
# ===========================================================================

class TestBookingStore:
    def test_put_and_get(self):
        bs = BookingStore()
        r = BookingRecord(
            booking_id="bk-001", case_id=_CASE, option_id=_OPTION_VA,
            slot_id=_SLOT_VA, patient_id=_PATIENT, consult_id=_CONSULT,
            handoff_id=_HANDOFF_ID, facility_name="VA",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            appointment_start=_T0, appointment_end=_T0,
            source_system="VISTA_ISS", booked_at=_T0,
            booked_by_role=ActorRole.SCHEDULER, booked_by_id=_SCHED_ID,
            idempotency_key="k1",
        )
        bs.put(r)
        assert bs.get("bk-001") is r
        assert bs.get_by_key("k1") is r

    def test_second_put_is_no_op(self):
        bs = BookingStore()
        r = BookingRecord(
            booking_id="bk-001", case_id=_CASE, option_id=_OPTION_VA,
            slot_id=_SLOT_VA, patient_id=_PATIENT, consult_id=_CONSULT,
            handoff_id=_HANDOFF_ID, facility_name="VA",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            appointment_start=_T0, appointment_end=_T0,
            source_system="VISTA_ISS", booked_at=_T0,
            booked_by_role=ActorRole.SCHEDULER, booked_by_id=_SCHED_ID,
            idempotency_key="k1",
        )
        bs.put(r)
        bs.put(r)
        assert len(bs) == 1


class TestSlotReservationStore:
    def test_reserve_and_is_reserved(self):
        from veteran_access_bridge.domain.models import SlotReservation
        rs = SlotReservationStore()
        rsv = SlotReservation(
            reservation_id="rsv-001", slot_id=_SLOT_VA, case_id=_CASE,
            option_id=_OPTION_VA, booking_id="bk-001", reserved_at=_T0,
        )
        result = rs.reserve(rsv)
        assert result is True
        assert rs.is_reserved(_SLOT_VA)

    def test_second_reserve_fails(self):
        from veteran_access_bridge.domain.models import SlotReservation
        rs = SlotReservationStore()
        rsv = SlotReservation(
            reservation_id="rsv-001", slot_id=_SLOT_VA, case_id=_CASE,
            option_id=_OPTION_VA, booking_id="bk-001", reserved_at=_T0,
        )
        rs.reserve(rsv)
        result = rs.reserve(rsv)
        assert result is False

    def test_release(self):
        from veteran_access_bridge.domain.models import SlotReservation
        rs = SlotReservationStore()
        rsv = SlotReservation(
            reservation_id="rsv-001", slot_id=_SLOT_VA, case_id=_CASE,
            option_id=_OPTION_VA, booking_id="bk-001", reserved_at=_T0,
        )
        rs.reserve(rsv)
        rs.release(_SLOT_VA)
        assert not rs.is_reserved(_SLOT_VA)
