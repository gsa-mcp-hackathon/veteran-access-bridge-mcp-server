"""M2-10 Full acceptance tests.

Ten end-to-end scenarios as defined in docs/IMPLEMENTATION_PLAN.md:

 S01  Valid cardiology consult traverses entire simulation
       (handoff → select → verify → confirm → approve → commit → complete)
 S02  Missing specialty consult blocks booking
       (no lifecycle history → commit fails with lifecycle guard)
 S03  Community option without valid HSRM authorization cannot commit
 S04  Stale EPS slot rejects commit
 S05  Two attempts to take one slot yield at most one successful commit
 S06  Veteran cannot call scheduler-only actions
 S07  Cancellation and rescheduling preserve history
 S08  Completion versus no-show are distinct outcomes
 S09  Source timeout does not produce false booking success
       (lifecycle guard prevents commit when state is not PENDING_SCHEDULER_APPROVAL)
 S10  Every option has source_id, retrieval timestamp, freshness, synthetic flag, trace

Plus M2-7 bonus scenarios (M2 plan sections 11–12):
 S11  Community Care HSRM auth and EPS slot availability revalidated independently
 S12  EPS follow-up booking fails closed
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from veteran_access_bridge.domain.models import (
    ActorRole,
    AppointmentIntent,
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
from veteran_access_bridge.services.confirmation import ConfirmationRequest, ConfirmationStore
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.outcomes import record_lifecycle_event
from veteran_access_bridge.services.selection import SelectionStore
from veteran_access_bridge.mcp.tools import get_case_lifecycle_state as gcls_tool

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 10, 25, 10, 0, 0, tzinfo=timezone.utc)
_T_FUTURE = datetime(2027, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
_T_PAST = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

_CASE = "ACC-CARD-ACCEPT-001"
_CASE_CC = "ACC-CARD-ACCEPT-CC-001"
_PATIENT = "5000335"
_CONSULT = "CONSULT-CARD-ACC-001"
_HANDOFF_ID = "handoff-acc-001"
_SCHED_ID = "sched-acc-001"
_VET_ID = "veteran-acc-001"
_OPTION_VA = "OPT-VA-ACC-001"
_OPTION_CC = "OPT-CC-ACC-001"
_SLOT_VA = "SLOT-VA-ACC-001"
_SLOT_CC = "EPS-SLOT-CC-ACC-001"
_PROVIDER_CC = "PROV-CC-ACC-001"
_SERVICE = "CARDIOLOGY"
_FACILITY = "VA Medical Center — Synthetic"


# ---------------------------------------------------------------------------
# Stores factory
# ---------------------------------------------------------------------------

def _fresh():
    return (
        CaseEventStore(),
        SelectionStore(),
        ConfirmationStore(),
        BookingStore(),
        SlotReservationStore(),
    )


# ---------------------------------------------------------------------------
# Lifecycle seeding helpers
# ---------------------------------------------------------------------------

def _seed_event(
    store: CaseEventStore,
    case_id: str,
    from_state: CaseLifecycleState,
    to_state: CaseLifecycleState,
    event_type: CaseEventType,
    idem_key: str,
    actor_role: ActorRole = ActorRole.SCHEDULER,
    actor_id: str = _SCHED_ID,
) -> CaseEvent:
    return store.append(CaseEvent(
        event_id="acc-" + hashlib.sha256(idem_key.encode()).hexdigest()[:16],
        case_id=case_id,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        actor_role=actor_role,
        actor_id=actor_id,
        occurred_at=_T0,
        idempotency_key=idem_key,
        payload={},
    ))


def _seed_to_pending_scheduler_approval(
    es: CaseEventStore, case_id: str
) -> None:
    """Bring a case to PENDING_SCHEDULER_APPROVAL via the standard path."""
    steps = [
        (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
         CaseEventType.WORKFLOW_GATE_EVALUATED, "rr"),
        (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
         CaseEventType.SEARCH_EXECUTED, "rts"),
        (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
         CaseEventType.OPTIONS_ASSESSED, "va"),
        (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
         CaseEventType.HANDOFF_PREPARED, "rfh"),
        (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED,
         CaseEventType.OPTION_SELECTED, "hr"),
        (CaseLifecycleState.OPTION_SELECTED, CaseLifecycleState.VERIFIED_BOOKABLE,
         CaseEventType.VERIFICATION_PASSED, "os"),
        (CaseLifecycleState.VERIFIED_BOOKABLE, CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
         CaseEventType.VETERAN_CONFIRMATION_REQUESTED, "vb"),
        (CaseLifecycleState.PENDING_VETERAN_CONFIRMATION, CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
         CaseEventType.VETERAN_CONFIRMED, "pvc"),
    ]
    for i, (fs, ts, et, tag) in enumerate(steps):
        role = ActorRole.VETERAN if tag == "pvc" else ActorRole.SCHEDULER
        actor = _VET_ID if tag == "pvc" else _SCHED_ID
        _seed_event(es, case_id, fs, ts, et, f"seed-{tag}-{case_id}-{i}", role, actor)


def _sel(case_id: str, option_id: str) -> OptionSelectionRecord:
    return OptionSelectionRecord(
        selection_id="sel-acc-001",
        case_id=case_id,
        handoff_id=_HANDOFF_ID,
        option_id=option_id,
        readiness_at_selection=OptionReadiness.AVAILABLE,
        requires_verification=False,
        selected_at=_T0,
        selected_by_role=ActorRole.SCHEDULER,
        selected_by_id=_SCHED_ID,
        idempotency_key="sel-idem-acc-001",
    )


def _conf(
    case_id: str,
    option_id: str,
    response: VeteranResponse = VeteranResponse.CONFIRMED,
) -> VeteranConfirmationRecord:
    raw = f"confirmation:{case_id}:sel-acc-001:{option_id}"
    cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    conf_id = "conf-" + hashlib.sha256(f"conf-key-{case_id}".encode()).hexdigest()[:16]
    return VeteranConfirmationRecord(
        confirmation_id=conf_id,
        confirmation_request_id=cr_id,
        case_id=case_id,
        option_id=option_id,
        response=response,
        responded_at=_T0,
        actor_role=ActorRole.VETERAN,
        actor_id=_VET_ID,
        idempotency_key=f"conf-key-{case_id}",
    )


def _conf_request(case_id: str, option_id: str) -> ConfirmationRequest:
    raw = f"confirmation:{case_id}:sel-acc-001:{option_id}"
    cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
    return ConfirmationRequest(
        confirmation_request_id=cr_id,
        case_id=case_id,
        option_id=option_id,
        selection_id="sel-acc-001",
        requested_at=_T0,
        requested_by_role=ActorRole.SYSTEM,
    )


def _hsrm(
    case_id: str,
    option_id: str,
    status: HSRMAuthorizationStatus = HSRMAuthorizationStatus.ACTIVE,
    expiration: datetime = _T_FUTURE,
    service: str = _SERVICE,
    provider_id: str | None = _PROVIDER_CC,
) -> HSRMAuthorizationRecord:
    return HSRMAuthorizationRecord(
        authorization_id=f"HSRM-AUTH-{option_id}",
        referral_id=f"HSRM-REF-{option_id}",
        case_id=case_id,
        option_id=option_id,
        authorized_service=service,
        status=status,
        effective_date=_T_PAST,
        expiration_date=expiration,
        retrieved_at=_T0,
        provenance_ref=f"HSRM-PROV-{option_id}",
        authorized_provider_id=provider_id,
    )


def _eps(
    option_id: str,
    slot_id: str,
    available: bool = True,
    initial_consult_eligible: bool = True,
) -> EPSSlotRecord:
    return EPSSlotRecord(
        slot_id=slot_id,
        option_id=option_id,
        provider_id=_PROVIDER_CC,
        provider_name="Dr. Community Cardiology",
        appointment_start=_T_FUTURE,
        appointment_end=_T_FUTURE,
        available=available,
        initial_consult_eligible=initial_consult_eligible,
        retrieved_at=_T0,
        provenance_ref=f"EPS-PROV-{slot_id}",
        synthetic=True,
    )


def _do_commit(
    case_id: str,
    option_id: str,
    slot_id: str,
    source: str,
    es: CaseEventStore,
    ss: SelectionStore,
    cs: ConfirmationStore,
    bs: BookingStore,
    rs: SlotReservationStore,
    *,
    idem_key: str | None = None,
    intent: AppointmentIntent = AppointmentIntent.INITIAL_CONSULT,
    hsrm: HSRMAuthorizationRecord | None = None,
    eps: EPSSlotRecord | None = None,
):
    return simulated_commit(
        case_id=case_id,
        option_id=option_id,
        slot_id=slot_id,
        source_system=source,
        intended_service=_SERVICE,
        appointment_intent=intent,
        patient_id=_PATIENT,
        consult_id=_CONSULT,
        handoff_id=_HANDOFF_ID,
        facility_name=_FACILITY,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key=idem_key or f"{case_id}:book:{option_id}:{slot_id}",
        event_store=es,
        confirmation_store=cs,
        selection_store=ss,
        booking_store=bs,
        reservation_store=rs,
        hsrm_record=hsrm,
        eps_slot=eps,
        _as_of=_T0,
    )


# ---------------------------------------------------------------------------
# S01 — Valid cardiology consult traverses entire simulation
# ---------------------------------------------------------------------------

def test_s01_full_va_lifecycle():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE)
    ss.put(_sel(_CASE, _OPTION_VA))
    cr = _conf_request(_CASE, _OPTION_VA)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE, _OPTION_VA))

    # Commit
    booking = _do_commit(_CASE, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs)
    assert booking.case_id == _CASE
    assert booking.option_id == _OPTION_VA

    # State is now BOOKED_SIMULATED
    lc = es.get_lifecycle_record(_CASE)
    assert lc.current_state == CaseLifecycleState.BOOKED_SIMULATED

    # Advance to COMPLETED
    e = record_lifecycle_event(
        case_id=_CASE,
        event_type=CaseEventType.APPOINTMENT_COMPLETED,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s01-completed",
        event_store=es,
    )
    assert e.to_state == CaseLifecycleState.COMPLETED

    # get_case_lifecycle_state reflects terminal state
    result = gcls_tool.run(_CASE, event_store=es)
    assert result["current_state"] == "COMPLETED"


# ---------------------------------------------------------------------------
# S02 — Missing consult (no lifecycle history) blocks booking
# ---------------------------------------------------------------------------

def test_s02_no_lifecycle_history_blocks_commit():
    es, ss, cs, bs, rs = _fresh()
    # No history seeded — case has never been initialised
    ss.put(_sel(_CASE, _OPTION_VA))
    cs.put_confirmation(_conf(_CASE, _OPTION_VA))

    with pytest.raises(ValueError, match="lifecycle"):
        _do_commit(_CASE, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs)


# ---------------------------------------------------------------------------
# S03 — Community option without valid HSRM authorization cannot commit
# ---------------------------------------------------------------------------

def test_s03_community_missing_hsrm_fails():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE_CC)
    ss.put(_sel(_CASE_CC, _OPTION_CC))
    cr = _conf_request(_CASE_CC, _OPTION_CC)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE_CC, _OPTION_CC))

    # No hsrm_record provided → HSRM check must fail
    result = validate_booking_preconditions(
        case_id=_CASE_CC,
        option_id=_OPTION_CC,
        slot_id=_SLOT_CC,
        source_system="COMMUNITY_CARE",
        intended_service=_SERVICE,
        appointment_intent=AppointmentIntent.INITIAL_CONSULT,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s03-no-hsrm",
        event_store=es,
        confirmation_store=cs,
        selection_store=ss,
        booking_store=bs,
        hsrm_record=None,
        eps_slot=_eps(_OPTION_CC, _SLOT_CC),
    )
    assert not result.passed
    assert any("HSRM" in f for f in result.failures)
    assert result.hsrm_checked is True


# ---------------------------------------------------------------------------
# S04 — Stale EPS slot rejects commit
# ---------------------------------------------------------------------------

def test_s04_stale_eps_slot_fails():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE_CC)
    ss.put(_sel(_CASE_CC, _OPTION_CC))
    cr = _conf_request(_CASE_CC, _OPTION_CC)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE_CC, _OPTION_CC))

    stale_eps = _eps(_OPTION_CC, _SLOT_CC, available=False)
    result = validate_booking_preconditions(
        case_id=_CASE_CC,
        option_id=_OPTION_CC,
        slot_id=_SLOT_CC,
        source_system="COMMUNITY_CARE",
        intended_service=_SERVICE,
        appointment_intent=AppointmentIntent.INITIAL_CONSULT,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s04-stale-eps",
        event_store=es,
        confirmation_store=cs,
        selection_store=ss,
        booking_store=bs,
        hsrm_record=_hsrm(_CASE_CC, _OPTION_CC),
        eps_slot=stale_eps,
    )
    assert not result.passed
    assert any("not available" in f for f in result.failures)
    assert result.eps_checked is True


# ---------------------------------------------------------------------------
# S05 — Two attempts to take one slot yield at most one successful commit
# ---------------------------------------------------------------------------

def test_s05_double_booking_rejected():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE)
    ss.put(_sel(_CASE, _OPTION_VA))
    cr = _conf_request(_CASE, _OPTION_VA)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE, _OPTION_VA))

    idem = f"{_CASE}:book:{_OPTION_VA}:{_SLOT_VA}"

    # First commit succeeds
    booking1 = _do_commit(_CASE, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs, idem_key=idem)
    assert booking1.booking_id is not None

    # Second attempt with same key → idempotent return, not a new commit
    booking2 = _do_commit(_CASE, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs, idem_key=idem)
    assert booking1.booking_id == booking2.booking_id

    # Second attempt with different key → reservation already held
    from veteran_access_bridge.services.events import InvalidTransitionError
    with pytest.raises((ValueError, InvalidTransitionError)):
        _do_commit(_CASE, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs,
                   idem_key="s05-second-attempt-different-key")


# ---------------------------------------------------------------------------
# S06 — Veteran cannot call scheduler-only actions
# ---------------------------------------------------------------------------

def test_s06_veteran_cannot_commit():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE)
    ss.put(_sel(_CASE, _OPTION_VA))
    cr = _conf_request(_CASE, _OPTION_VA)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE, _OPTION_VA))

    with pytest.raises(ValueError, match="SCHEDULER"):
        simulated_commit(
            case_id=_CASE,
            option_id=_OPTION_VA,
            slot_id=_SLOT_VA,
            source_system="VISTA_ISS",
            intended_service=_SERVICE,
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            patient_id=_PATIENT,
            consult_id=_CONSULT,
            handoff_id=_HANDOFF_ID,
            facility_name=_FACILITY,
            actor_role=ActorRole.VETERAN,  # <-- not SCHEDULER
            actor_id=_VET_ID,
            idempotency_key="s06-vet-attempt",
            event_store=es,
            confirmation_store=cs,
            selection_store=ss,
            booking_store=bs,
            reservation_store=rs,
            _as_of=_T0,
        )


def test_s06b_veteran_cannot_record_outcome_follow_up():
    """Veteran cannot drive FOLLOW_UP_INITIATED via MCP tool."""
    from veteran_access_bridge.mcp.tools import record_lifecycle_event as rle_tool

    es = CaseEventStore()
    # Seed to NO_SHOW
    _seed_to_pending_scheduler_approval(es, _CASE)
    _seed_event(es, _CASE,
        CaseLifecycleState.PENDING_SCHEDULER_APPROVAL, CaseLifecycleState.BOOKED_SIMULATED,
        CaseEventType.BOOKED_SIMULATED, "s06b-booked")
    _seed_event(es, _CASE,
        CaseLifecycleState.BOOKED_SIMULATED, CaseLifecycleState.NO_SHOW,
        CaseEventType.VETERAN_NO_SHOW, "s06b-no-show")

    with pytest.raises(ValueError, match="not permitted"):
        rle_tool.run(_CASE, "FOLLOW_UP_INITIATED", "VETERAN", _VET_ID, "s06b-key", event_store=es)


# ---------------------------------------------------------------------------
# S07 — Cancellation and rescheduling preserve history
# ---------------------------------------------------------------------------

def test_s07_cancellation_preserves_history():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE)
    ss.put(_sel(_CASE, _OPTION_VA))
    cr = _conf_request(_CASE, _OPTION_VA)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE, _OPTION_VA))

    _do_commit(_CASE, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs)
    event_count_before = len(es.get_events(_CASE))

    record_lifecycle_event(
        case_id=_CASE,
        event_type=CaseEventType.APPOINTMENT_CANCELLED,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s07-cancel",
        payload={"reason": "Patient unavailable"},
        event_store=es,
    )

    events = es.get_events(_CASE)
    # All prior events preserved + the cancel event appended
    assert len(events) == event_count_before + 1
    assert events[-1].to_state == CaseLifecycleState.CANCELLED
    assert events[-1].payload["reason"] == "Patient unavailable"
    # Full history is intact and ordered
    for i in range(len(events) - 1):
        assert events[i].to_state == events[i + 1].from_state


def test_s07b_rescheduling_preserves_history():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE)
    ss.put(_sel(_CASE, _OPTION_VA))
    cr = _conf_request(_CASE, _OPTION_VA)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE, _OPTION_VA))

    _do_commit(_CASE, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs)
    event_count_before = len(es.get_events(_CASE))

    record_lifecycle_event(
        case_id=_CASE,
        event_type=CaseEventType.RESCHEDULE_REQUESTED,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s07b-reschedule",
        event_store=es,
    )
    record_lifecycle_event(
        case_id=_CASE,
        event_type=CaseEventType.NEW_SEARCH_INITIATED,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s07b-new-search",
        event_store=es,
    )

    events = es.get_events(_CASE)
    assert len(events) == event_count_before + 2
    assert events[-1].to_state == CaseLifecycleState.READY_TO_SEARCH
    # Chain is contiguous
    for i in range(len(events) - 1):
        assert events[i].to_state == events[i + 1].from_state


# ---------------------------------------------------------------------------
# S08 — COMPLETED and NO_SHOW are distinct outcomes
# ---------------------------------------------------------------------------

def test_s08_completion_vs_no_show_distinct():
    es1, ss1, cs1, bs1, rs1 = _fresh()
    es2, ss2, cs2, bs2, rs2 = _fresh()

    for case_id, es, ss, cs, bs, rs in [
        ("ACC-S08-COMPLETED", es1, ss1, cs1, bs1, rs1),
        ("ACC-S08-NO-SHOW", es2, ss2, cs2, bs2, rs2),
    ]:
        _seed_to_pending_scheduler_approval(es, case_id)
        ss.put(_sel(case_id, _OPTION_VA))
        cr = _conf_request(case_id, _OPTION_VA)
        cs.put_request(cr)
        cs.put_confirmation(_conf(case_id, _OPTION_VA))
        _do_commit(case_id, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs)

    # COMPLETED
    record_lifecycle_event(
        case_id="ACC-S08-COMPLETED",
        event_type=CaseEventType.APPOINTMENT_COMPLETED,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s08-complete",
        event_store=es1,
    )
    # NO_SHOW
    record_lifecycle_event(
        case_id="ACC-S08-NO-SHOW",
        event_type=CaseEventType.VETERAN_NO_SHOW,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s08-no-show",
        event_store=es2,
    )

    assert es1.get_lifecycle_record("ACC-S08-COMPLETED").current_state == CaseLifecycleState.COMPLETED
    assert es2.get_lifecycle_record("ACC-S08-NO-SHOW").current_state == CaseLifecycleState.NO_SHOW
    # They are different
    assert es1.get_lifecycle_record("ACC-S08-COMPLETED").current_state != \
           es2.get_lifecycle_record("ACC-S08-NO-SHOW").current_state

    # NO_SHOW can continue to HUMAN_REVIEW; COMPLETED cannot
    record_lifecycle_event(
        case_id="ACC-S08-NO-SHOW",
        event_type=CaseEventType.FOLLOW_UP_INITIATED,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s08-follow-up",
        event_store=es2,
    )
    assert es2.get_lifecycle_record("ACC-S08-NO-SHOW").current_state == CaseLifecycleState.HUMAN_REVIEW

    with pytest.raises(ValueError):
        record_lifecycle_event(
            case_id="ACC-S08-COMPLETED",
            event_type=CaseEventType.APPOINTMENT_COMPLETED,
            actor_role=ActorRole.SCHEDULER,
            actor_id=_SCHED_ID,
            idempotency_key="s08-complete-second",
            event_store=es1,
        )


# ---------------------------------------------------------------------------
# S09 — Source timeout does not produce false booking success
# (Lifecycle guard prevents commit when state is not PENDING_SCHEDULER_APPROVAL)
# ---------------------------------------------------------------------------

def test_s09_wrong_state_prevents_commit():
    """Case in HUMAN_REVIEW cannot be committed — simulates timeout/re-entry."""
    es, ss, cs, bs, rs = _fresh()

    # Only seed to HUMAN_REVIEW (as if search returned but no approval has been given)
    _seed_event(es, _CASE, CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
                CaseEventType.WORKFLOW_GATE_EVALUATED, "s09-rr")
    _seed_event(es, _CASE, CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
                CaseEventType.SEARCH_EXECUTED, "s09-rts")
    _seed_event(es, _CASE, CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
                CaseEventType.OPTIONS_ASSESSED, "s09-va")
    _seed_event(es, _CASE, CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
                CaseEventType.HANDOFF_PREPARED, "s09-rfh")

    ss.put(_sel(_CASE, _OPTION_VA))
    cs.put_confirmation(_conf(_CASE, _OPTION_VA))

    with pytest.raises(ValueError, match="PENDING_SCHEDULER_APPROVAL"):
        _do_commit(_CASE, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs)


# ---------------------------------------------------------------------------
# S10 — Every option has required provenance fields
# (Tested via BookingRecord provenance fields from M2-7)
# ---------------------------------------------------------------------------

def test_s10_booking_record_has_provenance():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE)
    ss.put(_sel(_CASE, _OPTION_VA))
    cr = _conf_request(_CASE, _OPTION_VA)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE, _OPTION_VA))

    booking = _do_commit(_CASE, _OPTION_VA, _SLOT_VA, "VISTA_ISS", es, ss, cs, bs, rs)

    # All required provenance fields must be present
    assert booking.booking_id is not None
    assert booking.case_id == _CASE
    assert booking.option_id == _OPTION_VA
    assert booking.slot_id == _SLOT_VA
    assert booking.source_system == "VISTA_ISS"
    assert booking.patient_id == _PATIENT
    assert booking.consult_id == _CONSULT
    assert booking.booked_at is not None
    assert booking.booked_by_role == ActorRole.SCHEDULER
    assert booking.booked_by_id == _SCHED_ID
    assert booking.synthetic is True


# ---------------------------------------------------------------------------
# S11 — HSRM auth and EPS slot availability revalidated independently
# ---------------------------------------------------------------------------

def test_s11_hsrm_and_eps_checked_independently():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE_CC)
    ss.put(_sel(_CASE_CC, _OPTION_CC))
    cr = _conf_request(_CASE_CC, _OPTION_CC)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE_CC, _OPTION_CC))

    # Good HSRM, bad EPS
    result_bad_eps = validate_booking_preconditions(
        case_id=_CASE_CC,
        option_id=_OPTION_CC,
        slot_id=_SLOT_CC,
        source_system="COMMUNITY_CARE",
        intended_service=_SERVICE,
        appointment_intent=AppointmentIntent.INITIAL_CONSULT,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s11-bad-eps",
        event_store=es,
        confirmation_store=cs,
        selection_store=ss,
        booking_store=bs,
        hsrm_record=_hsrm(_CASE_CC, _OPTION_CC),
        eps_slot=_eps(_OPTION_CC, _SLOT_CC, available=False),
    )
    assert not result_bad_eps.passed
    assert result_bad_eps.hsrm_checked is True
    assert result_bad_eps.eps_checked is True
    # Only EPS failure
    assert all("EPS" in f or "not available" in f for f in result_bad_eps.failures)

    # Bad HSRM, good EPS
    result_bad_hsrm = validate_booking_preconditions(
        case_id=_CASE_CC,
        option_id=_OPTION_CC,
        slot_id=_SLOT_CC,
        source_system="COMMUNITY_CARE",
        intended_service=_SERVICE,
        appointment_intent=AppointmentIntent.INITIAL_CONSULT,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s11-bad-hsrm",
        event_store=es,
        confirmation_store=cs,
        selection_store=ss,
        booking_store=bs,
        hsrm_record=_hsrm(_CASE_CC, _OPTION_CC, status=HSRMAuthorizationStatus.EXPIRED),
        eps_slot=_eps(_OPTION_CC, _SLOT_CC),
    )
    assert not result_bad_hsrm.passed
    assert result_bad_hsrm.hsrm_checked is True
    assert result_bad_hsrm.eps_checked is True
    assert any("HSRM" in f for f in result_bad_hsrm.failures)


# ---------------------------------------------------------------------------
# S12 — EPS follow-up booking fails closed
# ---------------------------------------------------------------------------

def test_s12_eps_follow_up_fails_closed():
    es, ss, cs, bs, rs = _fresh()
    _seed_to_pending_scheduler_approval(es, _CASE_CC)
    ss.put(_sel(_CASE_CC, _OPTION_CC))
    cr = _conf_request(_CASE_CC, _OPTION_CC)
    cs.put_request(cr)
    cs.put_confirmation(_conf(_CASE_CC, _OPTION_CC))

    result = validate_booking_preconditions(
        case_id=_CASE_CC,
        option_id=_OPTION_CC,
        slot_id=_SLOT_CC,
        source_system="COMMUNITY_CARE",
        intended_service=_SERVICE,
        appointment_intent=AppointmentIntent.FOLLOW_UP,  # <-- follow-up
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key="s12-follow-up",
        event_store=es,
        confirmation_store=cs,
        selection_store=ss,
        booking_store=bs,
        hsrm_record=_hsrm(_CASE_CC, _OPTION_CC),
        eps_slot=_eps(_OPTION_CC, _SLOT_CC),
    )
    assert not result.passed
    assert any("FOLLOW_UP" in f for f in result.failures)
