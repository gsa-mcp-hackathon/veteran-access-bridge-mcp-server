"""Observer-first room creation/dispatch regression tests.

Read-only LiveKit checks are mocked. No real LiveKit room, credentials,
agent dispatch, or production network request is used.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from veteran_access_bridge.app import asgi
from veteran_access_bridge.voice.observer_readiness import (
    ObserverRoomNotReady,
    require_observer_room_ready,
)


class FakeRoomService:
    def __init__(self, room_exists: bool = True, participants=None) -> None:
        self.room_exists = room_exists
        self.participants = participants if participants is not None else [veteran()]
        self.calls: list[str] = []

    async def list_rooms(self, request):
        self.calls.append("list_rooms")
        assert list(request.names) == ["vab-voice-123"]
        rooms = [SimpleNamespace(name="vab-voice-123")] if self.room_exists else []
        return SimpleNamespace(rooms=rooms)

    async def list_participants(self, request):
        self.calls.append("list_participants")
        assert request.room == "vab-voice-123"
        return SimpleNamespace(participants=self.participants)


class FakeDispatch:
    def __init__(self, name: str = "vab-avery"):
        self.agent_name = name


class FakeDispatchService:
    def __init__(self, dispatches=None) -> None:
        self.dispatches = dispatches if dispatches is not None else [FakeDispatch()]
        self.calls: list[str] = []

    async def list_dispatch(self, room_name: str):
        self.calls.append(room_name)
        assert room_name == "vab-voice-123"
        return self.dispatches


class FakeApi:
    def __init__(
        self,
        *,
        room_exists: bool = True,
        participants=None,
        dispatches=None,
        raise_error: bool = False,
    ) -> None:
        self.room = FakeRoomService(room_exists, participants)
        self.agent_dispatch = FakeDispatchService(dispatches)
        if raise_error:

            async def unreachable(_request):
                raise RuntimeError("provider unavailable")

            self.room.list_rooms = unreachable


def veteran(
    *,
    identity="veteran-caller-123",
    role="veteran_caller",
    case_id="DEMO-PC-5000999-001",
    voice_session_id="voice-123",
    encounter_id="SE-PC-5000999-001",
):
    return SimpleNamespace(
        identity=identity,
        metadata=json.dumps(
            {
                "vab_role": role,
                "voice_session_id": voice_session_id,
                "interaction_id": "interaction_123",
                "case_id": case_id,
                "scheduling_encounter_id": encounter_id,
            }
        ),
    )


def observer():
    return SimpleNamespace(
        identity="msa-observer-123",
        metadata=json.dumps(
            {
                "role": "msa_observer",
                "voice_session_id": "voice-123",
                "interaction_id": "interaction_123",
                "case_id": "DEMO-PC-5000999-001",
            }
        ),
    )


def check(api: FakeApi):
    return require_observer_room_ready(
        api=api,
        room_name="vab-voice-123",
        voice_session_id="voice-123",
        interaction_id="interaction_123",
        case_id="DEMO-PC-5000999-001",
        scheduling_encounter_id="SE-PC-5000999-001",
    )


@pytest.mark.asyncio
async def test_observer_cannot_create_first_room():
    api = FakeApi(room_exists=False)
    with pytest.raises(ObserverRoomNotReady, match="existing voice room"):
        await check(api)
    assert api.room.calls == ["list_rooms"]
    assert api.agent_dispatch.calls == []


@pytest.mark.asyncio
async def test_observer_only_room_is_not_eligible():
    api = FakeApi(participants=[observer()])
    with pytest.raises(ObserverRoomNotReady, match="connected"):
        await check(api)
    assert api.agent_dispatch.calls == []


@pytest.mark.asyncio
async def test_veteran_first_and_registered_avery_is_eligible():
    api = FakeApi(participants=[veteran(), observer()])
    await check(api)
    assert api.room.calls == ["list_rooms", "list_participants"]
    assert api.agent_dispatch.calls == ["vab-voice-123"]


@pytest.mark.asyncio
async def test_isolated_readiness_does_not_accept_live_dispatch(monkeypatch):
    monkeypatch.setenv("VAB_VOICE_AGENT_NAME", "vab-avery-latency-eval")
    with pytest.raises(ObserverRoomNotReady):
        await check(FakeApi())
    await check(FakeApi(dispatches=[FakeDispatch("vab-avery-latency-eval")]))


@pytest.mark.asyncio
async def test_wrong_scope_caller_and_observer_cannot_bypass_gate():
    for bad_caller in (
        veteran(case_id="OTHER-CASE"),
        veteran(encounter_id="OTHER-ENCOUNTER"),
        veteran(voice_session_id="OTHER-VOICE"),
        veteran(identity="msa-observer-disguised"),
        veteran(role="msa_observer"),
    ):
        api = FakeApi(participants=[observer(), bad_caller])
        with pytest.raises(ObserverRoomNotReady, match="connected"):
            await check(api)
        assert api.agent_dispatch.calls == []


@pytest.mark.asyncio
async def test_existing_room_without_named_avery_dispatch_is_not_eligible():
    for dispatches in ([], [FakeDispatch("other-agent")]):
        api = FakeApi(dispatches=dispatches)
        with pytest.raises(ObserverRoomNotReady, match="Avery dispatch"):
            await check(api)


@pytest.mark.asyncio
async def test_provider_failure_is_not_reinterpreted_as_success():
    api = FakeApi(raise_error=True)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await check(api)
    assert api.agent_dispatch.calls == []


class FakeLiveKitClient:
    """The production handler's context-managed SDK client, without any network."""

    def __init__(self, api, **kwargs):
        assert kwargs["url"] == "ws://127.0.0.1:7880"
        assert kwargs["api_key"] == "test-monitor"
        assert kwargs["api_secret"] == "test-monitor-secret"
        self.room = api.room
        self.agent_dispatch = api.agent_dispatch

    async def __aenter__(self):
        return self

    async def __aexit__(self, _typ, _value, _traceback):
        return None


def setup_endpoint(monkeypatch: pytest.MonkeyPatch, api: FakeApi) -> SimpleNamespace:
    case_id = "DEMO-PC-5000999-001"
    session = SimpleNamespace(
        case_id=case_id,
        interaction_id="interaction_123",
        scheduling_encounter_id="SE-PC-5000999-001",
        state=SimpleNamespace(value="CONNECTED"),
    )
    snapshot = SimpleNamespace(
        correlation=SimpleNamespace(
            case_id=case_id,
            scheduling_encounter_id="SE-PC-5000999-001",
        )
    )
    for key, value in {
        "VAB_MSA_MONITOR_ENABLED": "true",
        "VAB_MSA_MONITOR_SERVICE_KEY": "z" * 40,
        "VAB_WEBRTC_GATEWAY": "LIVEKIT",
        "VAB_WEBRTC_GATEWAY_CONFIGURED": "true",
        "VAB_WEBRTC_SIGNALING_URL": "ws://127.0.0.1:7880",
        "LIVEKIT_API_KEY": "test-monitor",
        "LIVEKIT_API_SECRET": "test-monitor-secret",
    }.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(asgi, "_require_scheduler_case", lambda _req, _case: None)
    monkeypatch.setattr(
        asgi, "VOICE_SESSIONS", SimpleNamespace(get=lambda _id: session)
    )
    monkeypatch.setattr(
        asgi, "LIVE_INTERACTIONS", SimpleNamespace(snapshot=lambda _id: snapshot)
    )
    monkeypatch.setattr(
        asgi.livekit_api,
        "LiveKitAPI",
        lambda **kwargs: FakeLiveKitClient(api, **kwargs),
    )
    return snapshot


def request_token():
    return TestClient(asgi.app, raise_server_exceptions=False).post(
        "/api/voice-sessions/voice-123/msa-monitor-token",
        headers={"authorization": "Bearer " + "z" * 40},
    )


def test_observer_endpoint_returns_409_before_veteran_connects(monkeypatch):
    setup_endpoint(monkeypatch, FakeApi(room_exists=False))
    response = request_token()
    assert response.status_code == 409
    assert response.json() == {
        "error": "voice_room_not_ready",
        "synthetic": True,
    }
    assert "participant_token" not in response.text


def test_observer_endpoint_returns_409_if_dispatch_missing(monkeypatch):
    setup_endpoint(monkeypatch, FakeApi(dispatches=[]))
    response = request_token()
    assert response.status_code == 409
    assert "participant_token" not in response.text


def test_observer_endpoint_returns_503_if_livekit_unavailable(monkeypatch):
    setup_endpoint(monkeypatch, FakeApi(raise_error=True))
    response = request_token()
    assert response.status_code == 503
    assert response.json()["error"] == "voice_room_readiness_unavailable"
    assert "participant_token" not in response.text
    assert "provider unavailable" not in response.text


def test_observer_endpoint_issues_subscribe_only_token_for_ready_room(monkeypatch):
    import jwt

    setup_endpoint(monkeypatch, FakeApi())
    response = request_token()
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["capability"] == "subscribe_only"
    claims = jwt.decode(
        data["participant_token"],
        "test-monitor-secret",
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert claims["video"]["room"] == "vab-voice-123"
    assert claims["video"]["canPublish"] is False
    assert claims["video"]["canSubscribe"] is True
    assert claims["video"]["canPublishData"] is False
    assert "roomConfig" not in claims
