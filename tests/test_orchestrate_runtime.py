"""Tests for Issue #79 server-side watsonx Orchestrate runtime adapter."""

import json

import httpx
import pytest

from veteran_access_bridge.services import (
    FakeOrchestrateRuntime,
    HttpOrchestrateRuntime,
    OrchestrateAuthenticationError,
    OrchestrateConfig,
    RuntimeEventType,
)


@pytest.mark.asyncio
async def test_fake_runtime_supports_local_first_multiturn():
    runtime = FakeOrchestrateRuntime()
    interaction = await runtime.start_interaction(
        interaction_id="int-001",
        message="I need a primary care appointment.",
    )
    assert interaction.run_id == "run-int-001"
    assert interaction.session_id == "thread-int-001"

    response = await runtime.send_message(
        interaction=interaction,
        message="Mornings are best.",
    )
    assert response.event_type is RuntimeEventType.MESSAGE_COMPLETED
    assert "verification" in response.payload["text"].lower()


@pytest.mark.asyncio
async def test_fake_runtime_reprompts_only_missing_verification_fields():
    runtime = FakeOrchestrateRuntime()
    interaction = await runtime.start_interaction(
        interaction_id="int-verify-001",
        message="I need to schedule a primary care appointment.",
    )
    assert "verification purposes" in (interaction.initial_response_text or "").lower()

    first_follow_up = await runtime.send_message(
        interaction=interaction,
        message="My last name is Smith and my last4 is 1234.",
    )
    assert first_follow_up.event_type is RuntimeEventType.MESSAGE_COMPLETED
    assert "date of birth" in first_follow_up.payload["text"].lower()
    assert "last4" not in first_follow_up.payload["text"].lower()
    assert "last name" not in first_follow_up.payload["text"].lower()

    second_follow_up = await runtime.send_message(
        interaction=interaction,
        message="01/15/1984",
    )
    assert "thank you for verifying your information" in second_follow_up.payload[
        "text"
    ].lower()


@pytest.mark.asyncio
async def test_http_runtime_uses_ibm_issued_thread_after_initial_request(monkeypatch):
    monkeypatch.setenv("ORCHESTRATE_THREAD_MODE", "native")
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append({
            "authorization": request.headers.get("Authorization"),
            "thread": request.headers.get("X-IBM-THREAD-ID"),
            "body": json.loads(request.content),
        })
        if len(seen) == 1:
            return httpx.Response(200, json={
                "id": "run-001",
                "thread_id": "ibm-created-thread",
                "choices": [{"message": {"content": "Welcome"}}],
            })
        if request.headers.get("X-IBM-THREAD-ID") != "ibm-created-thread":
            return httpx.Response(404, json={"error": "unknown thread"})
        return httpx.Response(200, json={
            "id": "run-002",
            "thread_id": "ibm-created-thread",
            "choices": [{"message": {"content": "Follow-up"}}],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runtime = HttpOrchestrateRuntime(
        OrchestrateConfig(
            base_url="https://example.invalid/instances/demo",
            agent_id="veteran_access_agent",
            bearer_token="server-secret-token",
        ),
        client=client,
    )
    interaction = await runtime.start_interaction(
        interaction_id="int-001", message="Hello", session_id="vab-local-id",
    )
    assert interaction.session_id == "ibm-created-thread"
    assert interaction.run_id == "run-001"
    assert seen[0]["authorization"] == "Bearer server-secret-token"
    assert seen[0]["thread"] is None
    assert seen[0]["body"]["stream"] is False
    await runtime.send_message(interaction=interaction, message="Continue")
    assert seen[1]["thread"] == "ibm-created-thread"
    await client.aclose()

@pytest.mark.asyncio
async def test_send_message_normalizes_text_response():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "run-002",
                "thread_id": "ibm-002",
                "choices": [{"message": {"content": "Morning preference captured."}}],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runtime = HttpOrchestrateRuntime(
        OrchestrateConfig(
            base_url="https://example.invalid",
            agent_id="veteran_access_agent",
            bearer_token="token",
        ),
        client=client,
    )
    interaction = await runtime.start_interaction(
        interaction_id="int-001",
        message="Start",
        session_id="thread-001",
    )
    event = await runtime.send_message(
        interaction=interaction,
        message="Mornings are best",
    )
    assert event.event_type is RuntimeEventType.MESSAGE_COMPLETED
    assert event.payload["text"] == "Morning preference captured."
    await client.aclose()


@pytest.mark.asyncio
async def test_auth_failure_is_explicit():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runtime = HttpOrchestrateRuntime(
        OrchestrateConfig(
            base_url="https://example.invalid",
            agent_id="veteran_access_agent",
            bearer_token="bad-token",
            max_retries=0,
        ),
        client=client,
    )

    with pytest.raises(OrchestrateAuthenticationError):
        await runtime.start_interaction(
            interaction_id="int-001",
            message="Hello",
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_stream_normalizes_sse_deltas_and_completion(monkeypatch):
    monkeypatch.setenv("ORCHESTRATE_THREAD_MODE", "native")
    body = (
        'data: {"id":"run-001","choices":[{"delta":{"content":"Hello"}}]}\n\n'
        'data: {"id":"run-001","choices":[{"delta":{"content":" Veteran"}}]}\n\n'
        'data: [DONE]\n\n'
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["stream"] is False:
            return httpx.Response(
                200,
                json={
                    "id": "run-001",
                    "thread_id": "ibm-stream",
                    "choices": [{"message": {"content": "Started"}}],
                },
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body.encode(),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runtime = HttpOrchestrateRuntime(
        OrchestrateConfig(
            base_url="https://example.invalid",
            agent_id="veteran_access_agent",
            bearer_token="token",
        ),
        client=client,
    )

    interaction = await runtime.start_interaction(
        interaction_id="int-001",
        message="Start",
        session_id="thread-001",
    )
    events = [
        event
        async for event in runtime.stream_events(
            interaction=interaction,
            message="Continue",
        )
    ]
    assert [event.event_type for event in events] == [
        RuntimeEventType.RUN_STARTED,
        RuntimeEventType.MESSAGE_DELTA,
        RuntimeEventType.MESSAGE_DELTA,
        RuntimeEventType.RUN_COMPLETED,
    ]
    assert events[1].payload["text"] == "Hello"
    assert events[2].payload["text"] == " Veteran"
    await client.aclose()


def test_config_builds_configurable_chat_url():
    config = OrchestrateConfig(
        base_url="https://example.invalid/instances/demo/",
        agent_id="veteran_access_agent",
        bearer_token="token",
        chat_path="/v1/orchestrate/{agent_id}/chat/completions",
    )
    assert config.chat_url == (
        "https://example.invalid/instances/demo"
        "/v1/orchestrate/veteran_access_agent/chat/completions"
    )


@pytest.mark.asyncio
async def test_http_runtime_exchanges_api_key_for_iam_token_and_caches_it():
    seen = {"iam_calls": 0, "chat_calls": 0, "authorization": []}

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://iam.cloud.ibm.com/identity/token":
            seen["iam_calls"] += 1
            body = request.content.decode()
            assert "grant_type=urn%3Aibm%3Aparams%3Aoauth%3Agrant-type%3Aapikey" in body
            assert "apikey=server-api-key" in body
            return httpx.Response(
                200,
                json={
                    "access_token": "iam-access-token",
                    "expires_in": 3600,
                },
            )

        seen["chat_calls"] += 1
        seen["authorization"].append(request.headers.get("Authorization"))
        return httpx.Response(
            200,
            json={
                "id": f"run-{seen['chat_calls']}",
                "thread_id": "ibm-iam",
                "choices": [{"message": {"content": "ok"}}],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runtime = HttpOrchestrateRuntime(
        OrchestrateConfig(
            base_url="https://example.invalid/instances/demo",
            agent_id="89801bbc-fa87-41f9-b9d7-d2a9b4cbf0c3",
            api_key="server-api-key",
            max_retries=1,
        ),
        client=client,
    )

    interaction = await runtime.start_interaction(
        interaction_id="int-iam",
        message="I need primary care",
        session_id="thread-iam",
    )
    await runtime.send_message(
        interaction=interaction,
        message="Mornings are best",
    )

    assert seen["iam_calls"] == 1
    assert seen["chat_calls"] == 2
    assert seen["authorization"] == [
        "Bearer iam-access-token",
        "Bearer iam-access-token",
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_http_runtime_refreshes_iam_token_after_orchestrate_401():
    seen = {"iam_calls": 0, "chat_calls": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://iam.cloud.ibm.com/identity/token":
            seen["iam_calls"] += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"iam-token-{seen['iam_calls']}",
                    "expires_in": 3600,
                },
            )

        seen["chat_calls"] += 1
        if seen["chat_calls"] == 1:
            assert request.headers["Authorization"] == "Bearer iam-token-1"
            return httpx.Response(401, json={"error": "expired"})
        assert request.headers["Authorization"] == "Bearer iam-token-2"
        return httpx.Response(
            200,
            json={
                "id": "run-refreshed",
                "thread_id": "ibm-refreshed",
                "choices": [{"message": {"content": "ok"}}],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runtime = HttpOrchestrateRuntime(
        OrchestrateConfig(
            base_url="https://example.invalid/instances/demo",
            agent_id="89801bbc-fa87-41f9-b9d7-d2a9b4cbf0c3",
            api_key="server-api-key",
            max_retries=1,
        ),
        client=client,
    )

    interaction = await runtime.start_interaction(
        interaction_id="int-refresh",
        message="Hello",
    )

    assert interaction.run_id == "run-refreshed"
    assert seen["iam_calls"] == 2
    assert seen["chat_calls"] == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_history_replay_preserves_turns_without_ibm_thread_header(monkeypatch):
    monkeypatch.setenv("ORCHESTRATE_THREAD_MODE", "history")
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-IBM-THREAD-ID") is None
        messages = json.loads(request.content)["messages"]
        seen.append(messages)
        if len(messages) == 1:
            return httpx.Response(200, json={
                "thread_id": "ibm-thread-1", "run_id": "run-1",
                "choices": [{"message": {"content": "What time do you prefer?"}}],
            })
        assert [m["role"] for m in messages] == ["user", "assistant", "user"]
        assert "morning" in messages[-1]["content"]
        return httpx.Response(200, json={
            "thread_id": "ibm-thread-2", "run_id": "run-2",
            "choices": [{"message": {"content": "Morning preference noted."}}],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    runtime = HttpOrchestrateRuntime(
        OrchestrateConfig(base_url="https://example.invalid", agent_id="avery",
                          bearer_token="token"), client=client,
    )
    interaction = await runtime.start_interaction(
        interaction_id="int-replay", message="I need a primary care appointment.",
    )
    event = await runtime.send_message(
        interaction=interaction, message="I prefer morning appointments.",
    )
    assert len(seen) == 2
    assert interaction.session_id == "ibm-thread-1"
    assert event.payload["text"] == "Morning preference noted."
    assert len(runtime._history["int-replay"]) == 4
    await client.aclose()
