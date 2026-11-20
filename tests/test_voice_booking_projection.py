from copy import deepcopy

import pytest

from veteran_access_bridge.app.voice_booking_projection import project_voice_booking


@pytest.fixture
def receipt():
    return {
        "verified": True,
        "identity_verified": True,
        "state": "BOOKED_SIMULATED",
        "booking_case_id": "VAB-DEMO-20261113-CASE-032",
        "voice_session_id": "vs-test-call",
        "begins_at": "2026-11-24T16:00:00+00:00",
        "ends_at": "2026-11-24T16:30:00+00:00",
        "appointment_id": "a312dfdf-3859-5a5b-a3b9-c8bf25141e7f",
        "patient_name": "must not reach browser",
        "token": "must not reach browser",
    }


def test_receipt_is_minimum_necessary(receipt):
    result = project_voice_booking(receipt, booked=True)
    assert result["appointment_id"] == receipt["appointment_id"]
    assert "token" not in result and "patient_name" not in result


def test_dynamic_case_receipt_preserves_verification_requirements(receipt):
    receipt["booking_case_id"] = "VAB-CALL-0db65627-0c07-59eb-87eb-89b72eb6d0b5"
    assert (
        project_voice_booking(receipt, booked=True)["appointment_id"]
        == receipt["appointment_id"]
    )
    receipt["verified"] = False
    assert project_voice_booking(receipt, booked=True) == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("verified", "true"),
        ("identity_verified", False),
        ("state", "BOOKED"),
        ("booking_case_id", "another-case"),
        ("voice_session_id", "unbound"),
        ("appointment_id", "invented"),
        ("begins_at", "2026-11-24T16:00:00"),
        ("ends_at", "2026-11-24T15:00:00+00:00"),
    ],
)
def test_invalid_receipt_is_not_projected(receipt, field, value):
    receipt[field] = value
    assert project_voice_booking(receipt, booked=True) == {}


def test_offer_does_not_project_booking_id(receipt):
    offer = deepcopy(receipt)
    offer["state"] = "OFFERED"
    result = project_voice_booking(offer, booked=False)
    assert result["state"] == "OFFERED"
    assert "appointment_id" not in result


def test_receipt_retains_clinic_without_inventing_provider(receipt):
    receipt["clinic_name"] = "Test clinic"
    result = project_voice_booking(receipt, booked=True)
    assert result["clinic_name"] == "Test clinic"
    assert "provider_name" not in result
    receipt["clinic_name"] = "Bad\nclinic"
    assert project_voice_booking(receipt, booked=True) == {}


def test_booking_note_projection_keeps_provenance_and_drops_text(receipt):
    receipt.update(
        crm_note_status="SAVED",
        crm_note_id=receipt["appointment_id"],
        crm_note_text="private",
        crm_note_origin="agent",
    )
    result = project_voice_booking(receipt, booked=True)
    assert result["crm_note_origin"] == "trusted_booking_host"
    assert result["crm_note_id"] == receipt["appointment_id"]
    assert "crm_note_text" not in result
    receipt["crm_note_id"] = "invented"
    assert "crm_note_status" not in project_voice_booking(receipt, booked=True)
    receipt["crm_note_status"] = "PENDING"
    result = project_voice_booking(receipt, booked=True)
    assert result["crm_note_status"] == "PENDING" and "crm_note_id" not in result
