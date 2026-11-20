"""Fail-closed synthetic caller activity service tests; no LiveKit or VA API calls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from veteran_access_bridge.app import asgi

SECRET = "s" * 40
CASE = "DEMO-PC-VOICE-INTAKE-001"
VOICE = "voice_123"
INTERACTION = "interaction_456"
CORRELATION = "corr_123"
ENCOUNTER = "SE_123"
PATH = f"/api/voice-sessions/{VOICE}/caller-activity-events"


def _setup(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    monkeypatch.setenv("VAB_CALL_ACTIVITY_ENABLED", "true")
    monkeypatch.setenv("VAB_CALL_ACTIVITY_SERVICE_KEY", SECRET)

    session = SimpleNamespace(
        case_id=CASE,
        voice_session_id=VOICE,
        interaction_id=INTERACTION,
        correlation_id=CORRELATION,
        scheduling_encounter_id=ENCOUNTER,
    )
    scope = SimpleNamespace(
        case_id=CASE,
        interaction_id=INTERACTION,
        correlation_id=CORRELATION,
        scheduling_encounter_id=ENCOUNTER,
    )
    snapshot = SimpleNamespace(
        correlation=scope,
        status=SimpleNamespace(value="AGENT_HANDLING"),
        human_control_mode=SimpleNamespace(value="AUTONOMOUS"),
    )
    event = SimpleNamespace(
        event_id="evt-1",
    )
    record = {
        "event_id": "evt-1",
        "event_type": "mcp_tool_result",
        "interaction_id": INTERACTION,
        "case_id": CASE,
        "scheduling_encounter_id": ENCOUNTER,
        "correlation_id": CORRELATION,
        "source": "watsonx_orchestrate",
        "occurred_at": "2026-11-11T06:00:00+00:00",
        "synthetic": True,
        "payload": {
            "tool_name": "verify_synthetic_identity",
            "tool_call_id": "call_123",
            "status": "completed",
            "args": {"birth_date": "DO_NOT_LEAK"},
            "result": {"full_name": "DO_NOT_LEAK"},
        },
    }
    monkeypatch.setattr(asgi, "VOICE_SESSIONS", SimpleNamespace(get=lambda _id: session))
    monkeypatch.setattr(
        asgi, "LIVE_INTERACTIONS",
        SimpleNamespace(
            snapshot=lambda _id: snapshot,
            events=SimpleNamespace(get_events_after=lambda _id, _cursor: [event]),
        ),
    )
    monkeypatch.setattr(asgi, "event_to_dict", lambda _event: record)
    return session


def _headers(key: str = SECRET, case: str = CASE) -> dict[str, str]:
    return {
        "authorization": "Bearer " + key,
        "x-demo-role": "SCHEDULER",
        "x-demo-actor": "trusted-caller-projection",
        "x-demo-case": case,
    }


def test_enabled_valid_scoped_caller_gets_only_sanitized_events(monkeypatch):
    _setup(monkeypatch)
    r = TestClient(asgi.app).get(PATH, headers=_headers())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["synthetic"] is True
    assert data["voice_session_id"] == VOICE
    assert data["interaction_id"] == INTERACTION
    assert data["case_id"] == CASE
    assert data["correlation_id"] == CORRELATION
    assert data["transcript_verified"] is False
    assert data["events"][0]["payload"] == {
        "tool_name": "verify_synthetic_identity",
        "tool_call_id": "call_123",
        "status": "completed",
    }
    assert "DO_NOT_LEAK" not in r.text


def test_no_public_guest_token_or_spoofed_headers_grants_backend_access(monkeypatch):
    _setup(monkeypatch)
    client = TestClient(asgi.app)
    assert client.get(PATH).status_code == 403
    assert client.get(PATH, headers=_headers("not-the-key")).status_code == 403
    assert client.get(
        PATH, headers={"x-vab-guest-session": "f" * 64, "x-demo-role": "SCHEDULER"}
    ).status_code == 403
    assert client.get(PATH, headers=_headers(case="OTHER_CASE")).status_code == 403


def test_feature_disabled_and_wrong_session_scope_fail_closed(monkeypatch):
    session = _setup(monkeypatch)
    monkeypatch.setenv("VAB_CALL_ACTIVITY_ENABLED", "false")
    client = TestClient(asgi.app)
    assert client.get(PATH, headers=_headers()).status_code == 403
    monkeypatch.setenv("VAB_CALL_ACTIVITY_ENABLED", "true")
    session.case_id = "OTHER_CASE"
    assert client.get(PATH, headers=_headers()).status_code == 403
    session.case_id = CASE
    session.correlation_id = "wrong_corr"
    assert client.get(PATH, headers=_headers()).status_code == 403


def test_cursor_is_validated_before_accessing_event_store(monkeypatch):
    _setup(monkeypatch)
    client = TestClient(asgi.app)
    assert client.get(PATH + "?cursor=%3Cscript%3E", headers=_headers()).status_code == 400


def test_route_keeps_staff_monitor_independent():
    paths = {getattr(route, "path", "") for route in asgi.app.routes}
    assert "/api/voice-sessions/{voice_session_id}/caller-activity-events" in paths
    assert "/api/voice-sessions/{voice_session_id}/msa-monitor-token" in paths
    assert "/api/interactions/{interaction_id}/msa-monitor-events" in paths


@pytest.mark.parametrize("verified", [True, False])
def test_identity_result_exposes_only_actual_boolean_verification(monkeypatch, verified):
    _setup(monkeypatch)
    original = asgi.event_to_dict

    def evidence(_event):
        raw = original(_event).copy()
        raw["payload"] = {
            "tool_name": "verify_synthetic_identity",
            "tool_call_id": "call_123",
            "status": "completed",
            "result": {
                "verified": verified,
                "full_name": "DO_NOT_LEAK",
                "birth_date": "DO_NOT_LEAK",
            },
        }
        return raw

    monkeypatch.setattr(asgi, "event_to_dict", evidence)
    response = TestClient(asgi.app).get(PATH, headers=_headers())
    assert response.status_code == 200
    projected = response.json()["events"][0]["payload"]
    assert projected["verified"] is verified
    assert projected["status"] == "completed"
    assert "full_name" not in projected
    assert "birth_date" not in projected
    assert "DO_NOT_LEAK" not in response.text


@pytest.mark.parametrize("tool_name", ["search_availability", "verify_synthetic_identity"])
def test_unknown_identity_result_never_infers_verified_from_completed(monkeypatch, tool_name):
    _setup(monkeypatch)
    original = asgi.event_to_dict

    def evidence(_event):
        raw = original(_event).copy()
        raw["payload"] = {
            "tool_name": tool_name,
            "tool_call_id": "call_123",
            "status": "completed",
            "result": {"verified": "true"},
        }
        return raw

    monkeypatch.setattr(asgi, "event_to_dict", evidence)
    response = TestClient(asgi.app).get(PATH, headers=_headers())
    assert response.status_code == 200
    projected = response.json()["events"][0]["payload"]
    assert "verified" not in projected


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ('{"verified": true, "birth_date": "SENSITIVE"}', True),
        ('{"verified": false, "birth_date": "SENSITIVE"}', False),
        (
            {"content": [{"type": "text", "text": '{"verified": true}'}]},
            True,
        ),
        ({"structuredContent": {"verified": False}}, False),
        ('{"verified": "true"}', None),
        ("Verification succeeded", None),
        ('{"verified": true, "nested": {"secret": "SENSITIVE"}}', True),
        ("x" * 5000, None),
        ({"content": [{"type": "text", "text": "not JSON"}]}, None),
        ({"content": [{"type": "text", "text": '{"verified": true}'}, {}]}, None),
    ],
)
def test_identity_json_result_is_strict_and_minimum_necessary(
    monkeypatch, result, expected
):
    _setup(monkeypatch)
    original = asgi.event_to_dict

    def identity_event(_event):
        raw = original(_event).copy()
        raw["payload"] = {
            "tool_name": "verify_synthetic_identity",
            "tool_call_id": "call_123",
            "status": "completed",
            "result": result,
        }
        return raw

    monkeypatch.setattr(asgi, "event_to_dict", identity_event)
    response = TestClient(asgi.app).get(PATH, headers=_headers())
    assert response.status_code == 200
    payload = response.json()["events"][0]["payload"]
    if expected is None:
        assert "verified" not in payload
    else:
        assert payload["verified"] is expected
    assert "SENSITIVE" not in response.text
    assert "birth_date" not in response.text
