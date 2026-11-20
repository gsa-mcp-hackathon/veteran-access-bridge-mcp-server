from __future__ import annotations

import pytest

from veteran_access_bridge.app.auth import (
    AuthorizationError,
    DemoPrincipal,
    DemoRole,
    authorize,
)
from veteran_access_bridge.app.facade import ApplicationStores, DemoApplication
from veteran_access_bridge.app.telemetry import TelemetryStore
from veteran_access_bridge.domain.models import CaseLifecycleState
from veteran_access_bridge.integrations.contracts import (
    integration_readiness_report,
)

CASE = "DEMO-CARD-5000335-001"


def app() -> DemoApplication:
    return DemoApplication(stores=ApplicationStores.fresh())


def scheduler() -> DemoPrincipal:
    return DemoPrincipal("scheduler-test", DemoRole.SCHEDULER, frozenset({CASE}))


def veteran() -> DemoPrincipal:
    return DemoPrincipal("veteran-test", DemoRole.VETERAN, frozenset({CASE}))


def test_m3_case_scope_and_role_guards() -> None:
    authorize(scheduler(), CASE, "select_option")
    authorize(veteran(), CASE, "respond_confirmation")
    with pytest.raises(AuthorizationError):
        authorize(veteran(), CASE, "select_option")
    with pytest.raises(AuthorizationError):
        authorize(scheduler(), CASE, "respond_confirmation")
    with pytest.raises(AuthorizationError):
        authorize(scheduler(), "OTHER", "view_case")


def test_m3_seeded_snapshot_reaches_human_review() -> None:
    demo = app()
    snap = demo.snapshot(CASE, include_audit=True)
    assert snap["synthetic"] is True
    assert snap["lifecycle"]["current_state"] == CaseLifecycleState.HUMAN_REVIEW.value
    assert snap["handoff"]["viable_option_count"] >= 1
    assert len(snap["audit"]) == 4


def _choose_direct_option(demo: DemoApplication) -> str:
    snap = demo.snapshot(CASE)
    for option in snap["handoff"]["options"]:
        if option["source_system"] in {"VISTA_ISS", "FEDERAL_EHR_FHIR"}:
            return option["option_id"]
    raise AssertionError("No direct VA/Federal option found")


def test_m4_direct_path_full_closed_loop_booking() -> None:
    demo = app()
    option_id = _choose_direct_option(demo)
    demo.select_option(
        case_id=CASE,
        option_id=option_id,
        actor_id="scheduler-test",
        idempotency_key="m4-select",
    )
    assert demo.snapshot(CASE)["lifecycle"]["current_state"] == "VERIFIED_BOOKABLE"

    demo.request_veteran_confirmation(case_id=CASE)
    assert (
        demo.snapshot(CASE)["lifecycle"]["current_state"]
        == "PENDING_VETERAN_CONFIRMATION"
    )

    demo.record_veteran_response(
        case_id=CASE,
        actor_id="veteran-test",
        response="CONFIRMED",
        idempotency_key="m4-confirm",
    )
    assert (
        demo.snapshot(CASE)["lifecycle"]["current_state"]
        == "PENDING_SCHEDULER_APPROVAL"
    )

    result = demo.commit_selected_booking(
        case_id=CASE,
        actor_id="scheduler-test",
        idempotency_key="m4-book",
    )
    assert result["preconditions"]["passed"] is True
    assert result["booking"]["synthetic"] is True
    assert demo.snapshot(CASE)["lifecycle"]["current_state"] == "BOOKED_SIMULATED"

    demo.record_outcome(
        case_id=CASE,
        actor_id="scheduler-test",
        event_type="APPOINTMENT_COMPLETED",
        idempotency_key="m4-complete",
    )
    assert demo.snapshot(CASE)["lifecycle"]["current_state"] == "COMPLETED"


def test_m4_veteran_change_returns_to_human_review() -> None:
    demo = app()
    option_id = _choose_direct_option(demo)
    demo.select_option(
        case_id=CASE,
        option_id=option_id,
        actor_id="scheduler-test",
        idempotency_key="change-select",
    )
    demo.request_veteran_confirmation(case_id=CASE)
    demo.record_veteran_response(
        case_id=CASE,
        actor_id="veteran-test",
        response="REQUESTED_CHANGE",
        idempotency_key="change-response",
    )
    assert demo.snapshot(CASE)["lifecycle"]["current_state"] == "HUMAN_REVIEW"


def test_m5_telemetry_is_allowlisted() -> None:
    store = TelemetryStore()
    store.record(
        action="commit_booking",
        actor_role="SCHEDULER",
        success=False,
        duration_ms=12,
        case_ref=CASE,
        metadata={
            "failure_code": "slot_unavailable",
            "patient_name": "must-not-be-recorded",
        },
    )
    event = store.events()[0]
    assert "patient_name" not in event.metadata
    assert store.summary()["measures"]["stale_or_unavailable_blocks"] == 1


def test_m6_integration_report_keeps_production_writes_disabled() -> None:
    report = integration_readiness_report()
    assert report["production_writes_enabled"] is False
    systems = {item["system"] for item in report["capabilities"]}
    assert "HSRM-style Community Care" in systems
    assert "EPS-style Community Scheduling" in systems


def test_m4_community_care_hsrm_eps_closed_loop() -> None:
    demo = app()
    snap = demo.snapshot(CASE)
    option = next(
        item
        for item in snap["handoff"]["options"]
        if item["source_system"] == "COMMUNITY_CARE_EPS"
        and item["readiness"] == "AUTHORIZED_NOT_VERIFIED"
    )

    demo.select_option(
        case_id=CASE,
        option_id=option["option_id"],
        actor_id="scheduler-test",
        idempotency_key="cc-select",
    )
    assert demo.snapshot(CASE)["lifecycle"]["current_state"] == "READY_TO_VERIFY"

    demo.verify_selected_option(
        case_id=CASE,
        actor_id="scheduler-test",
        evidence_ref="HSRM-PROV-DEMO-EPS-002",
        outcome="VERIFIED",
        idempotency_key="cc-verify",
    )
    assert demo.snapshot(CASE)["lifecycle"]["current_state"] == "VERIFIED_BOOKABLE"

    demo.request_veteran_confirmation(case_id=CASE)
    demo.record_veteran_response(
        case_id=CASE,
        actor_id="veteran-test",
        response="CONFIRMED",
        idempotency_key="cc-confirm",
    )

    result = demo.commit_selected_booking(
        case_id=CASE,
        actor_id="scheduler-test",
        idempotency_key="cc-book",
        appointment_intent="INITIAL_CONSULT",
    )
    booking = result["booking"]
    assert result["preconditions"]["hsrm_checked"] is True
    assert result["preconditions"]["eps_checked"] is True
    assert booking["authorization_id"] == "HSRM-AUTH-DEMO-EPS-002"
    assert booking["referral_id"] == "HSRM-REF-DEMO-EPS-002"
    assert booking["hsrm_provenance_ref"] == "HSRM-PROV-DEMO-EPS-002"
    assert booking["eps_provenance_ref"] == "EPS-PROV-DEMO-EPS-002"
    assert booking["source_system"] == "COMMUNITY_CARE_EPS"
    assert demo.snapshot(CASE)["lifecycle"]["current_state"] == "BOOKED_SIMULATED"


def test_m4_eps_follow_up_fails_closed() -> None:
    demo = app()
    snap = demo.snapshot(CASE)
    option = next(
        item
        for item in snap["handoff"]["options"]
        if item["source_system"] == "COMMUNITY_CARE_EPS"
        and item["readiness"] == "AUTHORIZED_NOT_VERIFIED"
    )
    demo.select_option(
        case_id=CASE,
        option_id=option["option_id"],
        actor_id="scheduler-test",
        idempotency_key="fu-select",
    )
    demo.verify_selected_option(
        case_id=CASE,
        actor_id="scheduler-test",
        evidence_ref="HSRM-PROV-DEMO-EPS-002",
        outcome="VERIFIED",
        idempotency_key="fu-verify",
    )
    demo.request_veteran_confirmation(case_id=CASE)
    demo.record_veteran_response(
        case_id=CASE,
        actor_id="veteran-test",
        response="CONFIRMED",
        idempotency_key="fu-confirm",
    )
    with pytest.raises(ValueError, match="FOLLOW_UP"):
        demo.commit_selected_booking(
            case_id=CASE,
            actor_id="scheduler-test",
            idempotency_key="fu-book",
            appointment_intent="FOLLOW_UP",
        )
    assert (
        demo.snapshot(CASE)["lifecycle"]["current_state"]
        == "PENDING_SCHEDULER_APPROVAL"
    )
