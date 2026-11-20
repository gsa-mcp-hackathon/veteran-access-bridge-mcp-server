"""Fail-closed safety tests for the synthetic MSA LiveKit observer gateway.

These tests never request live tokens, connect to LiveKit, or mutate a database.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from veteran_access_bridge.app import asgi
from veteran_access_bridge.app.auth import AuthorizationError


@pytest.mark.parametrize(
    "source,exposed", [("application", True), ("watsonx_orchestrate", False)]
)
def test_scope_receipt_projection_requires_server_provenance(
    monkeypatch, source, exposed
):
    raw = {
        "event_type": "mcp_tool_result",
        "source": source,
        "payload": {
            "tool_name": "get_scheduling_encounter",
            "tool_call_id": "call-1",
            "status": "succeeded",
            "evidence": "server_scope_receipt",
            "scope_verified": True,
            "invoked_by": "agent",
            "verified_case_id": "DEMO-PC-P114-001",
            "arguments": {"session_scope": "private"},
            "result": {"patient_name": "never expose"},
        },
    }
    monkeypatch.setattr(asgi, "event_to_dict", lambda _: raw)
    payload = asgi._msa_monitor_event(object())["payload"]
    assert (payload.get("scope_verified") is True) == exposed
    assert "private" not in str(payload) and "never expose" not in str(payload)
    if exposed:
        assert payload["verified_case_id"] == "DEMO-PC-P114-001"


def test_monitor_gateway_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAB_MSA_MONITOR_ENABLED", raising=False)
    monkeypatch.delenv("VAB_MSA_MONITOR_SERVICE_KEY", raising=False)
    request = SimpleNamespace(headers={"authorization": "Bearer fake"})
    with pytest.raises(AuthorizationError, match="disabled"):
        asgi._require_msa_monitor_gateway(request, "DEMO-PC-5000999-001")


def test_monitor_gateway_rejects_spoofed_demo_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VAB_MSA_MONITOR_ENABLED", "true")
    monkeypatch.setenv("VAB_MSA_MONITOR_SERVICE_KEY", "z" * 40)
    request = SimpleNamespace(
        headers={
            "authorization": "Bearer attacker",
            "x-demo-role": "SCHEDULER",
            "x-demo-actor": "fake-msa",
            "x-demo-case": "DEMO-PC-5000999-001",
        }
    )
    with pytest.raises(AuthorizationError, match="denied"):
        asgi._require_msa_monitor_gateway(request, "DEMO-PC-5000999-001")


def test_monitor_gateway_requires_case_scope_after_service_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    monkeypatch.setenv("VAB_MSA_MONITOR_ENABLED", "true")
    monkeypatch.setenv("VAB_MSA_MONITOR_SERVICE_KEY", "z" * 40)
    monkeypatch.setattr(
        asgi, "_require_scheduler_case", lambda _request, case: called.append(case)
    )
    request = SimpleNamespace(headers={"authorization": "Bearer " + "z" * 40})
    asgi._require_msa_monitor_gateway(request, "DEMO-PC-5000999-001")
    assert called == ["DEMO-PC-5000999-001"]


def test_monitor_projection_never_exposes_transcript_or_tool_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    common = {
        "event_id": "evt-1",
        "interaction_id": "interaction-1",
        "case_id": "DEMO-PC-5000999-001",
        "scheduling_encounter_id": "SE-PC-5000999-001",
        "correlation_id": "corr-1",
        "source": "watsonx_orchestrate",
        "occurred_at": "2026-11-09T12:00:00+00:00",
        "synthetic": True,
    }

    monkeypatch.setattr(
        asgi,
        "event_to_dict",
        lambda _event: {
            **common,
            "event_type": "mcp_tool_result",
            "payload": {
                "tool_name": "get_scheduling_encounter",
                "tool_call_id": "call_123",
                "status": "completed",
                "args": {"dob": "sensitive"},
                "result": {"last_four": "sensitive"},
                "access_token": "secret",
            },
        },
    )
    projected = asgi._msa_monitor_event(object())
    assert projected["payload"] == {
        "tool_name": "get_scheduling_encounter",
        "tool_call_id": "call_123",
        "status": "completed",
    }
    assert "sensitive" not in str(projected)
    assert "secret" not in str(projected)

    monkeypatch.setattr(
        asgi,
        "event_to_dict",
        lambda _event: {
            **common,
            "event_type": "veteran_utterance",
            "payload": {"text": "Personal identity verification answer"},
        },
    )
    spoken = asgi._msa_monitor_event(object())
    assert spoken["payload"] == {"transcript_available": False}
    assert "verification answer" not in str(spoken)


def test_monitor_routes_are_registered_as_server_scoped() -> None:
    paths = {getattr(route, "path", "") for route in asgi.app.routes}
    assert "/api/voice-sessions/{voice_session_id}/msa-monitor-token" in paths
    assert "/api/interactions/{interaction_id}/msa-monitor-events" in paths


def test_observer_token_is_subscribe_only_and_voice_session_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token grants are enforced by LiveKit JWT, not by front-end button state."""
    import jwt
    from starlette.testclient import TestClient

    case = "DEMO-PC-5000999-001"
    encounter = "SE-PC-5000999-001"
    session = SimpleNamespace(
        case_id=case,
        interaction_id="interaction_123",
        scheduling_encounter_id=encounter,
        state=SimpleNamespace(value="CONNECTED"),
    )
    snapshot = SimpleNamespace(
        correlation=SimpleNamespace(case_id=case, scheduling_encounter_id=encounter)
    )
    monkeypatch.setenv("VAB_MSA_MONITOR_ENABLED", "true")
    monkeypatch.setenv("VAB_MSA_MONITOR_SERVICE_KEY", "z" * 40)
    monkeypatch.setenv("VAB_WEBRTC_GATEWAY", "LIVEKIT")
    monkeypatch.setenv("VAB_WEBRTC_GATEWAY_CONFIGURED", "true")
    monkeypatch.setenv("VAB_WEBRTC_SIGNALING_URL", "ws://127.0.0.1:7880")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-msa-monitor-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-msa-monitor-secret")
    monkeypatch.setattr(
        asgi, "VOICE_SESSIONS", SimpleNamespace(get=lambda _id: session)
    )
    monkeypatch.setattr(
        asgi, "LIVE_INTERACTIONS", SimpleNamespace(snapshot=lambda _id: snapshot)
    )
    monkeypatch.setattr(asgi, "_require_scheduler_case", lambda _req, _case: None)

    async def existing_room_ready(**_kwargs) -> None:
        pass

    # JWT grant tests must not call a real LiveKit service. Separate tests
    # exercise the authoritative room/dispatch preflight's failure modes.
    monkeypatch.setattr(asgi, "require_observer_room_ready", existing_room_ready)

    response = TestClient(asgi.app, raise_server_exceptions=False).post(
        "/api/voice-sessions/voice-123/msa-monitor-token",
        headers={"authorization": "Bearer " + "z" * 40},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["capability"] == "subscribe_only"
    assert payload["room_name"] == "vab-voice-123"
    assert payload["voice_session_id"] == "voice-123"
    assert payload["expires_in_seconds"] == 120
    claims = jwt.decode(
        payload["participant_token"],
        "test-msa-monitor-secret",
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert claims["video"]["room"] == "vab-voice-123"
    assert claims["video"]["roomJoin"] is True
    assert claims["video"]["canSubscribe"] is True
    assert claims["video"]["canPublish"] is False
    assert claims["video"]["canPublishData"] is False
    assert claims["sub"].startswith("msa-observer-")

    session.state.value = "ENDED"
    terminal = TestClient(asgi.app, raise_server_exceptions=False).post(
        "/api/voice-sessions/voice-123/msa-monitor-token",
        headers={"authorization": "Bearer " + "z" * 40},
    )
    assert terminal.status_code == 400

    session.state.value = "CONNECTED"
    snapshot.correlation.scheduling_encounter_id = "OTHER-ENCOUNTER"
    mismatch = TestClient(asgi.app, raise_server_exceptions=False).post(
        "/api/voice-sessions/voice-123/msa-monitor-token",
        headers={"authorization": "Bearer " + "z" * 40},
    )
    assert mismatch.status_code == 403


def test_ibm_tool_result_keeps_source_call_id_and_explicit_status() -> None:
    """The Command Center should match source call and result, not guess."""
    from veteran_access_bridge.services.orchestrate_runtime import (
        HttpOrchestrateRuntime,
    )

    raw = {
        "messages": [
            {
                "tool_calls": [
                    {
                        "id": "call_123",
                        "function": {
                            "name": "search_availability",
                            "arguments": "{}",
                        },
                    }
                ]
            },
            {
                "role": "tool",
                "name": "search_availability",
                "tool_call_id": "call_123",
                "status": "completed",
                "content": {"available_count": 2},
            },
        ]
    }
    activity = HttpOrchestrateRuntime._extract_tool_activity(raw)
    calls = [item for item in activity if item["phase"] == "call"]
    results = [item for item in activity if item["phase"] == "result"]
    assert len(calls) == len(results) == 1
    assert calls[0]["tool_call_id"] == results[0]["tool_call_id"] == "call_123"
    assert results[0]["status"] == "completed"


def test_canonical_mcp_result_preserves_observed_id_without_payload_leak() -> None:
    from veteran_access_bridge.app.live_interactions import LiveInteractionService
    from veteran_access_bridge.services import FakeOrchestrateRuntime

    service = LiveInteractionService(runtime=FakeOrchestrateRuntime())
    scope = SimpleNamespace(
        interaction_id="interaction_mcp_1",
        case_id="DEMO-PC-5000999-001",
        scheduling_encounter_id="SE-PC-5000999-001",
        correlation_id="corr_mcp_1",
    )
    service._append_runtime_tool_activity(
        correlation=scope,
        activity=[
            {
                "phase": "call",
                "name": "search_availability",
                "tool_call_id": "call_123",
                "arguments": {"dob": "never leak"},
            },
            {
                "phase": "result",
                "name": "search_availability",
                "tool_call_id": "call_123",
                "status": "completed",
                "result": {"private_identity": "never leak"},
            },
        ],
    )
    events = service.events.get_events(scope.interaction_id)
    projected = [asgi._msa_monitor_event(event) for event in events]
    assert [item["event_type"] for item in projected] == [
        "mcp_tool_called",
        "mcp_tool_result",
    ]
    assert {item["payload"]["tool_call_id"] for item in projected} == {"call_123"}
    assert projected[-1]["payload"]["status"] == "completed"
    assert "never leak" not in str(projected)
