import pytest

from veteran_access_bridge.app.voice_booking_projection import project_voice_options


def sample():
    return {
        "verified": True,
        "identity_verified": True,
        "booking_case_id": "VAB-DEMO-20261113-CASE-046",
        "voice_session_id": "vs-current",
        "patient_time_zone": "America/Chicago",
        "private_token": "secret",
        "options": [
            {
                "option_id": "test-option",
                "begins_at": "2026-11-25T16:00:00Z",
                "ends_at": "2026-11-25T16:30:00Z",
                "provider_name": None,
                "clinic_name": "Demo clinic",
                "private_token": "secret",
            }
        ],
    }


def test_options_never_expose_private_fields_or_invent_provider():
    result = project_voice_options(sample())
    assert "private_token" not in str(result)
    assert result["options"][0]["provider_name"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"identity_verified": False},
        {"patient_time_zone": "UTC"},
        {"voice_session_id": "other"},
        {"options": [None]},
    ],
)
def test_options_fail_closed(change):
    assert project_voice_options({**sample(), **change}) == {}


def test_duplicate_options_fail_closed():
    value = sample()
    value["options"] *= 2
    assert project_voice_options(value) == {}


def test_dynamic_case_options_preserve_binding_and_minimal_fields():
    value = sample()
    value["booking_case_id"] = "VAB-CALL-0db65627-0c07-59eb-87eb-89b72eb6d0b5"
    result = project_voice_options(value)
    assert result["booking_case_id"] == value["booking_case_id"]
    assert result["voice_session_id"] == value["voice_session_id"]
    assert len(result["options"]) == 1
    assert "private_token" not in str(result)
    assert project_voice_options({**value, "identity_verified": False}) == {}
    assert (
        project_voice_options({**value, "booking_case_id": "VAB-CALL-arbitrary"}) == {}
    )
