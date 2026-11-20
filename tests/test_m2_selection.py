"""M2-4 tests: validate_option_selection and record_option_selection.

Covers:
- valid selection (AVAILABLE VA option)
- valid selection (AUTHORIZED_NOT_VERIFIED CC option → requires_verification=True)
- unknown option_id
- option not present in handoff
- stale option rejection
- unavailable option rejection
- AVAILABLE_NOT_AUTHORIZED rejection
- wrong lifecycle state
- missing lifecycle history
- invalid actor role (VETERAN)
- invalid actor role (SYSTEM)
- duplicate retry idempotency (same key + same payload → existing record)
- conflicting idempotency-key reuse (same key + different option → error)
- exactly one OPTION_SELECTED event after retries
- lifecycle state after selection is OPTION_SELECTED
- OptionSelectionRecord fields: immutable, correct
- OptionSelectionValidation fields: defined, typed correctly
- selection_id derived from idempotency_key (not option_id)
- MCP validate tool integration: passes
- MCP validate tool integration: stale fails
- MCP record tool integration: valid round-trip
- MCP record tool integration: wrong state fails
- full regression (all prior tests)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import pytest

from veteran_access_bridge.domain.models import (
    AccessOption,
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    OptionReadiness,
    OptionSelectionRecord,
    OptionSelectionValidation,
    SchedulingHandoff,
    SourceProvenance,
)
from veteran_access_bridge.services.events import CaseEventStore, IdempotencyConflictError
from veteran_access_bridge.services.handoff import HandoffStore
from veteran_access_bridge.services.selection import (
    SelectionStore,
    record_option_selection,
    validate_option_selection,
)

# ---------------------------------------------------------------------------
# shared test clock and case IDs
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
_CASE = "DEMO-CARD-5000335-001"
_PATIENT = "5000335"
_CONSULT = "CONSULT-CARD-5000335-001"
_HANDOFF_ID = "handoff-test-001"
_SCHED_ID = "sched-demo-001"
_IDEM_KEY = f"{_CASE}:selection:OPT-VA-001"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _prov(source: str = "VISTA_ISS") -> SourceProvenance:
    return SourceProvenance(
        source_system=source,
        source_record_id=f"slot-{source}-001",
        retrieved_at=_T0,
        synthetic=True,
        environment="test",
        freshness="fixture-deterministic",
    )


def _opt(option_id: str, readiness: OptionReadiness, source: str = "VISTA_ISS") -> AccessOption:
    return AccessOption(
        option_id=option_id,
        source_system=source,
        source_record_id=option_id,
        specialty="Cardiology",
        facility_name="Test VA Medical Center",
        facility_id="000",
        slot_start=datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc),
        slot_end=datetime(2026, 11, 10, 9, 30, tzinfo=timezone.utc),
        availability_status="AVAILABLE",
        readiness=readiness,
        provenance=_prov(source),
    )


def _fresh_stores() -> tuple[CaseEventStore, HandoffStore, SelectionStore]:
    return CaseEventStore(), HandoffStore(), SelectionStore()


def _handoff_with(*options: AccessOption) -> SchedulingHandoff:
    return SchedulingHandoff(
        handoff_id=_HANDOFF_ID,
        patient_id=_PATIENT,
        consult_id=_CONSULT,
        prepared_at=_T0,
        options=options,
        viable_option_count=len(options),
        synthetic=True,
    )


def _seed_to_human_review(
    es: CaseEventStore,
    case_id: str = _CASE,
) -> None:
    """Seed exactly the events needed to reach HUMAN_REVIEW."""
    steps = [
        (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
         CaseEventType.WORKFLOW_GATE_EVALUATED, ActorRole.SYSTEM, "ik-1"),
        (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
         CaseEventType.SEARCH_EXECUTED, ActorRole.SYSTEM, "ik-2"),
        (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
         CaseEventType.OPTIONS_ASSESSED, ActorRole.SYSTEM, "ik-3"),
        (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
         CaseEventType.HANDOFF_PREPARED, ActorRole.SYSTEM, "ik-4"),
    ]
    for f, t, et, role, ik in steps:
        es.append(CaseEvent(
            event_id=f"{case_id}:{ik}",
            case_id=case_id,
            event_type=et,
            from_state=f,
            to_state=t,
            actor_role=role,
            actor_id="system",
            occurred_at=_T0,
            idempotency_key=f"{case_id}:{ik}",
        ))


def _record(
    es: CaseEventStore,
    hs: HandoffStore,
    ss: SelectionStore,
    option_id: str = "OPT-VA-001",
    idempotency_key: str = _IDEM_KEY,
    actor_id: str = _SCHED_ID,
) -> OptionSelectionRecord:
    return record_option_selection(
        case_id=_CASE,
        handoff_id=_HANDOFF_ID,
        option_id=option_id,
        actor_role=ActorRole.SCHEDULER,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        event_store=es,
        handoff_store=hs,
        selection_store=ss,
        _as_of=_T0,
    )


def _setup_valid(
    readiness: OptionReadiness = OptionReadiness.AVAILABLE,
    option_id: str = "OPT-VA-001",
) -> tuple[CaseEventStore, HandoffStore, SelectionStore]:
    es, hs, ss = _fresh_stores()
    _seed_to_human_review(es)
    hs.put(_handoff_with(_opt(option_id, readiness)))
    return es, hs, ss


# ---------------------------------------------------------------------------
# 1. Valid selection — AVAILABLE
# ---------------------------------------------------------------------------

class TestValidSelection:
    def test_available_option_validation_passes(self) -> None:
        es, hs, ss = _setup_valid()
        result = validate_option_selection(_CASE, _HANDOFF_ID, "OPT-VA-001", es, hs)
        assert result.valid is True
        assert result.option is not None
        assert result.option.option_id == "OPT-VA-001"
        assert result.requires_verification is False

    def test_available_option_record_succeeds(self) -> None:
        es, hs, ss = _setup_valid()
        rec = _record(es, hs, ss)
        assert rec.option_id == "OPT-VA-001"
        assert rec.readiness_at_selection == OptionReadiness.AVAILABLE
        assert rec.requires_verification is False
        assert rec.synthetic is True

    def test_selection_id_derived_from_idempotency_key(self) -> None:
        es, hs, ss = _setup_valid()
        rec = _record(es, hs, ss, idempotency_key="custom-idem-key")
        expected = "sel-" + hashlib.sha256("custom-idem-key".encode()).hexdigest()[:16]
        assert rec.selection_id == expected

    def test_selection_id_does_not_encode_option_id(self) -> None:
        """selection_id is derived from idempotency_key, not option_id."""
        es, hs, ss = _setup_valid()
        rec = _record(es, hs, ss, idempotency_key="my-key")
        assert "OPT-VA-001" not in rec.selection_id


# ---------------------------------------------------------------------------
# 2. Valid selection — AUTHORIZED_NOT_VERIFIED → requires_verification=True
# ---------------------------------------------------------------------------

class TestAuthorizedNotVerified:
    def test_authorized_not_verified_passes_validation(self) -> None:
        es, hs, ss = _setup_valid(OptionReadiness.AUTHORIZED_NOT_VERIFIED, "OPT-CC-001")
        result = validate_option_selection(_CASE, _HANDOFF_ID, "OPT-CC-001", es, hs)
        assert result.valid is True
        assert result.requires_verification is True

    def test_authorized_not_verified_sets_flag_in_record(self) -> None:
        es, hs, ss = _setup_valid(OptionReadiness.AUTHORIZED_NOT_VERIFIED, "OPT-CC-001")
        rec = _record(es, hs, ss, option_id="OPT-CC-001")
        assert rec.requires_verification is True
        assert rec.readiness_at_selection == OptionReadiness.AUTHORIZED_NOT_VERIFIED

    def test_readiness_not_upgraded_in_record(self) -> None:
        es, hs, ss = _setup_valid(OptionReadiness.AUTHORIZED_NOT_VERIFIED, "OPT-CC-001")
        rec = _record(es, hs, ss, option_id="OPT-CC-001")
        assert rec.readiness_at_selection != OptionReadiness.VERIFIED_BOOKABLE


# ---------------------------------------------------------------------------
# 3. Unknown / missing option
# ---------------------------------------------------------------------------

class TestUnknownOption:
    def test_unknown_option_id_fails_validation(self) -> None:
        es, hs, ss = _setup_valid()
        result = validate_option_selection(_CASE, _HANDOFF_ID, "OPT-DOES-NOT-EXIST", es, hs)
        assert result.valid is False
        assert "OPT-DOES-NOT-EXIST" in result.reason

    def test_unknown_option_id_raises_on_record(self) -> None:
        es, hs, ss = _setup_valid()
        with pytest.raises(ValueError, match="OPT-DOES-NOT-EXIST"):
            _record(es, hs, ss, option_id="OPT-DOES-NOT-EXIST")

    def test_option_not_in_handoff_fails(self) -> None:
        """Option exists in another handoff but not in the specified one."""
        es, hs, ss = _fresh_stores()
        _seed_to_human_review(es)
        # Handoff contains OPT-A; we ask for OPT-B
        hs.put(_handoff_with(_opt("OPT-A", OptionReadiness.AVAILABLE)))
        result = validate_option_selection(_CASE, _HANDOFF_ID, "OPT-B", es, hs)
        assert result.valid is False
        assert "OPT-B" in result.reason


# ---------------------------------------------------------------------------
# 4. Rejected readiness values
# ---------------------------------------------------------------------------

class TestRejectedReadiness:
    @pytest.mark.parametrize("readiness", [
        OptionReadiness.STALE,
        OptionReadiness.UNAVAILABLE,
        OptionReadiness.SOURCE_UNAVAILABLE,
        OptionReadiness.AVAILABLE_NOT_AUTHORIZED,
    ])
    def test_rejected_readiness_fails_validation(self, readiness: OptionReadiness) -> None:
        es, hs, ss = _setup_valid(readiness)
        result = validate_option_selection(_CASE, _HANDOFF_ID, "OPT-VA-001", es, hs)
        assert result.valid is False
        assert readiness.value in result.reason

    @pytest.mark.parametrize("readiness", [
        OptionReadiness.STALE,
        OptionReadiness.UNAVAILABLE,
        OptionReadiness.AVAILABLE_NOT_AUTHORIZED,
    ])
    def test_rejected_readiness_raises_on_record(self, readiness: OptionReadiness) -> None:
        es, hs, ss = _setup_valid(readiness)
        with pytest.raises(ValueError):
            _record(es, hs, ss)


# ---------------------------------------------------------------------------
# 5. Wrong lifecycle state
# ---------------------------------------------------------------------------

class TestWrongLifecycleState:
    def test_ready_to_search_state_fails_validation(self) -> None:
        es, hs, ss = _fresh_stores()
        # Seed only to READY_TO_SEARCH — not HUMAN_REVIEW
        es.append(CaseEvent(
            event_id=f"{_CASE}:ik-1", case_id=_CASE,
            event_type=CaseEventType.WORKFLOW_GATE_EVALUATED,
            from_state=CaseLifecycleState.REQUEST_RECEIVED,
            to_state=CaseLifecycleState.READY_TO_SEARCH,
            actor_role=ActorRole.SYSTEM, actor_id="s",
            occurred_at=_T0, idempotency_key=f"{_CASE}:ik-1",
        ))
        hs.put(_handoff_with(_opt("OPT-VA-001", OptionReadiness.AVAILABLE)))
        result = validate_option_selection(_CASE, _HANDOFF_ID, "OPT-VA-001", es, hs)
        assert result.valid is False
        assert "READY_TO_SEARCH" in result.reason

    def test_wrong_state_raises_on_record(self) -> None:
        es, hs, ss = _fresh_stores()
        es.append(CaseEvent(
            event_id=f"{_CASE}:ik-1", case_id=_CASE,
            event_type=CaseEventType.WORKFLOW_GATE_EVALUATED,
            from_state=CaseLifecycleState.REQUEST_RECEIVED,
            to_state=CaseLifecycleState.READY_TO_SEARCH,
            actor_role=ActorRole.SYSTEM, actor_id="s",
            occurred_at=_T0, idempotency_key=f"{_CASE}:ik-1",
        ))
        hs.put(_handoff_with(_opt("OPT-VA-001", OptionReadiness.AVAILABLE)))
        with pytest.raises(ValueError, match="READY_TO_SEARCH"):
            _record(es, hs, ss)


# ---------------------------------------------------------------------------
# 6. Missing lifecycle history
# ---------------------------------------------------------------------------

class TestMissingLifecycleHistory:
    def test_missing_history_fails_validation(self) -> None:
        es, hs, ss = _fresh_stores()
        hs.put(_handoff_with(_opt("OPT-VA-001", OptionReadiness.AVAILABLE)))
        result = validate_option_selection(_CASE, _HANDOFF_ID, "OPT-VA-001", es, hs)
        assert result.valid is False
        assert "no lifecycle history" in result.reason

    def test_missing_history_raises_on_record(self) -> None:
        es, hs, ss = _fresh_stores()
        hs.put(_handoff_with(_opt("OPT-VA-001", OptionReadiness.AVAILABLE)))
        with pytest.raises(ValueError, match="no lifecycle history"):
            _record(es, hs, ss)


# ---------------------------------------------------------------------------
# 7. Invalid actor role
# ---------------------------------------------------------------------------

class TestInvalidActorRole:
    def test_veteran_role_rejected(self) -> None:
        es, hs, ss = _setup_valid()
        with pytest.raises(ValueError, match="SCHEDULER"):
            record_option_selection(
                case_id=_CASE, handoff_id=_HANDOFF_ID, option_id="OPT-VA-001",
                actor_role=ActorRole.VETERAN, actor_id="vet-001",
                idempotency_key=_IDEM_KEY,
                event_store=es, handoff_store=hs, selection_store=ss,
                _as_of=_T0,
            )

    def test_system_role_rejected(self) -> None:
        es, hs, ss = _setup_valid()
        with pytest.raises(ValueError, match="SCHEDULER"):
            record_option_selection(
                case_id=_CASE, handoff_id=_HANDOFF_ID, option_id="OPT-VA-001",
                actor_role=ActorRole.SYSTEM, actor_id="sys",
                idempotency_key=_IDEM_KEY,
                event_store=es, handoff_store=hs, selection_store=ss,
                _as_of=_T0,
            )


# ---------------------------------------------------------------------------
# 8. Duplicate retry idempotency
# ---------------------------------------------------------------------------

class TestIdempotencyRetry:
    def test_same_key_same_payload_returns_existing(self) -> None:
        es, hs, ss = _setup_valid()
        r1 = _record(es, hs, ss)
        r2 = _record(es, hs, ss)
        assert r1 is r2

    def test_exactly_one_event_after_retries(self) -> None:
        es, hs, ss = _setup_valid()
        _record(es, hs, ss)
        _record(es, hs, ss)
        _record(es, hs, ss)
        events = [e for e in es.get_events(_CASE)
                  if e.event_type == CaseEventType.OPTION_SELECTED]
        assert len(events) == 1

    def test_same_key_same_payload_does_not_grow_selection_store(self) -> None:
        es, hs, ss = _setup_valid()
        _record(es, hs, ss)
        _record(es, hs, ss)
        assert len(ss) == 1


# ---------------------------------------------------------------------------
# 9. Conflicting idempotency-key reuse
# ---------------------------------------------------------------------------

class TestIdempotencyConflict:
    def test_same_key_different_option_fails_closed(self) -> None:
        es, hs, ss = _fresh_stores()
        _seed_to_human_review(es)
        # Handoff has two options
        hs.put(_handoff_with(
            _opt("OPT-A", OptionReadiness.AVAILABLE),
            _opt("OPT-B", OptionReadiness.AVAILABLE),
        ))
        # First selection: OPT-A
        _record(es, hs, ss, option_id="OPT-A", idempotency_key="shared-key")
        # Second attempt with same key but different option → must fail closed
        with pytest.raises(IdempotencyConflictError):
            _record(es, hs, ss, option_id="OPT-B", idempotency_key="shared-key")

    def test_conflict_appends_no_second_event(self) -> None:
        es, hs, ss = _fresh_stores()
        _seed_to_human_review(es)
        hs.put(_handoff_with(
            _opt("OPT-A", OptionReadiness.AVAILABLE),
            _opt("OPT-B", OptionReadiness.AVAILABLE),
        ))
        _record(es, hs, ss, option_id="OPT-A", idempotency_key="shared-key")
        events_before = es.get_events(_CASE)
        try:
            _record(es, hs, ss, option_id="OPT-B", idempotency_key="shared-key")
        except IdempotencyConflictError:
            pass
        events_after = es.get_events(_CASE)
        assert events_before == events_after

    def test_conflict_writes_no_selection_record(self) -> None:
        es, hs, ss = _fresh_stores()
        _seed_to_human_review(es)
        hs.put(_handoff_with(
            _opt("OPT-A", OptionReadiness.AVAILABLE),
            _opt("OPT-B", OptionReadiness.AVAILABLE),
        ))
        _record(es, hs, ss, option_id="OPT-A", idempotency_key="shared-key")
        store_size_before = len(ss)
        try:
            _record(es, hs, ss, option_id="OPT-B", idempotency_key="shared-key")
        except IdempotencyConflictError:
            pass
        assert len(ss) == store_size_before


# ---------------------------------------------------------------------------
# 10. Lifecycle state after selection
# ---------------------------------------------------------------------------

class TestLifecycleStateAfterSelection:
    def test_lifecycle_state_is_option_selected(self) -> None:
        es, hs, ss = _setup_valid()
        _record(es, hs, ss)
        record = es.get_lifecycle_record(_CASE)
        assert record is not None
        assert record.current_state == CaseLifecycleState.OPTION_SELECTED

    def test_option_selected_event_carries_payload(self) -> None:
        es, hs, ss = _setup_valid()
        rec = _record(es, hs, ss)
        events = [e for e in es.get_events(_CASE)
                  if e.event_type == CaseEventType.OPTION_SELECTED]
        assert len(events) == 1
        evt = events[0]
        assert evt.payload is not None
        assert evt.payload["option_id"] == "OPT-VA-001"
        assert evt.payload["selection_id"] == rec.selection_id


# ---------------------------------------------------------------------------
# 11. OptionSelectionRecord model properties
# ---------------------------------------------------------------------------

class TestOptionSelectionRecordModel:
    def test_record_is_frozen(self) -> None:
        es, hs, ss = _setup_valid()
        rec = _record(es, hs, ss)
        with pytest.raises((AttributeError, TypeError)):
            rec.option_id = "modified"  # type: ignore[misc]

    def test_record_carries_correct_handoff_id(self) -> None:
        es, hs, ss = _setup_valid()
        rec = _record(es, hs, ss)
        assert rec.handoff_id == _HANDOFF_ID

    def test_record_actor_role_is_scheduler(self) -> None:
        es, hs, ss = _setup_valid()
        rec = _record(es, hs, ss)
        assert rec.selected_by_role == ActorRole.SCHEDULER


# ---------------------------------------------------------------------------
# 12. OptionSelectionValidation model
# ---------------------------------------------------------------------------

class TestOptionSelectionValidationModel:
    def test_failed_validation_has_no_option(self) -> None:
        es, hs, ss = _fresh_stores()
        result = validate_option_selection(_CASE, _HANDOFF_ID, "OPT-X", es, hs)
        assert result.valid is False
        assert result.option is None

    def test_passed_validation_has_option(self) -> None:
        es, hs, ss = _setup_valid()
        result = validate_option_selection(_CASE, _HANDOFF_ID, "OPT-VA-001", es, hs)
        assert result.valid is True
        assert isinstance(result.option, AccessOption)

    def test_validation_is_frozen(self) -> None:
        v = OptionSelectionValidation(valid=True)
        with pytest.raises((AttributeError, TypeError)):
            v.valid = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 13. SelectionStore unit tests
# ---------------------------------------------------------------------------

class TestSelectionStore:
    def _make_record(self, idem_key: str = "k1") -> OptionSelectionRecord:
        return OptionSelectionRecord(
            selection_id="sel-" + hashlib.sha256(idem_key.encode()).hexdigest()[:16],
            case_id=_CASE,
            handoff_id=_HANDOFF_ID,
            option_id="OPT-VA-001",
            readiness_at_selection=OptionReadiness.AVAILABLE,
            requires_verification=False,
            selected_at=_T0,
            selected_by_role=ActorRole.SCHEDULER,
            selected_by_id=_SCHED_ID,
            idempotency_key=idem_key,
        )

    def test_put_and_get(self) -> None:
        ss = SelectionStore()
        r = self._make_record()
        ss.put(r)
        assert ss.get(r.selection_id) is r

    def test_get_by_key(self) -> None:
        ss = SelectionStore()
        r = self._make_record("my-key")
        ss.put(r)
        assert ss.get_by_key("my-key") is r

    def test_second_put_is_no_op(self) -> None:
        ss = SelectionStore()
        r1 = self._make_record()
        r2 = OptionSelectionRecord(
            selection_id=r1.selection_id, case_id="other",
            handoff_id=_HANDOFF_ID, option_id="OPT-OTHER",
            readiness_at_selection=OptionReadiness.AVAILABLE,
            requires_verification=False, selected_at=_T0,
            selected_by_role=ActorRole.SCHEDULER, selected_by_id=_SCHED_ID,
            idempotency_key=r1.idempotency_key,
        )
        ss.put(r1)
        ss.put(r2)
        assert ss.get(r1.selection_id).case_id == _CASE  # first wins

    def test_unknown_returns_none(self) -> None:
        ss = SelectionStore()
        assert ss.get("nonexistent") is None
        assert ss.get_by_key("nonexistent") is None

    def test_get_for_case(self) -> None:
        ss = SelectionStore()
        r = self._make_record()
        ss.put(r)
        assert ss.get_for_case(_CASE) is r

    def test_get_for_case_unknown(self) -> None:
        ss = SelectionStore()
        assert ss.get_for_case("unknown-case") is None


# ---------------------------------------------------------------------------
# 14. MCP tool integration
# ---------------------------------------------------------------------------

class TestMcpToolIntegration:
    def test_validate_tool_passes_for_valid_option(self) -> None:
        from veteran_access_bridge.mcp.tools.validate_option_selection import run as vos_run
        es, hs, ss = _setup_valid()
        result = vos_run(_CASE, _HANDOFF_ID, "OPT-VA-001", event_store=es, handoff_store=hs)
        assert result["valid"] is True
        assert result["case_id"] == _CASE

    def test_validate_tool_fails_for_stale_option(self) -> None:
        from veteran_access_bridge.mcp.tools.validate_option_selection import run as vos_run
        es, hs, ss = _setup_valid(OptionReadiness.STALE)
        result = vos_run(_CASE, _HANDOFF_ID, "OPT-VA-001", event_store=es, handoff_store=hs)
        assert result["valid"] is False
        assert "STALE" in result["reason"]

    def test_record_tool_returns_correct_fields(self) -> None:
        from veteran_access_bridge.mcp.tools.record_option_selection import run as ros_run
        es, hs, ss = _setup_valid()
        result = ros_run(
            _CASE, _HANDOFF_ID, "OPT-VA-001", _SCHED_ID, _IDEM_KEY,
            event_store=es, handoff_store=hs, selection_store=ss,
        )
        assert result["option_id"] == "OPT-VA-001"
        assert result["synthetic"] is True
        assert result["creates_booking"] is False
        assert result["creates_confirmation"] is False

    def test_record_tool_wrong_state_raises(self) -> None:
        from veteran_access_bridge.mcp.tools.record_option_selection import run as ros_run
        es, hs, ss = _fresh_stores()
        # Seed only to READY_TO_SEARCH
        es.append(CaseEvent(
            event_id=f"{_CASE}:ik-1", case_id=_CASE,
            event_type=CaseEventType.WORKFLOW_GATE_EVALUATED,
            from_state=CaseLifecycleState.REQUEST_RECEIVED,
            to_state=CaseLifecycleState.READY_TO_SEARCH,
            actor_role=ActorRole.SYSTEM, actor_id="s",
            occurred_at=_T0, idempotency_key=f"{_CASE}:ik-1",
        ))
        hs.put(_handoff_with(_opt("OPT-VA-001", OptionReadiness.AVAILABLE)))
        with pytest.raises(ValueError):
            ros_run(
                _CASE, _HANDOFF_ID, "OPT-VA-001", _SCHED_ID, _IDEM_KEY,
                event_store=es, handoff_store=hs, selection_store=ss,
            )
