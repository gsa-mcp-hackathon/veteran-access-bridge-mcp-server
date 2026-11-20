import json
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace

import pytest

from veteran_access_bridge.services import call_patient_lookup as mod


@pytest.fixture
def patient(monkeypatch):
    monkeypatch.setenv(
        "VAB_APPROVED_VA_CASE_ICNS_JSON",
        json.dumps(
            {
                "synthetic": True,
                "cases": [
                    {"case_id": "case-A", "patient_icn": "test-icn", "approved": True}
                ],
            }
        ),
    )
    monkeypatch.setattr(
        mod, "assert_synthetic_scheduling_database", lambda *a, **k: "vab_test"
    )
    cur = SimpleNamespace(
        execute=lambda *a: None,
        fetchone=lambda: ("Test Veteran", date(1980, 1, 15), True),
    )
    conn = SimpleNamespace(cursor=lambda: nullcontext(cur))
    resource = {
        "resourceType": "Patient",
        "identifier": [{"value": "test-icn"}],
        "name": [{"given": ["Test"], "family": "Veteran"}],
        "birthDate": "1980-01-15",
    }
    bundle = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": resource}],
    }
    monkeypatch.setattr(mod, "_get_bundle", lambda *a, **k: bundle)
    return lambda: nullcontext(conn), resource, bundle


def test_va_patient_read_matches_independent_stored_demographics(patient):
    connect, _, _ = patient
    result = mod.read_patient_summary(connect, "case-A")
    assert result["identity_matches"] is True
    assert result["assigned_provider"] is None
    assert result["booking_authority"] is False
    assert "test-icn" not in str(result)
    assert "1980-01-15" not in str(result)


@pytest.mark.parametrize(
    "change",
    [
        {"birthDate": "1980-01-16"},
        {"identifier": [{"value": "different"}]},
        {"name": [{"given": ["Another"], "family": "Veteran"}]},
    ],
)
def test_va_identity_mismatch_never_verifies(patient, change):
    connect, resource, _ = patient
    resource.update(change)
    with pytest.raises(PermissionError):
        mod.read_patient_summary(connect, "case-A")


def test_unapproved_case_never_calls_va(patient, monkeypatch):
    connect, _, _ = patient
    monkeypatch.setattr(
        mod, "_get_bundle", lambda *a, **k: pytest.fail("Unapproved external read")
    )
    with pytest.raises(PermissionError):
        mod.read_patient_summary(connect, "case-B")


def test_nonunique_va_patient_never_verifies(patient):
    connect, _, bundle = patient
    bundle["entry"] *= 2
    with pytest.raises(PermissionError):
        mod.read_patient_summary(connect, "case-A")
