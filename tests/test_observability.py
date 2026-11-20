"""Acceptance tests for Issue #84 runtime observability and fail-closed behavior."""

from collections.abc import AsyncIterator

import pytest
from starlette.testclient import TestClient

import veteran_access_bridge.app.asgi as asgi_module
from veteran_access_bridge.app.live_interactions import LiveInteractionService
from veteran_access_bridge.app.primary_care_demo import PrimaryCareDemoLifecycle
from veteran_access_bridge.app.telemetry import TelemetryStore
from veteran_access_bridge.domain import InteractionChannel
from veteran_access_bridge.services import (
    OrchestrateRuntime,
    OrchestrateTimeoutError,
    RuntimeEvent,
    RuntimeInteraction,
)


CASE_ID = "DEMO-PC-5000999-001"
ENCOUNTER_ID = "SE-DEMO-PC-5000999-001-REQ-PC-5000999-001"


class TimeoutRuntime(OrchestrateRuntime):
    last_retry_count = 1

    async def start_interaction(
        self,
        *,
        interaction_id: str,
        message: str,
        session_id: str | None = None,
    ) -> RuntimeInteraction:
        raise OrchestrateTimeoutError("runtime timeout")

    async def send_message(
        self,
        *,
        interaction: RuntimeInteraction,
        message: str,
    ) -> RuntimeEvent:
        raise OrchestrateTimeoutError("runtime timeout")

    async def stream_events(
        self,
        *,
        interaction: RuntimeInteraction,
        message: str,
    ) -> AsyncIterator[RuntimeEvent]:
        if False:
            yield RuntimeEvent  # pragma: no cover
        raise OrchestrateTimeoutError("runtime timeout")


def _headers():
    return {
        "X-Demo-Role": "SCHEDULER",
        "X-Demo-Actor": "msa-observability",
        "X-Demo-Case": CASE_ID,
    }


@pytest.mark.asyncio
async def test_runtime_timeout_preserves_interaction_without_agent_success():
    service = LiveInteractionService(runtime=TimeoutRuntime())

    snapshot = await service.create_interaction(
        case_id=CASE_ID,
        scheduling_encounter_id=ENCOUNTER_ID,
        channel=InteractionChannel.PHONE,
        initial_message="I need a primary care appointment.",
    )

    assert snapshot.correlation.case_id == CASE_ID
    assert snapshot.correlation.scheduling_encounter_id == ENCOUNTER_ID
    assert snapshot.runtime_failure_code == "ORCHESTRATE_TIMEOUT"

    events = service.events.get_events(snapshot.correlation.interaction_id)
    assert events[-1].event_type.value == "human_attention_recommended"
    assert events[-1].payload == {
        "failure_code": "ORCHESTRATE_TIMEOUT",
        "recoverable": True,
        "state_preserved": True,
    }
    assert all(event.event_type.value != "agent_answered" for event in events)


def test_interaction_create_timeout_returns_correlated_503_and_safe_telemetry(
    monkeypatch,
):
    service = LiveInteractionService(runtime=TimeoutRuntime())
    telemetry = TelemetryStore()
    monkeypatch.setattr(asgi_module, "LIVE_INTERACTIONS", service)
    monkeypatch.setattr(asgi_module, "TELEMETRY", telemetry)
    monkeypatch.setattr(
        asgi_module,
        "PRIMARY_CARE_DEMO",
        PrimaryCareDemoLifecycle(),
    )

    with TestClient(asgi_module.app) as client:
        response = client.post(
            "/api/interactions",
            headers=_headers(),
            json={
                "case_id": CASE_ID,
                "scheduling_encounter_id": ENCOUNTER_ID,
                "channel": "PHONE",
                "initial_message": "I need a primary care appointment.",
            },
        )

        assert response.status_code == 503
        payload = response.json()
        assert payload["interaction_id"].startswith("int-")
        assert payload["correlation_id"].startswith("corr-")
        assert payload["runtime_failure_code"] == "ORCHESTRATE_TIMEOUT"
        assert payload["recoverable"] is True
        assert payload["state_preserved"] is True
        assert payload["orchestrate_run_id"] is None

        observed = client.get("/api/observability", headers=_headers())
        assert observed.status_code == 200
        text = observed.text
        assert "ORCHESTRATE_TIMEOUT" in text
        assert "I need a primary care appointment." not in text
        assert "bearer" not in text.lower()
        assert "tool_args" not in text

        latest = observed.json()["recent"]["events"][-1]
        assert latest["interaction_id"] == payload["interaction_id"]
        assert latest["correlation_id"] == payload["correlation_id"]
        assert latest["metadata"]["retry_count"] == 1
        assert latest["metadata"]["terminal_status"] == "RECOVERABLE_FAILURE"


def test_observability_rejects_non_scheduler_role(monkeypatch):
    monkeypatch.setattr(asgi_module, "TELEMETRY", TelemetryStore())

    with TestClient(asgi_module.app) as client:
        response = client.get(
            "/api/observability",
            headers={
                "X-Demo-Role": "VETERAN",
                "X-Demo-Actor": "veteran-demo",
                "X-Demo-Case": CASE_ID,
            },
        )

    assert response.status_code == 403


def test_telemetry_drops_message_secret_and_raw_tool_arguments():
    store = TelemetryStore()
    store.record(
        action="interaction_message",
        actor_role="SYSTEM",
        success=False,
        duration_ms=12,
        case_ref=CASE_ID,
        interaction_id="int-safe",
        correlation_id="corr-safe",
        orchestrate_run_id="run-safe",
        metadata={
            "failure_code": "MCP_UNAVAILABLE",
            "retry_count": 1,
            "terminal_status": "RECOVERABLE_FAILURE",
            "tool_outcome": "UNAVAILABLE",
            "message": "private conversation text",
            "bearer_token": "secret-token-value",
            "tool_args": {"patient_id": "do-not-store"},
        },
    )

    event = store.events()[0]
    assert event.metadata["failure_code"] == "MCP_UNAVAILABLE"
    assert event.metadata["retry_count"] == 1
    assert event.metadata["tool_outcome"] == "UNAVAILABLE"
    assert "message" not in event.metadata
    assert "bearer_token" not in event.metadata
    assert "tool_args" not in event.metadata

    serialized = str(store.operational_snapshot())
    assert "private conversation text" not in serialized
    assert "secret-token-value" not in serialized
    assert "do-not-store" not in serialized


@pytest.mark.asyncio
async def test_explicit_mcp_failure_uses_bounded_taxonomy():
    from veteran_access_bridge.services import FakeOrchestrateRuntime

    service = LiveInteractionService(runtime=FakeOrchestrateRuntime())
    snapshot = await service.create_interaction(
        case_id=CASE_ID,
        scheduling_encounter_id=ENCOUNTER_ID,
        channel=InteractionChannel.CHAT,
    )

    event = service.record_external_failure(
        interaction_id=snapshot.correlation.interaction_id,
        failure_code="MCP_UNAVAILABLE",
        tool_outcome="UNAVAILABLE",
    )

    assert event.event_type.value == "human_attention_recommended"
    assert event.payload == {
        "failure_code": "MCP_UNAVAILABLE",
        "recoverable": True,
        "state_preserved": True,
        "tool_outcome": "UNAVAILABLE",
    }
    assert (
        service.snapshot(snapshot.correlation.interaction_id).runtime_failure_code
        == "MCP_UNAVAILABLE"
    )

    with pytest.raises(ValueError):
        service.record_external_failure(
            interaction_id=snapshot.correlation.interaction_id,
            failure_code="ARBITRARY_FAILURE",
        )
