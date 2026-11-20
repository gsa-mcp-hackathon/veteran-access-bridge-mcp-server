"""M2-6 Veteran confirmation service tests.

Covers:
1.  VERIFIED_BOOKABLE → PENDING_VETERAN_CONFIRMATION
2.  Exactly one VETERAN_CONFIRMATION_REQUESTED event
3.  Duplicate preparation retry → no duplicate event, same request returned
4.  Missing lifecycle history → fail closed (prepare)
5.  Wrong lifecycle state → fail closed (prepare)
6.  Unknown selection_id → fail closed (prepare)
7.  Veteran CONFIRMED → PENDING_SCHEDULER_APPROVAL
8.  Veteran DECLINED → CANCELLED
9.  Veteran REQUESTED_CHANGE → HUMAN_REVIEW
10. Invalid response → fail closed
11. Non-VETERAN actor role → fail closed
12. Duplicate confirmation retry → no duplicate event, same record returned
13. Conflicting idempotency reuse → IdempotencyConflictError
14. Preparation does not imply consent
15. No BOOKED_SIMULATED event after any M2-6 operation
16. Full regression suite (implicit in pytest run)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

import pytest

from veteran_access_bridge.domain.models import (
    AccessOption,
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    ConfirmationRequest,
    OptionReadiness,
    OptionSelectionRecord,
    SourceProvenance,
    VeteranConfirmationRecord,
    VeteranResponse,
)
from veteran_access_bridge.services.confirmation import (
    ConfirmationStore,
    prepare_veteran_confirmation_request,
    record_veteran_confirmation,
)
from veteran_access_bridge.services.events import (
    CaseEventStore,
    IdempotencyConflictError,
)
from veteran_access_bridge.services.selection import SelectionStore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone.utc)
_CASE = "DEMO-CARD-5000335-001"
_PATIENT = "5000335"
_CONSULT = "CONSULT-CARD-5000335-001"
_HANDOFF_ID = "handoff-test-001"
_SCHED_ID = "sched-demo-001"
_VET_ID = "veteran-5000335"
_OPTION_ID = "OPT-VA-001"
_SELECTION_ID = "sel-abc123"
_IDEM_KEY = f"{_CASE}:confirm:OPT-VA-001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_stores() -> tuple[CaseEventStore, SelectionStore, ConfirmationStore]:
    return CaseEventStore(), SelectionStore(), ConfirmationStore()


def _selection_record(
    selection_id: str = _SELECTION_ID,
    option_id: str = _OPTION_ID,
    readiness: OptionReadiness = OptionReadiness.AVAILABLE,
) -> OptionSelectionRecord:
    return OptionSelectionRecord(
        selection_id=selection_id,
        case_id=_CASE,
        handoff_id=_HANDOFF_ID,
        option_id=option_id,
        readiness_at_selection=readiness,
        requires_verification=False,
        selected_at=_T0,
        selected_by_role=ActorRole.SCHEDULER,
        selected_by_id=_SCHED_ID,
        idempotency_key="sel-idem-001",
    )


def _seed_to_verified_bookable(
    event_store: CaseEventStore,
    selection_store: SelectionStore,
    option_id: str = _OPTION_ID,
    selection_id: str = _SELECTION_ID,
) -> None:
    """Seed lifecycle to VERIFIED_BOOKABLE and put a selection record."""
    states = [
        (CaseLifecycleState.REQUEST_RECEIVED,    CaseLifecycleState.READY_TO_SEARCH,           CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
        (CaseLifecycleState.READY_TO_SEARCH,      CaseLifecycleState.VA_OPTIONS_AVAILABLE,      CaseEventType.SEARCH_EXECUTED,         "e-va"),
        (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,         CaseEventType.OPTIONS_ASSESSED,        "e-rfh"),
        (CaseLifecycleState.READY_FOR_HANDOFF,    CaseLifecycleState.HUMAN_REVIEW,              CaseEventType.HANDOFF_PREPARED,        "e-hr"),
        (CaseLifecycleState.HUMAN_REVIEW,         CaseLifecycleState.OPTION_SELECTED,           CaseEventType.OPTION_SELECTED,         "e-os"),
        (CaseLifecycleState.OPTION_SELECTED,      CaseLifecycleState.VERIFIED_BOOKABLE,         CaseEventType.VERIFICATION_PASSED,     "e-vb"),
    ]
    for from_s, to_s, etype, eid in states:
        event_store.append(CaseEvent(
            event_id=eid, case_id=_CASE, event_type=etype,
            from_state=from_s, to_state=to_s,
            actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
            occurred_at=_T0, idempotency_key=eid,
        ))
    selection_store.put(_selection_record(selection_id=selection_id, option_id=option_id))


def _prepare(
    event_store: CaseEventStore,
    selection_store: SelectionStore,
    confirmation_store: ConfirmationStore,
    case_id: str = _CASE,
    option_id: str = _OPTION_ID,
    selection_id: str = _SELECTION_ID,
) -> ConfirmationRequest:
    return prepare_veteran_confirmation_request(
        case_id=case_id,
        option_id=option_id,
        selection_id=selection_id,
        event_store=event_store,
        selection_store=selection_store,
        confirmation_store=confirmation_store,
        _as_of=_T0,
    )


def _seed_to_pending_confirmation(
    event_store: CaseEventStore,
    selection_store: SelectionStore,
    confirmation_store: ConfirmationStore,
) -> ConfirmationRequest:
    """Seed to PENDING_VETERAN_CONFIRMATION and return the ConfirmationRequest."""
    _seed_to_verified_bookable(event_store, selection_store)
    return _prepare(event_store, selection_store, confirmation_store)


def _record_response(
    event_store: CaseEventStore,
    confirmation_store: ConfirmationStore,
    confirmation_request_id: str,
    response: VeteranResponse = VeteranResponse.CONFIRMED,
    idem_key: str = _IDEM_KEY,
) -> VeteranConfirmationRecord:
    return record_veteran_confirmation(
        case_id=_CASE,
        confirmation_request_id=confirmation_request_id,
        option_id=_OPTION_ID,
        response=response,
        actor_role=ActorRole.VETERAN,
        actor_id=_VET_ID,
        idempotency_key=idem_key,
        event_store=event_store,
        confirmation_store=confirmation_store,
        _as_of=_T0,
    )


# ===========================================================================
# Test 1: VERIFIED_BOOKABLE → PENDING_VETERAN_CONFIRMATION
# ===========================================================================

class TestPrepareTransition:
    """Test 1: prepare_veteran_confirmation_request advances lifecycle correctly."""

    def test_lifecycle_advances_to_pending_veteran_confirmation(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        _prepare(es, ss, cs)

        lc = es.get_lifecycle_record(_CASE)
        assert lc is not None
        assert lc.current_state == CaseLifecycleState.PENDING_VETERAN_CONFIRMATION

    def test_returns_confirmation_request(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        req = _prepare(es, ss, cs)

        assert isinstance(req, ConfirmationRequest)
        assert req.case_id == _CASE
        assert req.option_id == _OPTION_ID
        assert req.selection_id == _SELECTION_ID

    def test_request_actor_is_system(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        req = _prepare(es, ss, cs)

        assert req.requested_by_role == ActorRole.SYSTEM

    def test_request_id_includes_selection_id(self):
        """confirmation_request_id is derived from case + selection + option."""
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        req = _prepare(es, ss, cs)

        raw = f"confirmation:{_CASE}:{_SELECTION_ID}:{_OPTION_ID}"
        expected = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        assert req.confirmation_request_id == expected

    def test_different_selection_id_produces_different_request_id(self):
        """Different selection_id → different confirmation_request_id."""
        raw1 = f"confirmation:{_CASE}:sel-abc123:{_OPTION_ID}"
        raw2 = f"confirmation:{_CASE}:sel-xyz999:{_OPTION_ID}"
        id1 = "cr-" + hashlib.sha256(raw1.encode()).hexdigest()[:16]
        id2 = "cr-" + hashlib.sha256(raw2.encode()).hexdigest()[:16]
        assert id1 != id2


# ===========================================================================
# Test 2: Exactly one VETERAN_CONFIRMATION_REQUESTED event
# ===========================================================================

class TestExactlyOnePreparationEvent:
    """Test 2: prepare produces exactly one VETERAN_CONFIRMATION_REQUESTED event."""

    def test_exactly_one_event_appended(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)
        count_before = len(es.get_events(_CASE))

        _prepare(es, ss, cs)

        assert len(es.get_events(_CASE)) == count_before + 1

    def test_event_type_is_veteran_confirmation_requested(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        _prepare(es, ss, cs)

        last_evt = es.get_events(_CASE)[-1]
        assert last_evt.event_type == CaseEventType.VETERAN_CONFIRMATION_REQUESTED

    def test_event_actor_is_system(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        _prepare(es, ss, cs)

        last_evt = es.get_events(_CASE)[-1]
        assert last_evt.actor_role == ActorRole.SYSTEM


# ===========================================================================
# Test 3: Duplicate preparation retry → idempotent
# ===========================================================================

class TestPreparationIdempotency:
    """Test 3: Duplicate prepare call returns same request with no new event."""

    def test_retry_returns_same_request(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        r1 = _prepare(es, ss, cs)
        r2 = _prepare(es, ss, cs)

        assert r1 is r2

    def test_retry_no_duplicate_event(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        _prepare(es, ss, cs)
        count_after_first = len(es.get_events(_CASE))
        _prepare(es, ss, cs)

        assert len(es.get_events(_CASE)) == count_after_first

    def test_retry_no_duplicate_request_in_store(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        _prepare(es, ss, cs)
        _prepare(es, ss, cs)

        assert cs.request_count() == 1


# ===========================================================================
# Test 4: Missing lifecycle history → fail closed (prepare)
# ===========================================================================

class TestMissingHistoryPrepare:
    """Test 4: Missing lifecycle history fails prepare closed."""

    def test_no_history_raises(self):
        es, ss, cs = _fresh_stores()
        # Put selection record but no lifecycle events
        ss.put(_selection_record())

        with pytest.raises(ValueError, match="no lifecycle history"):
            _prepare(es, ss, cs)

    def test_no_history_no_event_written(self):
        es, ss, cs = _fresh_stores()
        ss.put(_selection_record())

        with pytest.raises(ValueError):
            _prepare(es, ss, cs)

        assert len(es.get_events(_CASE)) == 0


# ===========================================================================
# Test 5: Wrong lifecycle state → fail closed (prepare)
# ===========================================================================

class TestWrongStatePrepare:
    """Test 5: Wrong lifecycle state fails prepare closed."""

    def test_option_selected_state_fails(self):
        es, ss, cs = _fresh_stores()
        # Seed only to OPTION_SELECTED (not VERIFIED_BOOKABLE)
        states = [
            (CaseLifecycleState.REQUEST_RECEIVED,    CaseLifecycleState.READY_TO_SEARCH,      CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
            (CaseLifecycleState.READY_TO_SEARCH,      CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseEventType.SEARCH_EXECUTED,         "e-va"),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,    CaseEventType.OPTIONS_ASSESSED,        "e-rfh"),
            (CaseLifecycleState.READY_FOR_HANDOFF,    CaseLifecycleState.HUMAN_REVIEW,         CaseEventType.HANDOFF_PREPARED,        "e-hr"),
            (CaseLifecycleState.HUMAN_REVIEW,         CaseLifecycleState.OPTION_SELECTED,      CaseEventType.OPTION_SELECTED,         "e-os"),
        ]
        for from_s, to_s, etype, eid in states:
            es.append(CaseEvent(
                event_id=eid, case_id=_CASE, event_type=etype,
                from_state=from_s, to_state=to_s,
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                occurred_at=_T0, idempotency_key=eid,
            ))
        ss.put(_selection_record())

        with pytest.raises(ValueError, match="prepare_veteran_confirmation_request requires"):
            _prepare(es, ss, cs)

    def test_wrong_state_no_new_event(self):
        es, ss, cs = _fresh_stores()
        states = [
            (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH, CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
            (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseEventType.SEARCH_EXECUTED, "e-va"),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF, CaseEventType.OPTIONS_ASSESSED, "e-rfh"),
            (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW, CaseEventType.HANDOFF_PREPARED, "e-hr"),
            (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED, CaseEventType.OPTION_SELECTED, "e-os"),
        ]
        for from_s, to_s, etype, eid in states:
            es.append(CaseEvent(
                event_id=eid, case_id=_CASE, event_type=etype,
                from_state=from_s, to_state=to_s,
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                occurred_at=_T0, idempotency_key=eid,
            ))
        ss.put(_selection_record())
        count_before = len(es.get_events(_CASE))

        with pytest.raises(ValueError):
            _prepare(es, ss, cs)

        assert len(es.get_events(_CASE)) == count_before


# ===========================================================================
# Test 6: Unknown selection_id → fail closed (prepare)
# ===========================================================================

class TestUnknownSelectionIdPrepare:
    """Test 6: Unknown selection_id fails prepare closed."""

    def test_unknown_selection_id_raises(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)
        # Do NOT put the selection record — selection_store is empty

        # Create fresh stores so selection_store has no records
        es2, ss2, cs2 = _fresh_stores()
        _seed_to_verified_bookable(es2, ss2)
        # Remove the selection from ss2 by using a new SelectionStore
        from veteran_access_bridge.services.selection import SelectionStore as SS
        ss_empty = SS()

        with pytest.raises(ValueError, match="not found in SelectionStore"):
            prepare_veteran_confirmation_request(
                case_id=_CASE,
                option_id=_OPTION_ID,
                selection_id="sel-does-not-exist",
                event_store=es2,
                selection_store=ss_empty,
                confirmation_store=cs2,
                _as_of=_T0,
            )

    def test_unknown_selection_no_event(self):
        es, ss_empty, cs = _fresh_stores()
        _seed_to_verified_bookable(es, SelectionStore())
        # Manually seed lifecycle without a selection record
        states = [
            (CaseLifecycleState.REQUEST_RECEIVED,    CaseLifecycleState.READY_TO_SEARCH,      CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
            (CaseLifecycleState.READY_TO_SEARCH,      CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseEventType.SEARCH_EXECUTED,         "e-va"),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,    CaseEventType.OPTIONS_ASSESSED,        "e-rfh"),
            (CaseLifecycleState.READY_FOR_HANDOFF,    CaseLifecycleState.HUMAN_REVIEW,         CaseEventType.HANDOFF_PREPARED,        "e-hr"),
            (CaseLifecycleState.HUMAN_REVIEW,         CaseLifecycleState.OPTION_SELECTED,      CaseEventType.OPTION_SELECTED,         "e-os"),
            (CaseLifecycleState.OPTION_SELECTED,      CaseLifecycleState.VERIFIED_BOOKABLE,    CaseEventType.VERIFICATION_PASSED,     "e-vb"),
        ]
        es2 = CaseEventStore()
        for from_s, to_s, etype, eid in states:
            es2.append(CaseEvent(
                event_id=eid, case_id=_CASE, event_type=etype,
                from_state=from_s, to_state=to_s,
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                occurred_at=_T0, idempotency_key=eid,
            ))
        count_before = len(es2.get_events(_CASE))

        from veteran_access_bridge.services.selection import SelectionStore as SS
        with pytest.raises(ValueError):
            prepare_veteran_confirmation_request(
                case_id=_CASE, option_id=_OPTION_ID, selection_id="no-such-sel",
                event_store=es2, selection_store=SS(), confirmation_store=cs,
                _as_of=_T0,
            )

        assert len(es2.get_events(_CASE)) == count_before


# ===========================================================================
# Tests 7–9: record_veteran_confirmation response branches
# ===========================================================================

class TestVeteranResponseBranches:
    """Tests 7–9: Veteran responses route to correct lifecycle states."""

    def test_confirmed_advances_to_pending_scheduler_approval(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        _record_response(es, cs, req.confirmation_request_id, VeteranResponse.CONFIRMED)

        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.PENDING_SCHEDULER_APPROVAL

    def test_declined_advances_to_cancelled(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        _record_response(es, cs, req.confirmation_request_id, VeteranResponse.DECLINED)

        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.CANCELLED

    def test_requested_change_advances_to_human_review(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        _record_response(es, cs, req.confirmation_request_id, VeteranResponse.REQUESTED_CHANGE)

        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.HUMAN_REVIEW

    @pytest.mark.parametrize("response,event_type", [
        (VeteranResponse.CONFIRMED,        CaseEventType.VETERAN_CONFIRMED),
        (VeteranResponse.DECLINED,         CaseEventType.VETERAN_DECLINED),
        (VeteranResponse.REQUESTED_CHANGE, CaseEventType.VETERAN_REQUESTED_CHANGE),
    ])
    def test_correct_event_type_per_response(self, response, event_type):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        _record_response(es, cs, req.confirmation_request_id, response)

        last_evt = es.get_events(_CASE)[-1]
        assert last_evt.event_type == event_type

    def test_confirmation_record_carries_response(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        record = _record_response(es, cs, req.confirmation_request_id, VeteranResponse.CONFIRMED)

        assert record.response == VeteranResponse.CONFIRMED
        assert record.case_id == _CASE
        assert record.actor_role == ActorRole.VETERAN


# ===========================================================================
# Test 10: Invalid response → fail closed
# ===========================================================================

class TestInvalidResponse:
    """Test 10: Invalid response strings fail closed."""

    def test_invalid_response_string_raises(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        with pytest.raises(ValueError):
            record_veteran_confirmation(
                case_id=_CASE,
                confirmation_request_id=req.confirmation_request_id,
                option_id=_OPTION_ID,
                response="APPROVED",  # type: ignore[arg-type] — invalid value
                actor_role=ActorRole.VETERAN,
                actor_id=_VET_ID,
                idempotency_key=_IDEM_KEY,
                event_store=es,
                confirmation_store=cs,
                _as_of=_T0,
            )

    def test_invalid_response_no_event(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)
        count_before = len(es.get_events(_CASE))

        with pytest.raises(ValueError):
            record_veteran_confirmation(
                case_id=_CASE,
                confirmation_request_id=req.confirmation_request_id,
                option_id=_OPTION_ID,
                response="MAYBE",  # type: ignore[arg-type]
                actor_role=ActorRole.VETERAN,
                actor_id=_VET_ID,
                idempotency_key=_IDEM_KEY,
                event_store=es,
                confirmation_store=cs,
                _as_of=_T0,
            )

        assert len(es.get_events(_CASE)) == count_before


# ===========================================================================
# Test 11: Non-VETERAN actor → fail closed
# ===========================================================================

class TestActorRoleGuard:
    """Test 11: SCHEDULER and SYSTEM are rejected on record_veteran_confirmation."""

    @pytest.mark.parametrize("bad_role", [ActorRole.SCHEDULER, ActorRole.SYSTEM])
    def test_non_veteran_role_rejected(self, bad_role):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        with pytest.raises(ValueError, match="Only ActorRole.VETERAN"):
            record_veteran_confirmation(
                case_id=_CASE,
                confirmation_request_id=req.confirmation_request_id,
                option_id=_OPTION_ID,
                response=VeteranResponse.CONFIRMED,
                actor_role=bad_role,
                actor_id="bad-actor",
                idempotency_key=_IDEM_KEY,
                event_store=es,
                confirmation_store=cs,
                _as_of=_T0,
            )

    @pytest.mark.parametrize("bad_role", [ActorRole.SCHEDULER, ActorRole.SYSTEM])
    def test_non_veteran_no_event(self, bad_role):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)
        count_before = len(es.get_events(_CASE))

        with pytest.raises(ValueError):
            record_veteran_confirmation(
                case_id=_CASE,
                confirmation_request_id=req.confirmation_request_id,
                option_id=_OPTION_ID,
                response=VeteranResponse.CONFIRMED,
                actor_role=bad_role,
                actor_id="bad-actor",
                idempotency_key=_IDEM_KEY,
                event_store=es,
                confirmation_store=cs,
                _as_of=_T0,
            )

        assert len(es.get_events(_CASE)) == count_before


# ===========================================================================
# Test 12: Duplicate confirmation retry → idempotent
# ===========================================================================

class TestConfirmationIdempotency:
    """Test 12: Duplicate record_veteran_confirmation is idempotent."""

    def test_retry_returns_same_record(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        r1 = _record_response(es, cs, req.confirmation_request_id)
        r2 = _record_response(es, cs, req.confirmation_request_id)

        assert r1 is r2

    def test_retry_no_duplicate_event(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        _record_response(es, cs, req.confirmation_request_id)
        count_after_first = len(es.get_events(_CASE))
        _record_response(es, cs, req.confirmation_request_id)

        assert len(es.get_events(_CASE)) == count_after_first

    def test_retry_no_duplicate_record_in_store(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        _record_response(es, cs, req.confirmation_request_id)
        _record_response(es, cs, req.confirmation_request_id)

        assert cs.confirmation_count() == 1


# ===========================================================================
# Test 13: Conflicting idempotency reuse → IdempotencyConflictError
# ===========================================================================

class TestIdempotencyConflict:
    """Test 13: Same key + different material → IdempotencyConflictError."""

    def test_same_key_different_response_raises(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        _record_response(es, cs, req.confirmation_request_id,
                         VeteranResponse.CONFIRMED, idem_key="conf-001")

        # Same key, different response
        with pytest.raises(IdempotencyConflictError):
            record_veteran_confirmation(
                case_id=_CASE,
                confirmation_request_id=req.confirmation_request_id,
                option_id=_OPTION_ID,
                response=VeteranResponse.DECLINED,
                actor_role=ActorRole.VETERAN,
                actor_id=_VET_ID,
                idempotency_key="conf-001",
                event_store=es,
                confirmation_store=cs,
                _as_of=_T0,
            )

    def test_conflict_no_extra_event(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        _record_response(es, cs, req.confirmation_request_id,
                         VeteranResponse.CONFIRMED, idem_key="conf-001")
        count_before = len(es.get_events(_CASE))

        with pytest.raises(IdempotencyConflictError):
            record_veteran_confirmation(
                case_id=_CASE,
                confirmation_request_id=req.confirmation_request_id,
                option_id=_OPTION_ID,
                response=VeteranResponse.DECLINED,
                actor_role=ActorRole.VETERAN,
                actor_id=_VET_ID,
                idempotency_key="conf-001",
                event_store=es,
                confirmation_store=cs,
                _as_of=_T0,
            )

        assert len(es.get_events(_CASE)) == count_before

    def test_conflict_no_second_record(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        _record_response(es, cs, req.confirmation_request_id,
                         VeteranResponse.CONFIRMED, idem_key="conf-001")

        with pytest.raises(IdempotencyConflictError):
            record_veteran_confirmation(
                case_id=_CASE,
                confirmation_request_id=req.confirmation_request_id,
                option_id=_OPTION_ID,
                response=VeteranResponse.DECLINED,
                actor_role=ActorRole.VETERAN,
                actor_id=_VET_ID,
                idempotency_key="conf-001",
                event_store=es,
                confirmation_store=cs,
                _as_of=_T0,
            )

        assert cs.confirmation_count() == 1


# ===========================================================================
# Test 14: Preparation does not imply consent
# ===========================================================================

class TestPreparationNotConsent:
    """Test 14: After preparation, lifecycle is PENDING_VETERAN_CONFIRMATION."""

    def test_lifecycle_is_pending_not_approved(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        _prepare(es, ss, cs)

        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.PENDING_VETERAN_CONFIRMATION
        assert lc.current_state != CaseLifecycleState.PENDING_SCHEDULER_APPROVAL

    def test_no_veteran_confirmed_event_after_prepare(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        _prepare(es, ss, cs)

        event_types = [e.event_type for e in es.get_events(_CASE)]
        assert CaseEventType.VETERAN_CONFIRMED not in event_types
        assert CaseEventType.VETERAN_CONFIRMATION_REQUESTED in event_types


# ===========================================================================
# Test 15: No BOOKED_SIMULATED event after any M2-6 operation
# ===========================================================================

class TestNoBookedSimulated:
    """Test 15: M2-6 never creates a BOOKED_SIMULATED event."""

    def test_no_booked_simulated_after_prepare(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)
        _prepare(es, ss, cs)

        event_types = [e.event_type for e in es.get_events(_CASE)]
        assert CaseEventType.BOOKED_SIMULATED not in event_types

    def test_no_booked_simulated_after_confirmed(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)
        _record_response(es, cs, req.confirmation_request_id, VeteranResponse.CONFIRMED)

        event_types = [e.event_type for e in es.get_events(_CASE)]
        assert CaseEventType.BOOKED_SIMULATED not in event_types

    def test_no_booked_simulated_after_declined(self):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)
        _record_response(es, cs, req.confirmation_request_id, VeteranResponse.DECLINED)

        event_types = [e.event_type for e in es.get_events(_CASE)]
        assert CaseEventType.BOOKED_SIMULATED not in event_types


# ===========================================================================
# Exactly one event per transition
# ===========================================================================

class TestExactlyOneEventPerTransition:
    """Each M2-6 operation appends exactly one lifecycle event."""

    def test_prepare_adds_one_event(self):
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)
        count_before = len(es.get_events(_CASE))

        _prepare(es, ss, cs)

        assert len(es.get_events(_CASE)) == count_before + 1

    @pytest.mark.parametrize("response", list(VeteranResponse))
    def test_record_response_adds_one_event(self, response):
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)
        count_before = len(es.get_events(_CASE))

        _record_response(es, cs, req.confirmation_request_id, response)

        assert len(es.get_events(_CASE)) == count_before + 1


# ===========================================================================
# ConfirmationStore unit tests
# ===========================================================================

class TestConfirmationStore:
    """Unit tests for ConfirmationStore."""

    def _make_request(self, case_id: str = _CASE) -> ConfirmationRequest:
        raw = f"confirmation:{case_id}:{_SELECTION_ID}:{_OPTION_ID}"
        cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        return ConfirmationRequest(
            confirmation_request_id=cr_id,
            case_id=case_id,
            option_id=_OPTION_ID,
            selection_id=_SELECTION_ID,
            requested_at=_T0,
            requested_by_role=ActorRole.SYSTEM,
        )

    def _make_record(self, idem_key: str = "k1") -> VeteranConfirmationRecord:
        conf_id = "conf-" + hashlib.sha256(idem_key.encode()).hexdigest()[:16]
        raw = f"confirmation:{_CASE}:{_SELECTION_ID}:{_OPTION_ID}"
        cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        return VeteranConfirmationRecord(
            confirmation_id=conf_id,
            confirmation_request_id=cr_id,
            case_id=_CASE,
            option_id=_OPTION_ID,
            response=VeteranResponse.CONFIRMED,
            responded_at=_T0,
            actor_role=ActorRole.VETERAN,
            actor_id=_VET_ID,
            idempotency_key=idem_key,
        )

    def test_put_and_get_request(self):
        cs = ConfirmationStore()
        req = self._make_request()
        cs.put_request(req)
        assert cs.get_request(req.confirmation_request_id) is req

    def test_get_request_for_case(self):
        cs = ConfirmationStore()
        req = self._make_request()
        cs.put_request(req)
        assert cs.get_request_for_case(_CASE) is req

    def test_second_put_request_is_no_op(self):
        cs = ConfirmationStore()
        req = self._make_request()
        cs.put_request(req)
        cs.put_request(req)
        assert cs.request_count() == 1

    def test_put_and_get_confirmation(self):
        cs = ConfirmationStore()
        record = self._make_record("k1")
        cs.put_confirmation(record)
        assert cs.get_confirmation(record.confirmation_id) is record

    def test_get_confirmation_by_key(self):
        cs = ConfirmationStore()
        record = self._make_record("k1")
        cs.put_confirmation(record)
        assert cs.get_confirmation_by_key("k1") is record

    def test_get_confirmation_for_case(self):
        cs = ConfirmationStore()
        record = self._make_record("k1")
        cs.put_confirmation(record)
        assert cs.get_confirmation_for_case(_CASE) is record

    def test_unknown_request_returns_none(self):
        cs = ConfirmationStore()
        assert cs.get_request("nonexistent") is None
        assert cs.get_request_for_case("UNKNOWN") is None

    def test_unknown_confirmation_returns_none(self):
        cs = ConfirmationStore()
        assert cs.get_confirmation("nonexistent") is None
        assert cs.get_confirmation_by_key("nonexistent") is None
        assert cs.get_confirmation_for_case("UNKNOWN") is None


# ===========================================================================
# Model invariants
# ===========================================================================

class TestModelInvariants:
    """ConfirmationRequest and VeteranConfirmationRecord are frozen."""

    def test_confirmation_request_is_frozen(self):
        raw = f"confirmation:{_CASE}:{_SELECTION_ID}:{_OPTION_ID}"
        cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        req = ConfirmationRequest(
            confirmation_request_id=cr_id,
            case_id=_CASE, option_id=_OPTION_ID, selection_id=_SELECTION_ID,
            requested_at=_T0, requested_by_role=ActorRole.SYSTEM,
        )
        with pytest.raises((AttributeError, TypeError)):
            req.option_id = "OPT-TAMPERED"  # type: ignore[misc]

    def test_veteran_confirmation_record_is_frozen(self):
        conf_id = "conf-" + hashlib.sha256(b"k1").hexdigest()[:16]
        raw = f"confirmation:{_CASE}:{_SELECTION_ID}:{_OPTION_ID}"
        cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        record = VeteranConfirmationRecord(
            confirmation_id=conf_id, confirmation_request_id=cr_id,
            case_id=_CASE, option_id=_OPTION_ID, response=VeteranResponse.CONFIRMED,
            responded_at=_T0, actor_role=ActorRole.VETERAN, actor_id=_VET_ID,
            idempotency_key="k1",
        )
        with pytest.raises((AttributeError, TypeError)):
            record.response = VeteranResponse.DECLINED  # type: ignore[misc]

    def test_synthetic_defaults(self):
        raw = f"confirmation:{_CASE}:{_SELECTION_ID}:{_OPTION_ID}"
        cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        req = ConfirmationRequest(
            confirmation_request_id=cr_id, case_id=_CASE,
            option_id=_OPTION_ID, selection_id=_SELECTION_ID,
            requested_at=_T0, requested_by_role=ActorRole.SYSTEM,
        )
        assert req.synthetic is True


# ===========================================================================
# MCP tool integration tests
# ===========================================================================

class TestMcpToolIntegration:
    """Smoke tests for the MCP tool run() functions."""

    def test_prepare_tool_returns_confirmation_request_id(self):
        from veteran_access_bridge.mcp.tools.prepare_veteran_confirmation_request import run
        es, ss, cs = _fresh_stores()
        _seed_to_verified_bookable(es, ss)

        result = run(
            _CASE, _OPTION_ID, _SELECTION_ID,
            event_store=es, selection_store=ss, confirmation_store=cs,
        )

        assert "confirmation_request_id" in result
        assert result["is_veteran_consent"] is False
        assert result["creates_booking"] is False

    def test_record_tool_confirmed_returns_record(self):
        from veteran_access_bridge.mcp.tools.record_veteran_confirmation import run
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        result = run(
            _CASE, req.confirmation_request_id, _OPTION_ID,
            "CONFIRMED", _VET_ID, _IDEM_KEY,
            event_store=es, confirmation_store=cs,
        )

        assert result["response"] == "CONFIRMED"
        assert result["creates_booking"] is False

    def test_record_tool_invalid_response_raises(self):
        from veteran_access_bridge.mcp.tools.record_veteran_confirmation import run
        es, ss, cs = _fresh_stores()
        req = _seed_to_pending_confirmation(es, ss, cs)

        with pytest.raises(ValueError):
            run(
                _CASE, req.confirmation_request_id, _OPTION_ID,
                "APPROVED", _VET_ID, _IDEM_KEY,
                event_store=es, confirmation_store=cs,
            )


# ===========================================================================
# Missing lifecycle history guard (record_veteran_confirmation)
# ===========================================================================

class TestMissingHistoryRecord:
    """record_veteran_confirmation fails closed on missing history."""

    def test_no_history_raises(self):
        es, ss, cs = _fresh_stores()
        # Put a confirmation request but no lifecycle events
        raw = f"confirmation:{_CASE}:{_SELECTION_ID}:{_OPTION_ID}"
        cr_id = "cr-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        cs.put_request(ConfirmationRequest(
            confirmation_request_id=cr_id, case_id=_CASE,
            option_id=_OPTION_ID, selection_id=_SELECTION_ID,
            requested_at=_T0, requested_by_role=ActorRole.SYSTEM,
        ))

        with pytest.raises(ValueError, match="no lifecycle history"):
            record_veteran_confirmation(
                case_id=_CASE,
                confirmation_request_id=cr_id,
                option_id=_OPTION_ID,
                response=VeteranResponse.CONFIRMED,
                actor_role=ActorRole.VETERAN,
                actor_id=_VET_ID,
                idempotency_key=_IDEM_KEY,
                event_store=es,
                confirmation_store=cs,
                _as_of=_T0,
            )


# ===========================================================================
# Unknown confirmation_request_id guard
# ===========================================================================

class TestUnknownConfirmationRequestId:
    """record_veteran_confirmation fails closed on unknown confirmation_request_id."""

    def test_unknown_request_id_raises(self):
        es, ss, cs = _fresh_stores()
        _seed_to_pending_confirmation(es, ss, cs)

        with pytest.raises(ValueError, match="not found"):
            record_veteran_confirmation(
                case_id=_CASE,
                confirmation_request_id="cr-does-not-exist",
                option_id=_OPTION_ID,
                response=VeteranResponse.CONFIRMED,
                actor_role=ActorRole.VETERAN,
                actor_id=_VET_ID,
                idempotency_key=_IDEM_KEY,
                event_store=es,
                confirmation_store=cs,
                _as_of=_T0,
            )
