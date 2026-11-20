"""Tests for Issue #72 governed Primary Care calendar projection."""

from starlette.testclient import TestClient

from veteran_access_bridge.app.asgi import app
from veteran_access_bridge.app.calendar_projection import (
    CalendarSlotState,
    project_calendar_slots,
)
from veteran_access_bridge.mcp.tools.get_scheduling_encounter import run


CASE_ID = "DEMO-PC-5000999-001"


def test_primary_care_calendar_projects_governed_eligibility():
    encounter = run(CASE_ID)
    slots = project_calendar_slots(encounter)

    assert len(slots) == 3

    by_id = {slot.slot_id: slot for slot in slots}
    assert by_id["VISTA-SLOT-PC-5000999-001"].state is CalendarSlotState.ELIGIBLE
    assert by_id["FEHR-SLOT-PC-5000999-001"].state is CalendarSlotState.ELIGIBLE

    excluded = by_id["VISTA-SLOT-PC-5000999-002"]
    assert excluded.state is CalendarSlotState.EXCLUDED
    assert "PATIENT_CLASSIFICATION_MISMATCH" in excluded.eligibility_reasons
    assert "APPOINTMENT_INTENT_MISMATCH" in excluded.eligibility_reasons
    assert "TEMPLATE_MISMATCH" in excluded.eligibility_reasons


def test_comparator_and_preference_rank_are_separate_metadata():
    encounter = run(CASE_ID)
    slots = project_calendar_slots(encounter)

    comparator = next(slot for slot in slots if slot.is_access_comparator)
    assert comparator.option_id == "OPT-VISTA-SLOT-PC-5000999-001"
    assert comparator.preference_rank is not None

    eligible = [slot for slot in slots if slot.state is CalendarSlotState.ELIGIBLE]
    assert {slot.preference_rank for slot in eligible} == {1, 2}


def test_calendar_api_returns_same_governed_primary_care_projection():
    headers = {
        "X-Demo-Role": "SCHEDULER",
        "X-Demo-Actor": "msa-test",
        "X-Demo-Case": CASE_ID,
    }
    with TestClient(app) as client:
        response = client.get(
            f"/api/scheduling-encounters/{CASE_ID}",
            headers=headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == CASE_ID
    assert payload["encounter"]["patient_classification"] == "ESTABLISHED"
    assert payload["encounter"]["request"]["care_category"] == "PRIMARY_CARE"
    assert len(payload["calendar"]) == 3

    excluded = next(
        item
        for item in payload["calendar"]
        if item["slot_id"] == "VISTA-SLOT-PC-5000999-002"
    )
    assert excluded["state"] == "EXCLUDED"
    assert excluded["eligibility_reasons"]


def test_encounter_api_includes_context_projection():
    headers = {
        "X-Demo-Role": "SCHEDULER",
        "X-Demo-Actor": "msa-test",
        "X-Demo-Case": CASE_ID,
    }
    with TestClient(app) as client:
        response = client.get(
            f"/api/scheduling-encounters/{CASE_ID}",
            headers=headers,
        )

    context = response.json()["handoff"]
    assert context["care_category"] == "PRIMARY_CARE"
    assert context["scheduling_encounter_state"] == "OPTIONS_ASSEMBLED"
    assert len(context["eligible_options"]) == 2
    assert len(context["excluded_options"]) == 1
    assert context["excluded_options"][0]["reasons"]
    assert context["access_evidence"]["eligible_comparator_wait_days"] == 14
    assert context["next_permitted_action"] == "SELECT_ELIGIBLE_OPTION"
    assert context["synthetic"] is True
