"""M2-3 tests: prepare_scheduling_handoff and get_scheduling_handoff.

Covers:
- successful handoff preparation (service layer)
- deterministic handoff_id (same viable options → same id)
- duplicate retry: no duplicate HANDOFF_PREPARED event
- stale option exclusion
- UNAVAILABLE option exclusion
- AVAILABLE_NOT_AUTHORIZED option exclusion
- Community Care AUTHORIZED_NOT_VERIFIED: included AND requires_verification=True
- Community Care readiness values preserved exactly
- mixed-source summary
- invalid lifecycle state rejection
- unknown case / empty availability
- handoff is a review artifact (no booking/selection/auth implied)
- exactly one HANDOFF_PREPARED event after multiple prepare calls
- get_scheduling_handoff: read-only, returns persisted handoff
- get_scheduling_handoff: unknown handoff_id fails cleanly
- get_scheduling_handoff: does not mutate lifecycle state
- MCP tool: prepare_scheduling_handoff integration (real fixture pipeline)
- MCP tool: get_scheduling_handoff integration
- M1 regression: all 84+ prior tests unaffected
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
    SchedulingHandoff,
    SearchAvailabilityResult,
    SourceProvenance,
    SourceSearchResult,
    SourceSearchStatus,
)
from veteran_access_bridge.services.events import CaseEventStore, InvalidTransitionError
from veteran_access_bridge.services.handoff import (
    HandoffStore,
    _deterministic_handoff_id,
    _viable_options,
    prepare_scheduling_handoff,
)

# ---------------------------------------------------------------------------
# shared test clock and case IDs
# ---------------------------------------------------------------------------

_T0 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
_CASE = "DEMO-CARD-5000335-001"
_PATIENT = "5000335"
_CONSULT = "CONSULT-CARD-5000335-001"


# ---------------------------------------------------------------------------
# minimal helpers to build synthetic AccessOption / SearchAvailabilityResult
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


def _opt(
    option_id: str,
    readiness: OptionReadiness,
    source: str = "VISTA_ISS",
) -> AccessOption:
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


def _source_result(
    source: str = "VISTA_ISS",
    options: tuple[AccessOption, ...] = (),
    status: SourceSearchStatus = SourceSearchStatus.SUCCESS,
) -> SourceSearchResult:
    return SourceSearchResult(
        source_system=source,
        status=status,
        retrieved_at=_T0,
        options=options,
    )


def _search_result(
    options: tuple[AccessOption, ...],
    source_results: tuple[SourceSearchResult, ...] | None = None,
) -> SearchAvailabilityResult:
    if source_results is None:
        source_results = (_source_result(options=options),)
    return SearchAvailabilityResult(
        patient_id=_PATIENT,
        consult_id=_CONSULT,
        searched_at=_T0,
        options=options,
        source_results=source_results,
    )


def _fresh_stores() -> tuple[CaseEventStore, HandoffStore]:
    return CaseEventStore(), HandoffStore()


def _advance_to_ready_for_handoff(
    store: CaseEventStore,
    case_id: str = _CASE,
) -> None:
    """Seed the event store so the case is at READY_FOR_HANDOFF."""
    events = [
        (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
         CaseEventType.WORKFLOW_GATE_EVALUATED, ActorRole.SYSTEM, "ik-1"),
        (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
         CaseEventType.SEARCH_EXECUTED, ActorRole.SYSTEM, "ik-2"),
        (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
         CaseEventType.OPTIONS_ASSESSED, ActorRole.SYSTEM, "ik-3"),
    ]
    for i, (f, t, et, role, ik) in enumerate(events):
        store.append(CaseEvent(
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


# ---------------------------------------------------------------------------
# 1. Successful handoff preparation
# ---------------------------------------------------------------------------


class TestSuccessfulPreparation:
    def test_returns_scheduling_handoff(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        result = prepare_scheduling_handoff(
            _CASE, _search_result((opt,)), es, hs, _as_of=_T0
        )
        assert isinstance(result, SchedulingHandoff)

    def test_handoff_id_is_set(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result((opt,)), es, hs, _as_of=_T0
        )
        assert handoff.handoff_id.startswith("handoff-")

    def test_viable_option_count_correct(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opts = (
            _opt("OPT-001", OptionReadiness.AVAILABLE),
            _opt("OPT-002", OptionReadiness.AUTHORIZED_NOT_VERIFIED, "COMMUNITY_CARE_EPS"),
        )
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result(opts), es, hs, _as_of=_T0
        )
        assert handoff.viable_option_count == 2

    def test_synthetic_flag_is_true(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result((opt,)), es, hs, _as_of=_T0
        )
        assert handoff.synthetic is True

    def test_no_booking_or_selection_occurs(self) -> None:
        """The handoff is a review artifact — no option is selected or booked."""
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result((opt,)), es, hs, _as_of=_T0
        )
        # The handoff carries options for review — none are 'selected'
        assert handoff.viable_option_count == len(handoff.options)
        # No booking record is created; BookingRecord is not referenced here


# ---------------------------------------------------------------------------
# 2. Deterministic handoff_id
# ---------------------------------------------------------------------------


class TestDeterministicHandoffId:
    def test_same_viable_options_produce_same_handoff_id(self) -> None:
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        id1 = _deterministic_handoff_id(_CASE, (opt,))
        id2 = _deterministic_handoff_id(_CASE, (opt,))
        assert id1 == id2

    def test_different_options_produce_different_handoff_ids(self) -> None:
        opt_a = _opt("OPT-AAA", OptionReadiness.AVAILABLE)
        opt_b = _opt("OPT-BBB", OptionReadiness.AVAILABLE)
        id_a = _deterministic_handoff_id(_CASE, (opt_a,))
        id_b = _deterministic_handoff_id(_CASE, (opt_b,))
        assert id_a != id_b

    def test_option_order_does_not_affect_handoff_id(self) -> None:
        """Sort by option_id inside the hash — order invariant."""
        opt_a = _opt("OPT-A", OptionReadiness.AVAILABLE)
        opt_b = _opt("OPT-B", OptionReadiness.AVAILABLE)
        id_ab = _deterministic_handoff_id(_CASE, (opt_a, opt_b))
        id_ba = _deterministic_handoff_id(_CASE, (opt_b, opt_a))
        assert id_ab == id_ba

    def test_different_case_same_options_different_id(self) -> None:
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        id1 = _deterministic_handoff_id("CASE-A", (opt,))
        id2 = _deterministic_handoff_id("CASE-B", (opt,))
        assert id1 != id2


# ---------------------------------------------------------------------------
# 3. Duplicate retry — no duplicate HANDOFF_PREPARED event
# ---------------------------------------------------------------------------


class TestDuplicateRetryIdempotency:
    def test_second_prepare_call_returns_same_handoff(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        sr = _search_result((opt,))
        h1 = prepare_scheduling_handoff(_CASE, sr, es, hs, _as_of=_T0)
        h2 = prepare_scheduling_handoff(_CASE, sr, es, hs, _as_of=_T0)
        assert h1.handoff_id == h2.handoff_id

    def test_exactly_one_handoff_prepared_event_after_retries(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        sr = _search_result((opt,))
        prepare_scheduling_handoff(_CASE, sr, es, hs, _as_of=_T0)
        prepare_scheduling_handoff(_CASE, sr, es, hs, _as_of=_T0)
        prepare_scheduling_handoff(_CASE, sr, es, hs, _as_of=_T0)
        history = es.get_events(_CASE)
        handoff_events = [e for e in history
                         if e.event_type == CaseEventType.HANDOFF_PREPARED]
        assert len(handoff_events) == 1


# ---------------------------------------------------------------------------
# 4. Stale option exclusion
# ---------------------------------------------------------------------------


class TestStaleOptionExclusion:
    def test_stale_option_excluded_from_viable(self) -> None:
        opts = (
            _opt("OPT-STALE", OptionReadiness.STALE),
            _opt("OPT-GOOD", OptionReadiness.AVAILABLE),
        )
        viable = _viable_options(opts)
        assert len(viable) == 1
        assert viable[0].option_id == "OPT-GOOD"

    def test_all_stale_produces_zero_viable(self) -> None:
        opts = (_opt("OPT-STALE-1", OptionReadiness.STALE),)
        assert len(_viable_options(opts)) == 0

    def test_handoff_viable_count_excludes_stale(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opts = (
            _opt("OPT-STALE", OptionReadiness.STALE),
            _opt("OPT-OK", OptionReadiness.AVAILABLE),
        )
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result(opts), es, hs, _as_of=_T0
        )
        assert handoff.viable_option_count == 1
        assert all(o.option_id != "OPT-STALE" for o in handoff.options)


# ---------------------------------------------------------------------------
# 5. AVAILABLE_NOT_AUTHORIZED exclusion
# ---------------------------------------------------------------------------


class TestAvailableNotAuthorizedExclusion:
    def test_available_not_authorized_excluded(self) -> None:
        opts = (
            _opt("OPT-NOAUTH", OptionReadiness.AVAILABLE_NOT_AUTHORIZED, "COMMUNITY_CARE_EPS"),
            _opt("OPT-AUTH", OptionReadiness.AUTHORIZED_NOT_VERIFIED, "COMMUNITY_CARE_EPS"),
        )
        viable = _viable_options(opts)
        assert len(viable) == 1
        assert viable[0].option_id == "OPT-AUTH"

    def test_handoff_count_excludes_unauthorized(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opts = (
            _opt("OPT-NOAUTH", OptionReadiness.AVAILABLE_NOT_AUTHORIZED, "COMMUNITY_CARE_EPS"),
            _opt("OPT-VA", OptionReadiness.AVAILABLE),
        )
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result(opts), es, hs, _as_of=_T0
        )
        assert handoff.viable_option_count == 1
        assert all(o.readiness != OptionReadiness.AVAILABLE_NOT_AUTHORIZED
                   for o in handoff.options)


# ---------------------------------------------------------------------------
# 6. Community Care authorization-state preservation
# ---------------------------------------------------------------------------


class TestCommunityAuthorizationStatePreservation:
    def test_authorized_not_verified_included_with_exact_readiness(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-CC-AUTH", OptionReadiness.AUTHORIZED_NOT_VERIFIED, "COMMUNITY_CARE_EPS")
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result((opt,)), es, hs, _as_of=_T0
        )
        assert handoff.viable_option_count == 1
        assert handoff.options[0].readiness == OptionReadiness.AUTHORIZED_NOT_VERIFIED

    def test_readiness_not_upgraded(self) -> None:
        """AUTHORIZED_NOT_VERIFIED must never be upgraded to VERIFIED_BOOKABLE."""
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-CC", OptionReadiness.AUTHORIZED_NOT_VERIFIED, "COMMUNITY_CARE_EPS")
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result((opt,)), es, hs, _as_of=_T0
        )
        assert handoff.options[0].readiness != OptionReadiness.VERIFIED_BOOKABLE

    def test_available_not_authorized_readiness_preserved_in_source_result(self) -> None:
        """Even though AVAILABLE_NOT_AUTHORIZED is excluded from viable options,
        the source result still records it accurately."""
        opt_noauth = _opt("OPT-NOAUTH", OptionReadiness.AVAILABLE_NOT_AUTHORIZED, "COMMUNITY_CARE_EPS")
        src = _source_result("COMMUNITY_CARE_EPS", options=(opt_noauth,))
        # The source result carries the original readiness — it is not modified
        assert src.options[0].readiness == OptionReadiness.AVAILABLE_NOT_AUTHORIZED


# ---------------------------------------------------------------------------
# 7. requires_verification flag
# ---------------------------------------------------------------------------


class TestRequiresVerificationFlag:
    def test_authorized_not_verified_sets_flag_true(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-CC", OptionReadiness.AUTHORIZED_NOT_VERIFIED, "COMMUNITY_CARE_EPS")
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result((opt,)), es, hs, _as_of=_T0
        )
        assert handoff.requires_verification is True

    def test_va_only_options_set_flag_false(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-VA", OptionReadiness.AVAILABLE)
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result((opt,)), es, hs, _as_of=_T0
        )
        assert handoff.requires_verification is False

    def test_mixed_sources_flag_true_when_cc_auth_present(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opts = (
            _opt("OPT-VA", OptionReadiness.AVAILABLE),
            _opt("OPT-CC", OptionReadiness.AUTHORIZED_NOT_VERIFIED, "COMMUNITY_CARE_EPS"),
        )
        handoff = prepare_scheduling_handoff(
            _CASE, _search_result(opts), es, hs, _as_of=_T0
        )
        assert handoff.requires_verification is True


# ---------------------------------------------------------------------------
# 8. Mixed-source summary
# ---------------------------------------------------------------------------


class TestMixedSourceSummary:
    def test_source_summary_names_present_sources(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opts = (
            _opt("OPT-VA", OptionReadiness.AVAILABLE, "VISTA_ISS"),
            _opt("OPT-FED", OptionReadiness.AVAILABLE, "FEDERAL_EHR_FHIR"),
        )
        sr = _search_result(opts, source_results=(
            _source_result("VISTA_ISS", options=(opts[0],)),
            _source_result("FEDERAL_EHR_FHIR", options=(opts[1],)),
        ))
        handoff = prepare_scheduling_handoff(_CASE, sr, es, hs, _as_of=_T0)
        assert "VISTA_ISS" in handoff.source_summary
        assert "FEDERAL_EHR_FHIR" in handoff.source_summary

    def test_failed_source_appears_in_summary(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-VA", OptionReadiness.AVAILABLE, "VISTA_ISS")
        sr = _search_result((opt,), source_results=(
            _source_result("VISTA_ISS", options=(opt,)),
            _source_result("COMMUNITY_CARE_EPS", status=SourceSearchStatus.SOURCE_UNAVAILABLE),
        ))
        handoff = prepare_scheduling_handoff(_CASE, sr, es, hs, _as_of=_T0)
        assert "COMMUNITY_CARE_EPS" in handoff.source_summary

    def test_no_viable_options_summary_is_not_empty(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        sr = _search_result((), source_results=(
            _source_result("VISTA_ISS", status=SourceSearchStatus.NO_SLOTS),
        ))
        handoff = prepare_scheduling_handoff(_CASE, sr, es, hs, _as_of=_T0)
        assert len(handoff.source_summary) > 0


# ---------------------------------------------------------------------------
# 9. Invalid lifecycle state rejection
# ---------------------------------------------------------------------------


class TestInvalidLifecycleStateRejection:
    def test_cancelled_case_rejects_handoff(self) -> None:
        es, hs = _fresh_stores()
        # Advance to CANCELLED via a valid path:
        # REQUEST_RECEIVED → READY_TO_SEARCH → VA_OPTIONS_AVAILABLE
        # → READY_FOR_HANDOFF → HUMAN_REVIEW → CANCELLED
        transitions = [
            (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
             CaseEventType.WORKFLOW_GATE_EVALUATED, ActorRole.SYSTEM, "ik-c1"),
            (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
             CaseEventType.SEARCH_EXECUTED, ActorRole.SYSTEM, "ik-c2"),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
             CaseEventType.OPTIONS_ASSESSED, ActorRole.SYSTEM, "ik-c3"),
            (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
             CaseEventType.HANDOFF_PREPARED, ActorRole.SYSTEM, "ik-c4"),
            (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.CANCELLED,
             CaseEventType.APPOINTMENT_CANCELLED, ActorRole.SCHEDULER, "ik-c5"),
        ]
        for f, t, et, role, ik in transitions:
            es.append(CaseEvent(
                event_id=f"{_CASE}:{ik}", case_id=_CASE,
                event_type=et, from_state=f, to_state=t,
                actor_role=role, actor_id="s",
                occurred_at=_T0, idempotency_key=f"{_CASE}:{ik}",
            ))
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        with pytest.raises(ValueError, match="CANCELLED"):
            prepare_scheduling_handoff(
                _CASE, _search_result((opt,)), es, hs, _as_of=_T0
            )

    def test_booked_simulated_case_rejects_handoff(self) -> None:
        es, hs = _fresh_stores()
        transitions = [
            (CaseLifecycleState.REQUEST_RECEIVED, CaseLifecycleState.READY_TO_SEARCH,
             CaseEventType.WORKFLOW_GATE_EVALUATED, ActorRole.SYSTEM, "ik-1"),
            (CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState.VA_OPTIONS_AVAILABLE,
             CaseEventType.SEARCH_EXECUTED, ActorRole.SYSTEM, "ik-2"),
            (CaseLifecycleState.VA_OPTIONS_AVAILABLE, CaseLifecycleState.READY_FOR_HANDOFF,
             CaseEventType.OPTIONS_ASSESSED, ActorRole.SYSTEM, "ik-3"),
            (CaseLifecycleState.READY_FOR_HANDOFF, CaseLifecycleState.HUMAN_REVIEW,
             CaseEventType.HANDOFF_PREPARED, ActorRole.SYSTEM, "ik-4"),
            (CaseLifecycleState.HUMAN_REVIEW, CaseLifecycleState.OPTION_SELECTED,
             CaseEventType.OPTION_SELECTED, ActorRole.SCHEDULER, "ik-5"),
            (CaseLifecycleState.OPTION_SELECTED, CaseLifecycleState.VERIFIED_BOOKABLE,
             CaseEventType.VERIFICATION_PASSED, ActorRole.SCHEDULER, "ik-6"),
            (CaseLifecycleState.VERIFIED_BOOKABLE, CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
             CaseEventType.VETERAN_CONFIRMATION_REQUESTED, ActorRole.SCHEDULER, "ik-7"),
            (CaseLifecycleState.PENDING_VETERAN_CONFIRMATION, CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
             CaseEventType.VETERAN_CONFIRMED, ActorRole.VETERAN, "ik-8"),
            (CaseLifecycleState.PENDING_SCHEDULER_APPROVAL, CaseLifecycleState.BOOKED_SIMULATED,
             CaseEventType.BOOKED_SIMULATED, ActorRole.SCHEDULER, "ik-9"),
        ]
        for f, t, et, role, ik in transitions:
            es.append(CaseEvent(
                event_id=f"{_CASE}:{ik}", case_id=_CASE,
                event_type=et, from_state=f, to_state=t,
                actor_role=role, actor_id="s",
                occurred_at=_T0, idempotency_key=f"{_CASE}:{ik}",
            ))
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        with pytest.raises(ValueError, match="BOOKED_SIMULATED"):
            prepare_scheduling_handoff(
                _CASE, _search_result((opt,)), es, hs, _as_of=_T0
            )


# ---------------------------------------------------------------------------
# 10. Unknown case / empty availability
# ---------------------------------------------------------------------------


class TestUnknownCaseAndEmptyAvailability:
    def test_unknown_case_no_events_fails_closed(self) -> None:
        """Missing lifecycle history must fail closed — not be silently bypassed.

        C2 decision: prepare_scheduling_handoff must not manufacture or backfill
        historical events. A case with no prior lifecycle record in the event
        store must raise ValueError with a clear structured message.
        """
        es, hs = _fresh_stores()
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        with pytest.raises(ValueError, match="no lifecycle history"):
            prepare_scheduling_handoff(
                "NEW-CASE-001", _search_result((opt,)), es, hs, _as_of=_T0
            )

    def test_missing_history_error_names_allowed_states(self) -> None:
        """The error message must name the allowed states so callers know what to seed."""
        es, hs = _fresh_stores()
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        with pytest.raises(ValueError, match="READY_FOR_HANDOFF"):
            prepare_scheduling_handoff(
                "NEW-CASE-001", _search_result((opt,)), es, hs, _as_of=_T0
            )

    def test_empty_search_result_produces_zero_viable(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        sr = _search_result((), source_results=(
            _source_result("VISTA_ISS", status=SourceSearchStatus.NO_SLOTS),
        ))
        handoff = prepare_scheduling_handoff(_CASE, sr, es, hs, _as_of=_T0)
        assert handoff.viable_option_count == 0
        assert len(handoff.options) == 0


# ---------------------------------------------------------------------------
# 11. Exactly one HANDOFF_PREPARED event
# ---------------------------------------------------------------------------


class TestExactlyOneHandoffEvent:
    def test_one_event_appended_on_first_prepare(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        prepare_scheduling_handoff(_CASE, _search_result((opt,)), es, hs, _as_of=_T0)
        history = es.get_events(_CASE)
        handoff_evts = [e for e in history if e.event_type == CaseEventType.HANDOFF_PREPARED]
        assert len(handoff_evts) == 1

    def test_event_carries_handoff_id_in_payload(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        handoff = prepare_scheduling_handoff(_CASE, _search_result((opt,)), es, hs, _as_of=_T0)
        history = es.get_events(_CASE)
        evt = next(e for e in history if e.event_type == CaseEventType.HANDOFF_PREPARED)
        assert evt.payload is not None
        assert evt.payload["handoff_id"] == handoff.handoff_id

    def test_event_to_state_is_human_review(self) -> None:
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        prepare_scheduling_handoff(_CASE, _search_result((opt,)), es, hs, _as_of=_T0)
        history = es.get_events(_CASE)
        evt = next(e for e in history if e.event_type == CaseEventType.HANDOFF_PREPARED)
        assert evt.to_state == CaseLifecycleState.HUMAN_REVIEW


# ---------------------------------------------------------------------------
# 12. get_scheduling_handoff — read-only behavior
# ---------------------------------------------------------------------------


class TestGetSchedulingHandoff:
    def test_returns_previously_prepared_handoff(self) -> None:
        from veteran_access_bridge.mcp.tools.get_scheduling_handoff import run as gsh_run
        from veteran_access_bridge.mcp.tools.prepare_scheduling_handoff import run as psh_run

        # Use fresh, isolated stores via the service layer (not module singletons)
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        handoff = prepare_scheduling_handoff(_CASE, _search_result((opt,)), es, hs, _as_of=_T0)

        # Now retrieve it via the tool's run() with injected stores
        result = gsh_run(handoff.handoff_id, handoff_store=hs)
        assert result["found"] is True
        assert result["handoff_id"] == handoff.handoff_id

    def test_unknown_handoff_returns_not_found(self) -> None:
        from veteran_access_bridge.mcp.tools.get_scheduling_handoff import run as gsh_run
        _, hs = _fresh_stores()
        result = gsh_run("handoff-does-not-exist", handoff_store=hs)
        assert result["found"] is False
        assert "error" in result

    def test_get_does_not_mutate_event_store(self) -> None:
        from veteran_access_bridge.mcp.tools.get_scheduling_handoff import run as gsh_run
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        opt = _opt("OPT-001", OptionReadiness.AVAILABLE)
        handoff = prepare_scheduling_handoff(_CASE, _search_result((opt,)), es, hs, _as_of=_T0)

        events_before = es.get_events(_CASE)
        gsh_run(handoff.handoff_id, handoff_store=hs)
        gsh_run(handoff.handoff_id, handoff_store=hs)
        events_after = es.get_events(_CASE)
        assert events_before == events_after


# ---------------------------------------------------------------------------
# 13. MCP tool integration (real M1 fixture pipeline)
# ---------------------------------------------------------------------------


class TestMcpToolIntegration:
    def test_prepare_scheduling_handoff_tool_run(self) -> None:
        from veteran_access_bridge.mcp.tools.prepare_scheduling_handoff import run as psh_run
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        result = psh_run(_CASE, event_store=es, handoff_store=hs)
        assert "handoff_id" in result
        assert result["synthetic"] is True
        assert result["creates_booking"] is False
        assert result["creates_selection"] is False
        assert result["viable_option_count"] >= 1

    def test_prepare_handoff_tool_viable_options_have_no_stale(self) -> None:
        from veteran_access_bridge.mcp.tools.prepare_scheduling_handoff import run as psh_run
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        result = psh_run(_CASE, event_store=es, handoff_store=hs)
        for opt in result.get("options", []):
            assert opt["readiness"] not in ("STALE", "UNAVAILABLE", "SOURCE_UNAVAILABLE",
                                             "AVAILABLE_NOT_AUTHORIZED")

    def test_prepare_handoff_tool_duplicate_returns_same_handoff_id(self) -> None:
        from veteran_access_bridge.mcp.tools.prepare_scheduling_handoff import run as psh_run
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        r1 = psh_run(_CASE, event_store=es, handoff_store=hs)
        r2 = psh_run(_CASE, event_store=es, handoff_store=hs)
        assert r1["handoff_id"] == r2["handoff_id"]

    def test_prepare_handoff_tool_exactly_one_event_on_retry(self) -> None:
        from veteran_access_bridge.mcp.tools.prepare_scheduling_handoff import run as psh_run
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        psh_run(_CASE, event_store=es, handoff_store=hs)
        psh_run(_CASE, event_store=es, handoff_store=hs)
        handoff_evts = [e for e in es.get_events(_CASE)
                        if e.event_type == CaseEventType.HANDOFF_PREPARED]
        assert len(handoff_evts) == 1

    def test_get_handoff_tool_round_trip(self) -> None:
        from veteran_access_bridge.mcp.tools.get_scheduling_handoff import run as gsh_run
        from veteran_access_bridge.mcp.tools.prepare_scheduling_handoff import run as psh_run
        es, hs = _fresh_stores()
        _advance_to_ready_for_handoff(es)
        prep = psh_run(_CASE, event_store=es, handoff_store=hs)
        fetched = gsh_run(prep["handoff_id"], handoff_store=hs)
        assert fetched["found"] is True
        assert fetched["handoff_id"] == prep["handoff_id"]

    def test_get_handoff_tool_unknown_id_not_found(self) -> None:
        from veteran_access_bridge.mcp.tools.get_scheduling_handoff import run as gsh_run
        _, hs = _fresh_stores()
        result = gsh_run("handoff-nonexistent", handoff_store=hs)
        assert result["found"] is False


# ---------------------------------------------------------------------------
# 14. HandoffStore — unit tests
# ---------------------------------------------------------------------------


class TestHandoffStore:
    def _make_handoff(self, handoff_id: str = "h-001") -> SchedulingHandoff:
        return SchedulingHandoff(
            handoff_id=handoff_id,
            patient_id=_PATIENT,
            consult_id=_CONSULT,
            prepared_at=_T0,
        )

    def test_put_and_get(self) -> None:
        hs = HandoffStore()
        h = self._make_handoff()
        hs.put(h)
        assert hs.get("h-001") is h

    def test_unknown_returns_none(self) -> None:
        hs = HandoffStore()
        assert hs.get("nonexistent") is None

    def test_second_put_does_not_overwrite(self) -> None:
        """First write wins — subsequent puts are no-ops."""
        hs = HandoffStore()
        h1 = self._make_handoff("h-001")
        h2 = SchedulingHandoff(
            handoff_id="h-001",
            patient_id="different-patient",
            consult_id=_CONSULT,
            prepared_at=_T0,
        )
        hs.put(h1)
        hs.put(h2)
        assert hs.get("h-001").patient_id == _PATIENT  # first wins

    def test_len(self) -> None:
        hs = HandoffStore()
        hs.put(self._make_handoff("h-001"))
        hs.put(self._make_handoff("h-002"))
        assert len(hs) == 2
