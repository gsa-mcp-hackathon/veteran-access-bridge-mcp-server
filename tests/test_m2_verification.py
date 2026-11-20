"""M2-5 Verification service tests.

Covers:
1.  VA AVAILABLE selection → VERIFIED_BOOKABLE (route_from_option_selected)
2.  Federal EHR AVAILABLE selection → VERIFIED_BOOKABLE
3.  Community Care AUTHORIZED_NOT_VERIFIED → READY_TO_VERIFY (returns None)
4.  READY_TO_VERIFY + VERIFIED evidence → VERIFIED_BOOKABLE
5.  READY_TO_VERIFY + AUTH_REQUIRED evidence → AUTH_REQUIRED
6.  READY_TO_VERIFY + INCONCLUSIVE evidence → HUMAN_REVIEW
7.  Wrong lifecycle state → fail closed (both functions)
8.  Missing lifecycle history → fail closed (both functions)
9.  Unknown selection_id → fail closed (route_from_option_selected)
10. Readiness mismatch (STALE / UNAVAILABLE / AVAILABLE_NOT_AUTHORIZED) → fail closed
11. Community Care auth state never upgraded without record_verification_result
12. Duplicate retry → no duplicate event, same result returned (both functions)
13. Conflicting idempotency reuse → IdempotencyConflictError (both functions)
14. Exactly one lifecycle event per successful transition
15. Full regression: prior 247 + new tests all pass (implicit in pytest run)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from veteran_access_bridge.domain.models import (
    AccessOption,
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    OptionReadiness,
    OptionSelectionRecord,
    SourceProvenance,
    VerificationOutcome,
    VerificationResult,
)
from veteran_access_bridge.services.events import (
    CaseEventStore,
    IdempotencyConflictError,
)
from veteran_access_bridge.services.selection import SelectionStore
from veteran_access_bridge.services.verification import (
    VerificationStore,
    record_verification_result,
    route_from_option_selected,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 10, 20, 9, 0, 0, tzinfo=timezone.utc)
_CASE = "DEMO-CARD-5000335-001"
_PATIENT = "5000335"
_CONSULT = "CONSULT-CARD-5000335-001"
_HANDOFF_ID = "handoff-test-001"
_SCHED_ID = "sched-demo-001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prov(source: str = "VISTA_ISS") -> SourceProvenance:
    return SourceProvenance(
        source_system=source,
        source_record_id="REC-001",
        retrieved_at=_T0,
        synthetic=True,
        environment="test",
        freshness="fresh",
    )


def _opt(option_id: str, readiness: OptionReadiness, source: str = "VISTA_ISS") -> AccessOption:
    return AccessOption(
        option_id=option_id,
        source_system=source,
        source_record_id=f"SLOT-{option_id}",
        specialty="CARDIOLOGY",
        facility_name="VA Medical Center Test",
        facility_id="FAC-001",
        slot_start=_T0,
        slot_end=_T0,
        availability_status="AVAILABLE",
        readiness=readiness,
        provenance=_prov(source),
    )


def _fresh_stores() -> tuple[CaseEventStore, SelectionStore, VerificationStore]:
    return CaseEventStore(), SelectionStore(), VerificationStore()


def _selection_record(
    selection_id: str,
    option_id: str,
    readiness: OptionReadiness,
    source: str = "VISTA_ISS",
    requires_verification: bool = False,
    idem_key: str = "sel-idem-001",
) -> OptionSelectionRecord:
    return OptionSelectionRecord(
        selection_id=selection_id,
        case_id=_CASE,
        handoff_id=_HANDOFF_ID,
        option_id=option_id,
        readiness_at_selection=readiness,
        requires_verification=requires_verification,
        selected_at=_T0,
        selected_by_role=ActorRole.SCHEDULER,
        selected_by_id=_SCHED_ID,
        idempotency_key=idem_key,
    )


def _seed_to_option_selected(
    event_store: CaseEventStore,
    selection_store: SelectionStore,
    option_id: str = "OPT-VA-001",
    readiness: OptionReadiness = OptionReadiness.AVAILABLE,
    source: str = "VISTA_ISS",
) -> OptionSelectionRecord:
    """Seed event store through OPTION_SELECTED and put a selection record."""
    states = [
        (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
         CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
        (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
         CaseEventType.SEARCH_EXECUTED, "e-va"),
        (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
         CaseEventType.OPTIONS_ASSESSED, "e-rfh"),
        (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
         CaseEventType.HANDOFF_PREPARED, "e-hr"),
        (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED,
         CaseEventType.OPTION_SELECTED, "e-os"),
    ]
    for from_s, to_s, etype, eid in states:
        event_store.append(CaseEvent(
            event_id=eid,
            case_id=_CASE,
            event_type=etype,
            from_state=from_s,
            to_state=to_s,
            actor_role=ActorRole.SCHEDULER,
            actor_id=_SCHED_ID,
            occurred_at=_T0,
            idempotency_key=eid,
        ))

    sel = _selection_record(
        selection_id="sel-abc123",
        option_id=option_id,
        readiness=readiness,
        source=source,
        requires_verification=(readiness == OptionReadiness.AUTHORIZED_NOT_VERIFIED),
    )
    selection_store.put(sel)
    return sel


def _seed_to_ready_to_verify(
    event_store: CaseEventStore,
    selection_store: SelectionStore,
    verification_store: VerificationStore,
    option_id: str = "OPT-CC-001",
) -> OptionSelectionRecord:
    """Seed through READY_TO_VERIFY (Community Care path)."""
    sel = _seed_to_option_selected(
        event_store, selection_store,
        option_id=option_id,
        readiness=OptionReadiness.AUTHORIZED_NOT_VERIFIED,
        source="COMMUNITY_CARE",
    )
    route_from_option_selected(
        case_id=_CASE,
        selection_id="sel-abc123",
        idempotency_key="route-cc-001",
        event_store=event_store,
        selection_store=selection_store,
        verification_store=verification_store,
        _as_of=_T0,
    )
    return sel


def _record(
    event_store: CaseEventStore,
    verification_store: VerificationStore,
    outcome: VerificationOutcome = VerificationOutcome.VERIFIED,
    option_id: str = "OPT-CC-001",
    evidence_ref: str = "AUTH-REF-001",
    idem_key: str = "verify-result-001",
) -> VerificationResult:
    return record_verification_result(
        case_id=_CASE,
        option_id=option_id,
        source_system="COMMUNITY_CARE",
        evidence_ref=evidence_ref,
        outcome=outcome,
        actor_role=ActorRole.SCHEDULER,
        actor_id=_SCHED_ID,
        idempotency_key=idem_key,
        event_store=event_store,
        verification_store=verification_store,
        _as_of=_T0,
    )


# ===========================================================================
# Test 1–2: VA / Federal EHR fast path → VERIFIED_BOOKABLE
# ===========================================================================

class TestVAFastPath:
    """Tests 1–2: VA and Federal EHR AVAILABLE options route directly to VERIFIED_BOOKABLE."""

    @pytest.mark.parametrize("source,option_id", [
        ("VISTA_ISS", "OPT-VA-001"),
        ("FEDERAL_EHR", "OPT-FED-001"),
    ])
    def test_available_option_advances_to_verified_bookable(self, source, option_id):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, option_id=option_id, readiness=OptionReadiness.AVAILABLE, source=source)

        result = route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        assert result is not None
        assert isinstance(result, VerificationResult)
        assert result.outcome == VerificationOutcome.VERIFIED

    @pytest.mark.parametrize("source,option_id", [
        ("VISTA_ISS", "OPT-VA-001"),
        ("FEDERAL_EHR", "OPT-FED-001"),
    ])
    def test_lifecycle_advances_to_verified_bookable(self, source, option_id):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, option_id=option_id, readiness=OptionReadiness.AVAILABLE, source=source)

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        lc = es.get_lifecycle_record(_CASE)
        assert lc is not None
        assert lc.current_state == CaseLifecycleState.VERIFIED_BOOKABLE

    def test_already_verified_bookable_readiness_routes_directly(self):
        """VERIFIED_BOOKABLE readiness at selection also takes the fast path."""
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, readiness=OptionReadiness.VERIFIED_BOOKABLE)

        result = route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-vb-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        assert result is not None
        assert result.outcome == VerificationOutcome.VERIFIED
        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.VERIFIED_BOOKABLE

    def test_result_has_correct_fields(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, option_id="OPT-VA-001", readiness=OptionReadiness.AVAILABLE)

        result = route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        assert result.case_id == _CASE
        assert result.option_id == "OPT-VA-001"
        assert result.evidence_ref is None
        assert result.requires_authorization is False
        assert result.requires_human_review is False
        assert result.synthetic is True

    def test_verification_id_derived_from_key(self):
        import hashlib
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, readiness=OptionReadiness.AVAILABLE)

        result = route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        expected = "ver-" + hashlib.sha256(b"route-va-001").hexdigest()[:16]
        assert result.verification_id == expected


# ===========================================================================
# Test 3: Community Care routing → READY_TO_VERIFY (returns None)
# ===========================================================================

class TestCCRouting:
    """Test 3: Community Care AUTHORIZED_NOT_VERIFIED routes to READY_TO_VERIFY."""

    def test_cc_routing_returns_none(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(
            es, ss,
            option_id="OPT-CC-001",
            readiness=OptionReadiness.AUTHORIZED_NOT_VERIFIED,
            source="COMMUNITY_CARE",
        )

        result = route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-cc-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        assert result is None

    def test_cc_routing_lifecycle_at_ready_to_verify(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(
            es, ss,
            option_id="OPT-CC-001",
            readiness=OptionReadiness.AUTHORIZED_NOT_VERIFIED,
            source="COMMUNITY_CARE",
        )

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-cc-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.READY_TO_VERIFY

    def test_cc_routing_event_type_is_verification_required(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(
            es, ss,
            option_id="OPT-CC-001",
            readiness=OptionReadiness.AUTHORIZED_NOT_VERIFIED,
            source="COMMUNITY_CARE",
        )

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-cc-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        events = es.get_events(_CASE)
        last_evt = events[-1]
        assert last_evt.event_type == CaseEventType.VERIFICATION_REQUIRED

    def test_cc_routing_no_verification_result_stored(self):
        """No VerificationResult is created for the routing-only CC step (test 11)."""
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(
            es, ss,
            option_id="OPT-CC-001",
            readiness=OptionReadiness.AUTHORIZED_NOT_VERIFIED,
            source="COMMUNITY_CARE",
        )

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-cc-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        assert vs.get_for_case(_CASE) is None
        assert len(vs) == 0


# ===========================================================================
# Tests 4–6: record_verification_result resolutions
# ===========================================================================

class TestVerificationResolution:
    """Tests 4–6: READY_TO_VERIFY resolved by explicit evidence."""

    def test_verified_evidence_advances_to_verified_bookable(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        result = _record(es, vs, outcome=VerificationOutcome.VERIFIED)

        assert result.outcome == VerificationOutcome.VERIFIED
        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.VERIFIED_BOOKABLE

    def test_auth_required_evidence_advances_to_auth_required(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        result = _record(es, vs, outcome=VerificationOutcome.AUTH_REQUIRED)

        assert result.outcome == VerificationOutcome.AUTH_REQUIRED
        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.AUTH_REQUIRED

    def test_inconclusive_evidence_advances_to_human_review(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        result = _record(es, vs, outcome=VerificationOutcome.INCONCLUSIVE)

        assert result.outcome == VerificationOutcome.INCONCLUSIVE
        lc = es.get_lifecycle_record(_CASE)
        assert lc.current_state == CaseLifecycleState.HUMAN_REVIEW

    def test_verified_result_flags(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        result = _record(es, vs, outcome=VerificationOutcome.VERIFIED)

        assert result.requires_authorization is False
        assert result.requires_human_review is False

    def test_auth_required_result_flags(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        result = _record(es, vs, outcome=VerificationOutcome.AUTH_REQUIRED)

        assert result.requires_authorization is True
        assert result.requires_human_review is False

    def test_inconclusive_result_flags(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        result = _record(es, vs, outcome=VerificationOutcome.INCONCLUSIVE)

        assert result.requires_authorization is False
        assert result.requires_human_review is True

    def test_result_carries_evidence_ref(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        result = _record(es, vs, evidence_ref="AUTH-DOC-42")

        assert result.evidence_ref == "AUTH-DOC-42"

    @pytest.mark.parametrize("outcome,event_type", [
        (VerificationOutcome.VERIFIED, CaseEventType.VERIFICATION_PASSED),
        (VerificationOutcome.AUTH_REQUIRED, CaseEventType.VERIFICATION_FAILED),
        (VerificationOutcome.INCONCLUSIVE, CaseEventType.VERIFICATION_INCONCLUSIVE),
    ])
    def test_correct_event_type_per_outcome(self, outcome, event_type):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        _record(es, vs, outcome=outcome)

        events = es.get_events(_CASE)
        assert events[-1].event_type == event_type


# ===========================================================================
# Test 7: Wrong lifecycle state → fail closed
# ===========================================================================

class TestWrongLifecycleState:
    """Test 7: Wrong lifecycle state fails closed with no event written."""

    def test_route_wrong_state_fails(self):
        es, ss, vs = _fresh_stores()
        sel = _seed_to_option_selected(es, ss, readiness=OptionReadiness.AVAILABLE)
        # Manually advance to VERIFIED_BOOKABLE first so state is wrong
        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )
        # Now try to route again from VERIFIED_BOOKABLE (wrong state)
        with pytest.raises(ValueError, match="route_from_option_selected requires"):
            route_from_option_selected(
                case_id=_CASE, selection_id="sel-abc123",
                idempotency_key="route-va-002",
                event_store=es, selection_store=ss, verification_store=vs,
                _as_of=_T0,
            )

    def test_record_wrong_state_fails(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, readiness=OptionReadiness.AVAILABLE)
        # Case is at OPTION_SELECTED, not READY_TO_VERIFY
        with pytest.raises(ValueError, match="record_verification_result requires"):
            _record(es, vs)

    def test_wrong_state_no_extra_event(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, readiness=OptionReadiness.AVAILABLE)
        count_before = len(es.get_events(_CASE))

        with pytest.raises(ValueError):
            _record(es, vs)

        assert len(es.get_events(_CASE)) == count_before


# ===========================================================================
# Test 8: Missing lifecycle history → fail closed
# ===========================================================================

class TestMissingLifecycleHistory:
    """Test 8: Missing lifecycle history fails closed."""

    def test_route_missing_history_fails(self):
        es, ss, vs = _fresh_stores()
        # Put a selection in SelectionStore but no lifecycle events
        sel = _selection_record("sel-abc123", "OPT-VA-001", OptionReadiness.AVAILABLE)
        ss.put(sel)

        with pytest.raises(ValueError, match="no lifecycle history"):
            route_from_option_selected(
                case_id=_CASE, selection_id="sel-abc123",
                idempotency_key="route-va-001",
                event_store=es, selection_store=ss, verification_store=vs,
                _as_of=_T0,
            )

    def test_record_missing_history_fails(self):
        es, ss, vs = _fresh_stores()

        with pytest.raises(ValueError, match="no lifecycle history"):
            _record(es, vs)


# ===========================================================================
# Test 9: Unknown selection_id → fail closed
# ===========================================================================

class TestUnknownSelectionId:
    """Test 9: Unknown selection_id fails closed."""

    def test_unknown_selection_id_raises(self):
        es, ss, vs = _fresh_stores()
        # Seed lifecycle to OPTION_SELECTED but no selection record
        states = [
            (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
             CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
            (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
             CaseEventType.SEARCH_EXECUTED, "e-va"),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
             CaseEventType.OPTIONS_ASSESSED, "e-rfh"),
            (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
             CaseEventType.HANDOFF_PREPARED, "e-hr"),
            (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED,
             CaseEventType.OPTION_SELECTED, "e-os"),
        ]
        for from_s, to_s, etype, eid in states:
            es.append(CaseEvent(
                event_id=eid, case_id=_CASE, event_type=etype,
                from_state=from_s, to_state=to_s,
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                occurred_at=_T0, idempotency_key=eid,
            ))

        with pytest.raises(ValueError, match="not found in SelectionStore"):
            route_from_option_selected(
                case_id=_CASE, selection_id="sel-does-not-exist",
                idempotency_key="route-va-001",
                event_store=es, selection_store=ss, verification_store=vs,
                _as_of=_T0,
            )


# ===========================================================================
# Test 10: Readiness mismatch → fail closed
# ===========================================================================

class TestReadinessMismatch:
    """Test 10: Unsupported readiness values fail closed."""

    @pytest.mark.parametrize("bad_readiness", [
        OptionReadiness.STALE,
        OptionReadiness.UNAVAILABLE,
        OptionReadiness.AVAILABLE_NOT_AUTHORIZED,
        OptionReadiness.SOURCE_UNAVAILABLE,
    ])
    def test_bad_readiness_raises(self, bad_readiness):
        es, ss, vs = _fresh_stores()
        # Seed with this readiness — lifecycle path uses VISTA_ISS regardless
        sel = _selection_record("sel-abc123", "OPT-VA-001", bad_readiness)
        # Seed lifecycle events manually
        states = [
            (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
             CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
            (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
             CaseEventType.SEARCH_EXECUTED, "e-va"),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
             CaseEventType.OPTIONS_ASSESSED, "e-rfh"),
            (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
             CaseEventType.HANDOFF_PREPARED, "e-hr"),
            (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED,
             CaseEventType.OPTION_SELECTED, "e-os"),
        ]
        for from_s, to_s, etype, eid in states:
            es.append(CaseEvent(
                event_id=eid, case_id=_CASE, event_type=etype,
                from_state=from_s, to_state=to_s,
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                occurred_at=_T0, idempotency_key=eid,
            ))
        ss.put(sel)

        with pytest.raises(ValueError, match="cannot be routed"):
            route_from_option_selected(
                case_id=_CASE, selection_id="sel-abc123",
                idempotency_key="route-bad-001",
                event_store=es, selection_store=ss, verification_store=vs,
                _as_of=_T0,
            )

    @pytest.mark.parametrize("bad_readiness", [
        OptionReadiness.STALE,
        OptionReadiness.UNAVAILABLE,
        OptionReadiness.AVAILABLE_NOT_AUTHORIZED,
        OptionReadiness.SOURCE_UNAVAILABLE,
    ])
    def test_bad_readiness_no_event_written(self, bad_readiness):
        es, ss, vs = _fresh_stores()
        sel = _selection_record("sel-abc123", "OPT-VA-001", bad_readiness)
        states = [
            (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
             CaseEventType.WORKFLOW_GATE_EVALUATED, "e-rts"),
            (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
             CaseEventType.SEARCH_EXECUTED, "e-va"),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
             CaseEventType.OPTIONS_ASSESSED, "e-rfh"),
            (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
             CaseEventType.HANDOFF_PREPARED, "e-hr"),
            (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED,
             CaseEventType.OPTION_SELECTED, "e-os"),
        ]
        for from_s, to_s, etype, eid in states:
            es.append(CaseEvent(
                event_id=eid, case_id=_CASE, event_type=etype,
                from_state=from_s, to_state=to_s,
                actor_role=ActorRole.SCHEDULER, actor_id=_SCHED_ID,
                occurred_at=_T0, idempotency_key=eid,
            ))
        ss.put(sel)
        count_before = len(es.get_events(_CASE))

        with pytest.raises(ValueError):
            route_from_option_selected(
                case_id=_CASE, selection_id="sel-abc123",
                idempotency_key="route-bad-001",
                event_store=es, selection_store=ss, verification_store=vs,
                _as_of=_T0,
            )

        assert len(es.get_events(_CASE)) == count_before


# ===========================================================================
# Test 11: Community Care auth never upgraded without explicit evidence
# ===========================================================================

class TestCCAuthNotUpgradedWithoutEvidence:
    """Test 11: AUTHORIZED_NOT_VERIFIED routing does not upgrade auth state."""

    def test_cc_routing_does_not_set_verified_bookable(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(
            es, ss,
            option_id="OPT-CC-001",
            readiness=OptionReadiness.AUTHORIZED_NOT_VERIFIED,
            source="COMMUNITY_CARE",
        )

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-cc-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        lc = es.get_lifecycle_record(_CASE)
        # Must be READY_TO_VERIFY, never VERIFIED_BOOKABLE
        assert lc.current_state == CaseLifecycleState.READY_TO_VERIFY
        assert lc.current_state != CaseLifecycleState.VERIFIED_BOOKABLE

    def test_cc_routing_no_verification_result_until_evidence(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(
            es, ss,
            option_id="OPT-CC-001",
            readiness=OptionReadiness.AUTHORIZED_NOT_VERIFIED,
            source="COMMUNITY_CARE",
        )

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-cc-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        # After routing-only step, no VerificationResult exists
        assert vs.get_for_case(_CASE) is None


# ===========================================================================
# Test 12: Duplicate retry → idempotent (no duplicate event)
# ===========================================================================

class TestIdempotentRetry:
    """Test 12: Duplicate calls return same result without appending a new event."""

    def test_route_va_idempotent_retry(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, readiness=OptionReadiness.AVAILABLE)

        r1 = route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )
        r2 = route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        assert r1 is r2

    def test_route_va_retry_no_duplicate_event(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, readiness=OptionReadiness.AVAILABLE)

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )
        count_after_first = len(es.get_events(_CASE))
        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        assert len(es.get_events(_CASE)) == count_after_first

    def test_record_verification_idempotent_retry(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        r1 = _record(es, vs, outcome=VerificationOutcome.VERIFIED)
        r2 = _record(es, vs, outcome=VerificationOutcome.VERIFIED)

        assert r1 is r2

    def test_record_verification_retry_no_duplicate_event(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        _record(es, vs, outcome=VerificationOutcome.VERIFIED)
        count_after_first = len(es.get_events(_CASE))
        _record(es, vs, outcome=VerificationOutcome.VERIFIED)

        assert len(es.get_events(_CASE)) == count_after_first


# ===========================================================================
# Test 13: Conflicting idempotency reuse → IdempotencyConflictError
# ===========================================================================

class TestIdempotencyConflict:
    """Test 13: Same key, different material → IdempotencyConflictError."""

    def test_route_conflict_raises(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, readiness=OptionReadiness.AVAILABLE)

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        # Same key, different case_id
        with pytest.raises(IdempotencyConflictError):
            route_from_option_selected(
                case_id="DIFFERENT-CASE",
                selection_id="sel-abc123",
                idempotency_key="route-va-001",
                event_store=es, selection_store=ss, verification_store=vs,
                _as_of=_T0,
            )

    def test_record_conflict_raises(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        _record(es, vs, outcome=VerificationOutcome.VERIFIED, idem_key="verify-001")

        # Same key, different outcome
        with pytest.raises(IdempotencyConflictError):
            record_verification_result(
                case_id=_CASE,
                option_id="OPT-CC-001",
                source_system="COMMUNITY_CARE",
                evidence_ref="AUTH-REF-001",
                outcome=VerificationOutcome.AUTH_REQUIRED,  # different outcome
                actor_role=ActorRole.SCHEDULER,
                actor_id=_SCHED_ID,
                idempotency_key="verify-001",
                event_store=es,
                verification_store=vs,
                _as_of=_T0,
            )

    def test_conflict_no_event_written(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        _record(es, vs, outcome=VerificationOutcome.VERIFIED, idem_key="verify-001")
        count_before = len(es.get_events(_CASE))

        with pytest.raises(IdempotencyConflictError):
            record_verification_result(
                case_id=_CASE,
                option_id="OPT-CC-001",
                source_system="COMMUNITY_CARE",
                evidence_ref="AUTH-REF-001",
                outcome=VerificationOutcome.AUTH_REQUIRED,
                actor_role=ActorRole.SCHEDULER,
                actor_id=_SCHED_ID,
                idempotency_key="verify-001",
                event_store=es,
                verification_store=vs,
                _as_of=_T0,
            )

        assert len(es.get_events(_CASE)) == count_before


# ===========================================================================
# Test 14: Exactly one lifecycle event per successful transition
# ===========================================================================

class TestExactlyOneEventPerTransition:
    """Test 14: Each successful routing/verification adds exactly one event."""

    def test_va_fast_path_adds_one_event(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(es, ss, readiness=OptionReadiness.AVAILABLE)
        count_before = len(es.get_events(_CASE))

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-va-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        assert len(es.get_events(_CASE)) == count_before + 1

    def test_cc_routing_adds_one_event(self):
        es, ss, vs = _fresh_stores()
        _seed_to_option_selected(
            es, ss,
            option_id="OPT-CC-001",
            readiness=OptionReadiness.AUTHORIZED_NOT_VERIFIED,
            source="COMMUNITY_CARE",
        )
        count_before = len(es.get_events(_CASE))

        route_from_option_selected(
            case_id=_CASE, selection_id="sel-abc123",
            idempotency_key="route-cc-001",
            event_store=es, selection_store=ss, verification_store=vs,
            _as_of=_T0,
        )

        assert len(es.get_events(_CASE)) == count_before + 1

    def test_record_verification_adds_one_event(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)
        count_before = len(es.get_events(_CASE))

        _record(es, vs, outcome=VerificationOutcome.VERIFIED)

        assert len(es.get_events(_CASE)) == count_before + 1

    def test_complete_cc_path_has_correct_total_events(self):
        """Full CC path: 5 seed + 1 routing + 1 verification = 7 events."""
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)
        # At this point: 5 seed events + 1 routing event = 6
        assert len(es.get_events(_CASE)) == 6

        _record(es, vs, outcome=VerificationOutcome.VERIFIED)
        assert len(es.get_events(_CASE)) == 7


# ===========================================================================
# Governance / role guard tests
# ===========================================================================

class TestRoleGuard:
    """record_verification_result requires SCHEDULER; VETERAN and SYSTEM are rejected."""

    def test_veteran_role_rejected(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        with pytest.raises(ValueError, match="Only ActorRole.SCHEDULER"):
            record_verification_result(
                case_id=_CASE, option_id="OPT-CC-001",
                source_system="COMMUNITY_CARE",
                evidence_ref="AUTH-REF-001",
                outcome=VerificationOutcome.VERIFIED,
                actor_role=ActorRole.VETERAN,
                actor_id="veteran-001",
                idempotency_key="verify-001",
                event_store=es, verification_store=vs,
                _as_of=_T0,
            )

    def test_system_role_rejected(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        with pytest.raises(ValueError, match="Only ActorRole.SCHEDULER"):
            record_verification_result(
                case_id=_CASE, option_id="OPT-CC-001",
                source_system="COMMUNITY_CARE",
                evidence_ref="AUTH-REF-001",
                outcome=VerificationOutcome.VERIFIED,
                actor_role=ActorRole.SYSTEM,
                actor_id="system",
                idempotency_key="verify-001",
                event_store=es, verification_store=vs,
                _as_of=_T0,
            )


# ===========================================================================
# Evidence guard tests
# ===========================================================================

class TestEvidenceGuard:
    """evidence_ref must be non-empty for record_verification_result."""

    def test_empty_evidence_ref_rejected(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        with pytest.raises(ValueError, match="evidence_ref must be a non-empty"):
            _record(es, vs, evidence_ref="")

    def test_whitespace_only_evidence_ref_rejected(self):
        es, ss, vs = _fresh_stores()
        _seed_to_ready_to_verify(es, ss, vs)

        with pytest.raises(ValueError, match="evidence_ref must be a non-empty"):
            _record(es, vs, evidence_ref="   ")


# ===========================================================================
# VerificationStore unit tests
# ===========================================================================

class TestVerificationStore:
    """Unit tests for VerificationStore."""

    def _make_result(self, idem_key: str = "k1") -> VerificationResult:
        import hashlib
        vid = "ver-" + hashlib.sha256(idem_key.encode()).hexdigest()[:16]
        return VerificationResult(
            verification_id=vid,
            case_id=_CASE,
            option_id="OPT-VA-001",
            source_system="VISTA_ISS",
            outcome=VerificationOutcome.VERIFIED,
            evidence_ref=None,
            verified_at=_T0,
            requires_authorization=False,
            requires_human_review=False,
            idempotency_key=idem_key,
        )

    def test_put_and_get(self):
        vs = VerificationStore()
        r = self._make_result("k1")
        vs.put(r)
        assert vs.get(r.verification_id) is r

    def test_get_by_key(self):
        vs = VerificationStore()
        r = self._make_result("k1")
        vs.put(r)
        assert vs.get_by_key("k1") is r

    def test_second_put_is_no_op(self):
        vs = VerificationStore()
        r1 = self._make_result("k1")
        vs.put(r1)
        vs.put(r1)
        assert len(vs) == 1

    def test_unknown_returns_none(self):
        vs = VerificationStore()
        assert vs.get("nonexistent") is None
        assert vs.get_by_key("nonexistent") is None

    def test_get_for_case(self):
        vs = VerificationStore()
        r = self._make_result("k1")
        vs.put(r)
        assert vs.get_for_case(_CASE) is r

    def test_get_for_case_unknown(self):
        vs = VerificationStore()
        assert vs.get_for_case("UNKNOWN-CASE") is None


# ===========================================================================
# VerificationResult model tests
# ===========================================================================

class TestVerificationResultModel:
    """VerificationResult frozen dataclass invariants."""

    def test_result_is_frozen(self):
        import hashlib
        vid = "ver-" + hashlib.sha256(b"k1").hexdigest()[:16]
        r = VerificationResult(
            verification_id=vid, case_id=_CASE, option_id="OPT-VA-001",
            source_system="VISTA_ISS", outcome=VerificationOutcome.VERIFIED,
            evidence_ref=None, verified_at=_T0,
            requires_authorization=False, requires_human_review=False,
            idempotency_key="k1",
        )
        with pytest.raises((AttributeError, TypeError)):
            r.outcome = VerificationOutcome.INCONCLUSIVE  # type: ignore[misc]

    def test_result_synthetic_default_true(self):
        import hashlib
        vid = "ver-" + hashlib.sha256(b"k1").hexdigest()[:16]
        r = VerificationResult(
            verification_id=vid, case_id=_CASE, option_id="OPT-VA-001",
            source_system="VISTA_ISS", outcome=VerificationOutcome.VERIFIED,
            evidence_ref=None, verified_at=_T0,
            requires_authorization=False, requires_human_review=False,
            idempotency_key="k1",
        )
        assert r.synthetic is True
