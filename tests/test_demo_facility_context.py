import pytest

from veteran_access_bridge.services.demo_facility_context import (
    configured_facilities,
    resolve_demo_facility,
)


def test_mapping_is_explicit_and_does_not_grant_patient_assignment(monkeypatch):
    monkeypatch.setenv("VAB_DEMO_CLINIC_FACILITIES", '{"VAB-DEMO-CL-03":"vha_589A5"}')
    result = resolve_demo_facility(
        "VAB-DEMO-CL-03",
        reader=lambda fid: {
            "facility_id": fid,
            "name": "Test facility",
            "time_zone": "America/Chicago",
            "source": "VA_FACILITIES_API_SANDBOX",
            "source_verified": True,
            "patient_assignment_verified": True,
            "booking_authority": True,
        },
    )
    assert result["patient_assignment_verified"] is False
    assert result["booking_authority"] is False
    assert result["mapping_kind"] == "EXPLICIT_DEMO_INVENTORY"
    with pytest.raises(PermissionError):
        resolve_demo_facility(
            "VAB-DEMO-CL-01", reader=lambda _: pytest.fail("No lookup")
        )


@pytest.mark.parametrize(
    "raw",
    ["[]", "{}", '{"bad":"vha_688"}', '{"VAB-DEMO-CL-03":"https://evil.invalid"}'],
)
def test_invalid_config_never_silently_defaults(raw, monkeypatch):
    monkeypatch.setenv("VAB_DEMO_CLINIC_FACILITIES", raw)
    with pytest.raises(ValueError):
        configured_facilities()


@pytest.mark.parametrize(
    "changes",
    [
        {"facility_id": "vha_688"},
        {"time_zone": "UTC"},
        {"source_verified": False},
        {"source": "MODEL_TEXT"},
    ],
)
def test_facility_evidence_must_match_config(changes, monkeypatch):
    monkeypatch.setenv("VAB_DEMO_CLINIC_FACILITIES", '{"VAB-DEMO-CL-03":"vha_589A5"}')
    data = {
        "facility_id": "vha_589A5",
        "time_zone": "America/Chicago",
        "source": "VA_FACILITIES_API_SANDBOX",
        "source_verified": True,
    }
    with pytest.raises(PermissionError):
        resolve_demo_facility("VAB-DEMO-CL-03", reader=lambda _: {**data, **changes})
