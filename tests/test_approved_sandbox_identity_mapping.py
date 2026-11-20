"""Opt-in approved VA API sandbox *synthetic export* checks: no HTTP/VA calls."""

from __future__ import annotations

import json

import pytest

from veteran_access_bridge.mcp.approved_sandbox_patients import (
    approved_sandbox_patient_for_case,
    list_approved_sandbox_patients,
)
from veteran_access_bridge.mcp.cases import (
    load_demo_encounter_case,
    load_demo_scheduling_context,
)
from veteran_access_bridge.mcp.tools.verify_synthetic_identity import run

INTAKE = "DEMO-PC-VOICE-INTAKE-001"
CASE = "DEMO-PC-SBX-TEST101-001"


def _manifest() -> dict:
    return {
        "synthetic": True,
        "source_system": "VA_API_SANDBOX_APPROVED_EXPORT",
        "patients": [
            {
                "case_id": CASE,
                "full_name": "Synthetic Sandbox Caller",
                "birth_date": "1984-07-12",
                "city": "Test City",
                "state": "KS",
                "postal_code": "66601",
                "source_record_ref": "Patient/synthetic-test-101",
                "synthetic": True,
                "approved": True,
            }
        ],
    }


def test_mapping_disabled_by_default_and_unknown_caller_stays_unverified(monkeypatch):
    monkeypatch.delenv("VAB_APPROVED_SANDBOX_PATIENTS_JSON", raising=False)
    assert list_approved_sandbox_patients() == []
    assert run(INTAKE, "Synthetic Sandbox Caller", "1984-07-12")["verified"] is False
    assert approved_sandbox_patient_for_case(CASE) is None
    with pytest.raises(ValueError, match="Unknown synthetic"):
        load_demo_encounter_case(CASE)


def test_approved_export_creates_own_case_and_requires_exact_name_plus_dob(monkeypatch):
    monkeypatch.setenv("VAB_APPROVED_SANDBOX_PATIENTS_JSON", json.dumps(_manifest()))
    identity = run(INTAKE, "Synthetic Sandbox Caller", "July 12, 1984")
    assert identity == {
        "verified": True,
        "synthetic": True,
        "case_id": INTAKE,
        "matched_case_id": CASE,
        "reason": "MATCH",
        "patient_match_enabled": True,
        "verification_source": "APPROVED_SYNTHETIC_SANDBOX_EXPORT",
    }
    assert run(INTAKE, "Synthetic Sandbox Caller", "1984-07-13")["verified"] is False
    assert run(INTAKE, "Other Name", "1984-07-12")["verified"] is False

    patient, consult = load_demo_encounter_case(CASE)
    request, relationship = load_demo_scheduling_context(CASE)
    assert consult is None
    assert patient.patient_id == "SYNTHETIC-" + CASE
    assert patient.display_name == "Synthetic Sandbox Caller"
    assert request.case_id == CASE
    assert request.synthetic is True
    assert relationship.patient_id == patient.patient_id
    assert patient.provenance[0].source_system == "VA_API_SANDBOX_APPROVED_EXPORT"
    assert patient.provenance[0].environment == "synthetic-sandbox-export"
    assert "Patient/synthetic-test-101" not in str(identity)
    assert "1984-07-12" not in str(identity)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda x: x.update(synthetic=False),
        lambda x: x.update(source_system="VA_PRODUCTION"),
        lambda x: x["patients"][0].update(approved=False),
        lambda x: x["patients"][0].update(synthetic=False),
        lambda x: x["patients"][0].update(case_id="DEMO-PC-5000999-001"),
        lambda x: x["patients"][0].update(source_record_ref="https://unknown"),
        lambda x: x["patients"][0].update(birth_date="not-a-date"),
        lambda x: x["patients"].append(dict(x["patients"][0])),
    ],
)
def test_unapproved_or_malformed_manifest_fails_closed(monkeypatch, mutate):
    raw = _manifest()
    mutate(raw)
    monkeypatch.setenv("VAB_APPROVED_SANDBOX_PATIENTS_JSON", json.dumps(raw))
    with pytest.raises(ValueError, match="mapping unavailable"):
        list_approved_sandbox_patients()
    result = run(INTAKE, "Synthetic Sandbox Caller", "1984-07-12")
    assert result["verified"] is False
    assert result["reason"] == "SANDBOX_MAPPING_UNAVAILABLE"
    assert "matched_case_id" not in result


def test_staged_export_does_not_change_existing_roster(monkeypatch):
    monkeypatch.setenv("VAB_APPROVED_SANDBOX_PATIENTS_JSON", json.dumps(_manifest()))
    assert run(
        INTAKE, "Mariano761 Ruelas156", "1907-11-20"
    )["verified"] is True
    assert approved_sandbox_patient_for_case("DEMO-PC-5000335-001") is None
