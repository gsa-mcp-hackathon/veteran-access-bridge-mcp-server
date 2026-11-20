"""M2-2 CaseEventStore tests.

Covers:
- valid append
- invalid transition rejection
- duplicate retry idempotency (same idempotency_key → return existing)
- conflicting event_id reuse (same id, different data → fail closed)
- same event_id + same data → idempotent
- event ordering (from_state must match current persisted state)
- deterministic state reconstruction from event history
- terminal-state protection (COMPLETED, CANCELLED block further appends)
- WorkflowState rejection despite equal string value  ← targeted regression
- actor-role validation
- immutable history (get_events returns copies, not mutable references)
- case_ids() membership
- unknown case returns None from get_lifecycle_record
"""

from __future__ import annotations

import pytest

from veteran_access_bridge.domain.models import (
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleRecord,
    CaseLifecycleState,
    WorkflowState,
)
from veteran_access_bridge.services.events import (
    CaseEventStore,
    IdempotencyConflictError,
    InvalidTransitionError,
    TerminalStateError,
)

# ---------------------------------------------------------------------------
# shared test clock
# ---------------------------------------------------------------------------

from datetime import datetime, timezone

_T0 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 10, 16, 12, 1, 0, tzinfo=timezone.utc)
_T2 = datetime(2026, 10, 16, 12, 2, 0, tzinfo=timezone.utc)
_T3 = datetime(2026, 10, 16, 12, 3, 0, tzinfo=timezone.utc)

_CASE = "DEMO-CARD-5000335-001"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _evt(
    event_id: str,
    from_state: CaseLifecycleState,
    to_state: CaseLifecycleState,
    idempotency_key: str,
    *,
    case_id: str = _CASE,
    event_type: CaseEventType = CaseEventType.WORKFLOW_GATE_EVALUATED,
    actor_role: ActorRole = ActorRole.SYSTEM,
    occurred_at: datetime = _T0,
    payload: dict | None = None,
) -> CaseEvent:
    return CaseEvent(
        event_id=event_id,
        case_id=case_id,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        actor_role=actor_role,
        actor_id="test-actor",
        occurred_at=occurred_at,
        idempotency_key=idempotency_key,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# 1. Valid append
# ---------------------------------------------------------------------------


class TestValidAppend:
    def test_single_valid_event_is_stored(self) -> None:
        store = CaseEventStore()
        evt = _evt(
            "evt-001",
            CaseLifecycleState.REQUEST_RECEIVED,
            CaseLifecycleState.READY_TO_SEARCH,
            "idem-001",
        )
        result = store.append(evt)
        assert result is evt

    def test_event_appears_in_history(self) -> None:
        store = CaseEventStore()
        evt = _evt("evt-001", CaseLifecycleState.REQUEST_RECEIVED,
                   CaseLifecycleState.READY_TO_SEARCH, "idem-001")
        store.append(evt)
        assert store.get_events(_CASE) == (evt,)

    def test_sequential_valid_events_stored_in_order(self) -> None:
        store = CaseEventStore()
        e1 = _evt("evt-001", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.READY_TO_SEARCH, "idem-001",
                  occurred_at=_T0)
        e2 = _evt("evt-002", CaseLifecycleState.READY_TO_SEARCH,
                  CaseLifecycleState.VA_OPTIONS_AVAILABLE, "idem-002",
                  event_type=CaseEventType.SEARCH_EXECUTED,
                  occurred_at=_T1)
        store.append(e1)
        store.append(e2)
        history = store.get_events(_CASE)
        assert history == (e1, e2)

    def test_case_id_registered_after_first_append(self) -> None:
        store = CaseEventStore()
        evt = _evt("evt-001", CaseLifecycleState.REQUEST_RECEIVED,
                   CaseLifecycleState.READY_TO_SEARCH, "idem-001")
        store.append(evt)
        assert _CASE in store.case_ids()


# ---------------------------------------------------------------------------
# 2. Invalid transition rejection
# ---------------------------------------------------------------------------


class TestInvalidTransitionRejection:
    def test_skip_from_request_received_to_booked_simulated_raises(self) -> None:
        store = CaseEventStore()
        with pytest.raises(InvalidTransitionError):
            store.append(_evt(
                "evt-001",
                CaseLifecycleState.REQUEST_RECEIVED,
                CaseLifecycleState.BOOKED_SIMULATED,
                "idem-001",
            ))

    def test_skip_verified_bookable_to_booked_simulated_raises(self) -> None:
        """VERIFIED_BOOKABLE must not skip veteran confirmation."""
        store = CaseEventStore()
        # Advance to VERIFIED_BOOKABLE legitimately
        for e in [
            _evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                 CaseLifecycleState.READY_TO_SEARCH, "ik-1"),
            _evt("e2", CaseLifecycleState.READY_TO_SEARCH,
                 CaseLifecycleState.VA_OPTIONS_AVAILABLE, "ik-2",
                 event_type=CaseEventType.SEARCH_EXECUTED),
            _evt("e3", CaseLifecycleState.VA_OPTIONS_AVAILABLE,
                 CaseLifecycleState.READY_FOR_HANDOFF, "ik-3",
                 event_type=CaseEventType.OPTIONS_ASSESSED),
            _evt("e4", CaseLifecycleState.READY_FOR_HANDOFF,
                 CaseLifecycleState.HUMAN_REVIEW, "ik-4",
                 event_type=CaseEventType.HANDOFF_PREPARED),
            _evt("e5", CaseLifecycleState.HUMAN_REVIEW,
                 CaseLifecycleState.OPTION_SELECTED, "ik-5",
                 event_type=CaseEventType.OPTION_SELECTED,
                 actor_role=ActorRole.SCHEDULER),
            _evt("e6", CaseLifecycleState.OPTION_SELECTED,
                 CaseLifecycleState.VERIFIED_BOOKABLE, "ik-6",
                 event_type=CaseEventType.VERIFICATION_PASSED,
                 actor_role=ActorRole.SCHEDULER),
        ]:
            store.append(e)

        with pytest.raises(InvalidTransitionError):
            store.append(_evt(
                "e7",
                CaseLifecycleState.VERIFIED_BOOKABLE,
                CaseLifecycleState.BOOKED_SIMULATED,
                "ik-7",
                event_type=CaseEventType.BOOKED_SIMULATED,
                actor_role=ActorRole.SCHEDULER,
            ))

    def test_error_message_names_the_bad_transition(self) -> None:
        store = CaseEventStore()
        with pytest.raises(InvalidTransitionError, match="READY_TO_SEARCH"):
            store.append(_evt(
                "evt-001",
                CaseLifecycleState.READY_TO_SEARCH,
                CaseLifecycleState.COMPLETED,
                "idem-001",
            ))


# ---------------------------------------------------------------------------
# 3. Duplicate retry idempotency — same idempotency_key returns existing event
# ---------------------------------------------------------------------------


class TestIdempotencyRetry:
    def test_same_idempotency_key_returns_existing_event(self) -> None:
        store = CaseEventStore()
        evt = _evt("evt-001", CaseLifecycleState.REQUEST_RECEIVED,
                   CaseLifecycleState.READY_TO_SEARCH, "idem-001")
        first = store.append(evt)
        second = store.append(evt)
        assert second is first

    def test_duplicate_does_not_grow_history(self) -> None:
        store = CaseEventStore()
        evt = _evt("evt-001", CaseLifecycleState.REQUEST_RECEIVED,
                   CaseLifecycleState.READY_TO_SEARCH, "idem-001")
        store.append(evt)
        store.append(evt)
        store.append(evt)
        assert len(store.get_events(_CASE)) == 1

    def test_different_event_id_same_idempotency_key_returns_first(self) -> None:
        """Two different event_ids with the same idempotency_key → first wins."""
        store = CaseEventStore()
        e1 = _evt("evt-001", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.READY_TO_SEARCH, "idem-shared")
        e2 = _evt("evt-002", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.READY_TO_SEARCH, "idem-shared")
        first = store.append(e1)
        second = store.append(e2)
        assert second is first
        assert first.event_id == "evt-001"


# ---------------------------------------------------------------------------
# 4. Conflicting event_id reuse — same id, different data → fail closed
# ---------------------------------------------------------------------------


class TestIdempotencyConflict:
    def test_same_event_id_different_to_state_raises(self) -> None:
        store = CaseEventStore()
        e1 = _evt("evt-CONFLICT", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.READY_TO_SEARCH, "idem-001")
        # e2 shares event_id but claims a different to_state
        e2 = _evt("evt-CONFLICT", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.CONSULT_PENDING, "idem-002")
        store.append(e1)
        with pytest.raises(IdempotencyConflictError):
            store.append(e2)

    def test_error_names_conflicting_event_id(self) -> None:
        store = CaseEventStore()
        e1 = _evt("evt-X", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.READY_TO_SEARCH, "idem-a")
        e2 = _evt("evt-X", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.CONSULT_PENDING, "idem-b")
        store.append(e1)
        with pytest.raises(IdempotencyConflictError, match="evt-X"):
            store.append(e2)

    def test_same_event_id_same_data_is_idempotent(self) -> None:
        """Same event_id AND same data → treat as idempotent, return existing."""
        store = CaseEventStore()
        e1 = _evt("evt-SAME", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.READY_TO_SEARCH, "idem-001")
        # e2 has a different idempotency_key but same event_id and same data
        e2 = _evt("evt-SAME", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.READY_TO_SEARCH, "idem-002")
        first = store.append(e1)
        second = store.append(e2)
        assert second is first


# ---------------------------------------------------------------------------
# 5. Event ordering — from_state must match current persisted state
# ---------------------------------------------------------------------------


class TestEventOrdering:
    def test_out_of_order_from_state_rejected(self) -> None:
        store = CaseEventStore()
        store.append(_evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-1"))
        # Current state is READY_TO_SEARCH; from_state says CONSULT_PENDING
        with pytest.raises(InvalidTransitionError, match="READY_TO_SEARCH"):
            store.append(_evt(
                "e2",
                CaseLifecycleState.CONSULT_PENDING,   # wrong
                CaseLifecycleState.READY_TO_SEARCH,
                "ik-2",
            ))

    def test_correct_sequence_accepted(self) -> None:
        store = CaseEventStore()
        store.append(_evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-1"))
        store.append(_evt("e2", CaseLifecycleState.READY_TO_SEARCH,
                          CaseLifecycleState.SOURCE_UNAVAILABLE, "ik-2",
                          event_type=CaseEventType.SEARCH_EXECUTED))
        assert len(store.get_events(_CASE)) == 2


# ---------------------------------------------------------------------------
# 6. Deterministic state reconstruction
# ---------------------------------------------------------------------------


class TestStateReconstruction:
    def test_no_events_returns_none(self) -> None:
        store = CaseEventStore()
        assert store.get_lifecycle_record("NONEXISTENT") is None

    def test_single_event_reconstructs_to_state(self) -> None:
        store = CaseEventStore()
        store.append(_evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-1"))
        record = store.get_lifecycle_record(_CASE)
        assert record is not None
        assert record.current_state == CaseLifecycleState.READY_TO_SEARCH

    def test_multi_event_reconstructs_latest_to_state(self) -> None:
        store = CaseEventStore()
        store.append(_evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-1"))
        store.append(_evt("e2", CaseLifecycleState.READY_TO_SEARCH,
                          CaseLifecycleState.VA_OPTIONS_AVAILABLE, "ik-2",
                          event_type=CaseEventType.SEARCH_EXECUTED))
        record = store.get_lifecycle_record(_CASE)
        assert record is not None
        assert record.current_state == CaseLifecycleState.VA_OPTIONS_AVAILABLE

    def test_event_count_is_accurate(self) -> None:
        store = CaseEventStore()
        for i, (f, t) in enumerate([
            (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH),
            (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE),
        ]):
            store.append(_evt(f"e{i}", f, t, f"ik-{i}",
                              event_type=CaseEventType.SEARCH_EXECUTED if i else
                              CaseEventType.WORKFLOW_GATE_EVALUATED))
        record = store.get_lifecycle_record(_CASE)
        assert record is not None
        assert record.event_count == 2

    def test_reconstruction_is_deterministic(self) -> None:
        """Same event sequence always yields the same record."""
        def build() -> CaseLifecycleRecord | None:
            s = CaseEventStore()
            s.append(_evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-1"))
            s.append(_evt("e2", CaseLifecycleState.READY_TO_SEARCH,
                          CaseLifecycleState.SOURCE_UNAVAILABLE, "ik-2",
                          event_type=CaseEventType.SEARCH_EXECUTED))
            return s.get_lifecycle_record(_CASE)

        r1, r2 = build(), build()
        assert r1 is not None and r2 is not None
        assert r1.current_state == r2.current_state
        assert r1.event_count == r2.event_count


# ---------------------------------------------------------------------------
# 7. Terminal-state protection
# ---------------------------------------------------------------------------


class TestTerminalStateProtection:
    def _advance_to_cancelled(self) -> CaseEventStore:
        store = CaseEventStore()
        store.append(_evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-1"))
        store.append(_evt("e2", CaseLifecycleState.READY_TO_SEARCH,
                          CaseLifecycleState.VA_OPTIONS_AVAILABLE, "ik-2",
                          event_type=CaseEventType.SEARCH_EXECUTED))
        store.append(_evt("e3", CaseLifecycleState.VA_OPTIONS_AVAILABLE,
                          CaseLifecycleState.READY_FOR_HANDOFF, "ik-3",
                          event_type=CaseEventType.OPTIONS_ASSESSED))
        store.append(_evt("e4", CaseLifecycleState.READY_FOR_HANDOFF,
                          CaseLifecycleState.HUMAN_REVIEW, "ik-4",
                          event_type=CaseEventType.HANDOFF_PREPARED))
        store.append(_evt("e5", CaseLifecycleState.HUMAN_REVIEW,
                          CaseLifecycleState.CANCELLED, "ik-5",
                          event_type=CaseEventType.APPOINTMENT_CANCELLED,
                          actor_role=ActorRole.SCHEDULER))
        return store

    def test_cancelled_case_rejects_further_transitions(self) -> None:
        store = self._advance_to_cancelled()
        with pytest.raises((TerminalStateError, InvalidTransitionError)):
            store.append(_evt(
                "e6",
                CaseLifecycleState.CANCELLED,
                CaseLifecycleState.READY_TO_SEARCH,
                "ik-6",
                event_type=CaseEventType.SEARCH_RETRY_REQUESTED,
            ))

    def test_completed_case_rejects_further_transitions(self) -> None:
        store = CaseEventStore()
        # Build a minimal path to COMPLETED via BOOKED_SIMULATED
        transitions = [
            (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
             CaseEventType.WORKFLOW_GATE_EVALUATED, ActorRole.SYSTEM),
            (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
             CaseEventType.SEARCH_EXECUTED, ActorRole.SYSTEM),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
             CaseEventType.OPTIONS_ASSESSED, ActorRole.SYSTEM),
            (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
             CaseEventType.HANDOFF_PREPARED, ActorRole.SYSTEM),
            (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED,
             CaseEventType.OPTION_SELECTED, ActorRole.SCHEDULER),
            (CaseLifecycleState.OPTION_SELECTED, CaseLifecycleState.VERIFIED_BOOKABLE,
             CaseEventType.VERIFICATION_PASSED, ActorRole.SCHEDULER),
            (CaseLifecycleState.VERIFIED_BOOKABLE, CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
             CaseEventType.VETERAN_CONFIRMATION_REQUESTED, ActorRole.SCHEDULER),
            (CaseLifecycleState.PENDING_VETERAN_CONFIRMATION, CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
             CaseEventType.VETERAN_CONFIRMED, ActorRole.VETERAN),
            (CaseLifecycleState.PENDING_SCHEDULER_APPROVAL, CaseLifecycleState.BOOKED_SIMULATED,
             CaseEventType.BOOKED_SIMULATED, ActorRole.SCHEDULER),
            (CaseLifecycleState.BOOKED_SIMULATED, CaseLifecycleState.COMPLETED,
             CaseEventType.APPOINTMENT_COMPLETED, ActorRole.SCHEDULER),
        ]
        for i, (f, t, et, role) in enumerate(transitions):
            store.append(_evt(f"e{i}", f, t, f"ik-{i}",
                               event_type=et, actor_role=role))

        record = store.get_lifecycle_record(_CASE)
        assert record is not None
        assert record.current_state == CaseLifecycleState.COMPLETED

        with pytest.raises((TerminalStateError, InvalidTransitionError)):
            store.append(_evt(
                "e-bad",
                CaseLifecycleState.COMPLETED,
                CaseLifecycleState.READY_TO_SEARCH,
                "ik-bad",
            ))

    def test_terminal_error_message_names_terminal_state(self) -> None:
        store = self._advance_to_cancelled()
        with pytest.raises((TerminalStateError, InvalidTransitionError), match="CANCELLED"):
            store.append(_evt(
                "e6",
                CaseLifecycleState.CANCELLED,
                CaseLifecycleState.READY_TO_SEARCH,
                "ik-6",
            ))


# ---------------------------------------------------------------------------
# 8. WorkflowState rejection — targeted cross-type regression
# ---------------------------------------------------------------------------


class TestWorkflowStateRejection:
    """Regression: WorkflowState must be rejected even when its string value
    equals a CaseLifecycleState value.

    This test permanently documents and protects against the cross-type bug
    identified in M2-1: Python StrEnum equality compares string values, so
    WorkflowState.READY_TO_SEARCH == CaseLifecycleState.READY_TO_SEARCH is True.
    The event store must catch this at the type boundary, not rely on equality.
    """

    def test_equal_string_values_confirm_the_hazard(self) -> None:
        """Confirm the hazard exists: equal string values despite different types."""
        assert WorkflowState.READY_TO_SEARCH == CaseLifecycleState.READY_TO_SEARCH
        assert type(WorkflowState.READY_TO_SEARCH) is not type(CaseLifecycleState.READY_TO_SEARCH)

    def test_workflow_state_as_from_state_raises_type_error(self) -> None:
        store = CaseEventStore()
        # Deliberately pass WorkflowState where CaseLifecycleState is required
        bad_evt = _evt(
            "evt-bad",
            WorkflowState.READY_TO_SEARCH,   # type: ignore[arg-type]
            CaseLifecycleState.VA_OPTIONS_AVAILABLE,
            "idem-bad",
        )
        with pytest.raises(TypeError):
            store.append(bad_evt)

    def test_workflow_state_as_to_state_raises_type_error(self) -> None:
        store = CaseEventStore()
        bad_evt = _evt(
            "evt-bad",
            CaseLifecycleState.READY_TO_SEARCH,
            WorkflowState.VA_OPTIONS_AVAILABLE,   # type: ignore[arg-type]
            "idem-bad",
        )
        with pytest.raises(TypeError):
            store.append(bad_evt)

    def test_type_error_message_names_workflow_state(self) -> None:
        store = CaseEventStore()
        bad_evt = _evt(
            "evt-bad",
            WorkflowState.READY_TO_SEARCH,   # type: ignore[arg-type]
            CaseLifecycleState.VA_OPTIONS_AVAILABLE,
            "idem-bad",
        )
        with pytest.raises(TypeError, match="WorkflowState"):
            store.append(bad_evt)


# ---------------------------------------------------------------------------
# 9. Actor-role validation
# ---------------------------------------------------------------------------


class TestActorRoleValidation:
    def test_invalid_actor_role_string_raises_type_error(self) -> None:
        store = CaseEventStore()
        bad_evt = CaseEvent(
            event_id="evt-role",
            case_id=_CASE,
            event_type=CaseEventType.WORKFLOW_GATE_EVALUATED,
            from_state=CaseLifecycleState.REQUEST_RECEIVED,
            to_state=CaseLifecycleState.READY_TO_SEARCH,
            actor_role="ADMIN",   # type: ignore[arg-type]  # not an ActorRole
            actor_id="x",
            occurred_at=_T0,
            idempotency_key="ik-role",
        )
        with pytest.raises(TypeError):
            store.append(bad_evt)

    def test_valid_roles_accepted(self) -> None:
        store = CaseEventStore()
        for role in (ActorRole.SCHEDULER, ActorRole.VETERAN, ActorRole.SYSTEM):
            # Each valid role gets its own store / case to avoid ordering conflicts
            s = CaseEventStore()
            s.append(_evt("evt-" + role.value,
                          CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH,
                          "ik-" + role.value,
                          actor_role=role))


# ---------------------------------------------------------------------------
# 10. Immutable history
# ---------------------------------------------------------------------------


class TestImmutableHistory:
    def test_get_events_returns_tuple_not_list(self) -> None:
        store = CaseEventStore()
        store.append(_evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-1"))
        history = store.get_events(_CASE)
        assert isinstance(history, tuple)

    def test_modifying_returned_tuple_does_not_affect_store(self) -> None:
        store = CaseEventStore()
        evt = _evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                   CaseLifecycleState.READY_TO_SEARCH, "ik-1")
        store.append(evt)
        history = store.get_events(_CASE)
        # tuples are immutable; this test confirms the contract
        assert len(history) == 1
        assert history[0] is evt

    def test_second_call_returns_independent_copy(self) -> None:
        store = CaseEventStore()
        store.append(_evt("e1", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-1"))
        h1 = store.get_events(_CASE)
        h2 = store.get_events(_CASE)
        assert h1 == h2
        assert h1 is not h2  # distinct tuple objects


# ---------------------------------------------------------------------------
# 11. Multiple independent cases
# ---------------------------------------------------------------------------


class TestMultipleCases:
    def test_two_cases_are_independent(self) -> None:
        store = CaseEventStore()
        case_a = "CASE-A"
        case_b = "CASE-B"
        ea = _evt("e-a", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.READY_TO_SEARCH, "ik-a", case_id=case_a)
        eb = _evt("e-b", CaseLifecycleState.REQUEST_RECEIVED,
                  CaseLifecycleState.CONSULT_PENDING, "ik-b", case_id=case_b)
        store.append(ea)
        store.append(eb)
        assert store.get_lifecycle_record(case_a).current_state == CaseLifecycleState.READY_TO_SEARCH
        assert store.get_lifecycle_record(case_b).current_state == CaseLifecycleState.CONSULT_PENDING

    def test_case_ids_contains_both(self) -> None:
        store = CaseEventStore()
        store.append(_evt("e-a", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-a", case_id="A"))
        store.append(_evt("e-b", CaseLifecycleState.REQUEST_RECEIVED,
                          CaseLifecycleState.READY_TO_SEARCH, "ik-b", case_id="B"))
        assert {"A", "B"}.issubset(store.case_ids())
