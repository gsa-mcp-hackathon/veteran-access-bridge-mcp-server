"""Synthetic patient roster and scoped local demo call data contracts.

No external LiveKit, Deepgram, IBM, or FHIR requests are made.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from veteran_access_bridge.app.asgi import app
from veteran_access_bridge.mcp.cases import (
    load_demo_encounter_case,
    load_demo_scheduling_context,
)
from veteran_access_bridge.mcp.voice_demo_patients import (
    list_voice_demo_patients,
    voice_demo_patient_for_case,
)


def test_seven_demo_personas_and_match_flags_are_source_properties() -> None:
    patients = list_voice_demo_patients()
    assert [patient["id"] for patient in patients] == [
        101,
        102,
        103,
        114,
        217,
        218,
        219,
    ]
    assert [p["enabled_for_patient_match"] for p in patients] == [
        False,
        False,
        False,
        False,
        True,
        True,
        True,
    ]
    assert patients[1]["case_id"] == "DEMO-PC-5000335-001"
    assert len({p["case_id"] for p in patients}) == 7
    assert all(
        "icn" not in p and "phone" not in p and "address" not in p for p in patients
    )
    assert voice_demo_patient_for_case("UNKNOWN") is None


def test_each_patient_has_a_distinct_governed_synthetic_encounter() -> None:
    for person in list_voice_demo_patients():
        case_id = person["case_id"]
        patient, consult = load_demo_encounter_case(case_id)
        request, relationship = load_demo_scheduling_context(case_id)
        assert patient.display_name == person["name"] or person["id"] == 102
        assert request.case_id == case_id
        assert relationship.patient_id == patient.patient_id
        assert consult is None
        assert request.synthetic
        assert relationship.synthetic
        if person["id"] != 102:
            assert patient.active_conditions == ()
            assert relationship.last_completed_visit is None


def test_public_endpoint_does_not_expose_the_synthetic_roster() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/demo/voice-patients")
    assert response.status_code == 404


def test_unselected_intake_is_not_a_patient_match() -> None:
    from veteran_access_bridge.mcp.tools.verify_synthetic_identity import run

    intake = "DEMO-PC-VOICE-INTAKE-001"
    patient, consult = load_demo_encounter_case(intake)
    request, relationship = load_demo_scheduling_context(intake)
    assert consult is None
    assert patient.patient_id == "UNIDENTIFIED"
    assert request.case_id == intake
    assert relationship.patient_id == "UNIDENTIFIED"
    assert not run(intake, "Not on the list", "1970-01-01")["verified"]


def test_mcp_verifies_all_seven_caller_personas_without_preselection() -> None:
    from veteran_access_bridge.mcp.tools.verify_synthetic_identity import run

    intake = "DEMO-PC-VOICE-INTAKE-001"
    for patient in list_voice_demo_patients():
        verified = run(intake, patient["name"], patient["birthdate"])
        assert verified["verified"] is True
        assert verified["matched_case_id"] == patient["case_id"]
        assert verified["patient_match_enabled"] == patient["enabled_for_patient_match"]
        assert "birth_date" not in verified
        assert "icn" not in verified
        assert "phone" not in verified
    mismatch = run(intake, "Ruben Moreno", "1949-12-29")
    assert mismatch["verified"] is False
    assert "matched_case_id" not in mismatch
    # Spoken accented surnames are normalized for the approved synthetic roster.
    assert run(intake, "Lorenzo669 Valentin837", "January 11 1942")["verified"]


def test_false_patient_match_flag_does_not_reject_verified_synthetic_identity() -> None:
    from veteran_access_bridge.mcp.tools.verify_synthetic_identity import run

    patient = next(
        patient
        for patient in list_voice_demo_patients()
        if patient["case_id"] == "DEMO-PC-P101-001"
    )

    verified = run(
        "DEMO-PC-VOICE-INTAKE-001",
        patient["name"],
        patient["birthdate"],
    )

    assert verified["verified"] is True
    assert verified["matched_case_id"] == patient["case_id"]
    assert verified["patient_match_enabled"] is False


def test_inbound_voice_case_has_backend_scheduling_encounter() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    case = "DEMO-PC-VOICE-INTAKE-001"
    response = client.get(
        "/api/scheduling-encounters/" + case,
        headers={
            "X-Demo-Role": "SCHEDULER",
            "X-Demo-Actor": "unidentified-intake-test",
            "X-Demo-Case": case,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["case_id"] == case
    assert body["scheduling_encounter_id"].startswith("SE-" + case)
    assert body["synthetic"] is True
