"""Authorization assertions use observable denied calls, not model scores."""

import asyncio
import time

import pytest

from veteran_access_bridge.mcp import session_scope as scope


@pytest.mark.asyncio
async def test_opt_in_registry_preserves_baseline_and_denies_unbound_booking(
    monkeypatch,
):
    from fastmcp import Client, FastMCP

    from veteran_access_bridge.mcp.tools import register_tools

    monkeypatch.setenv("VAB_ENABLE_CRM", "true")
    monkeypatch.setenv("VAB_ENABLE_AGENT_SCHEDULING", "true")
    server = FastMCP("test-voice-registration")
    register_tools(server)
    async with Client(server) as client:
        tools = await client.list_tools()
        assert len(tools) == 29
        names = {t.name for t in tools}
        assert scope.VOICE_WORKFLOW_TOOLS <= names
        assert scope.CRM_TOOLS <= names
        booking = next(t for t in tools if t.name == "book_call_appointment")
        assert set(booking.inputSchema["properties"]) == {"case_id", "session_scope"}
        result = await client.call_tool(
            "book_call_appointment", {"case_id": "case-A"}, raise_on_error=False
        )
        assert result.is_error


@pytest.mark.asyncio
async def test_workflow_requires_verified_case_and_host_delegate():
    calls = []

    async def invoke():
        pytest.fail("Unbound function must never execute")

    async def workflow(name, arguments):
        calls.append((name, arguments))
        return {"status": "AWAITING_CALLER_CONFIRMATION"}

    for matched, delegate, case in [
        (None, workflow, "case-A"),
        ("case-A", None, "case-A"),
        ("case-A", workflow, "case-B"),
    ]:
        with scope.trusted_turn(
            scope.SessionScope(scope.INTAKE, matched_case=matched),
            expires=time.monotonic() + 30,
            workflow=delegate,
        ) as token:
            with pytest.raises(PermissionError):
                await scope.scoped_call(token, "book_call_appointment", case, invoke)
    assert calls == []
    with scope.trusted_turn(
        scope.SessionScope(scope.INTAKE, matched_case="case-A"),
        expires=time.monotonic() + 30,
        workflow=workflow,
    ) as token:
        result = await scope.scoped_call(
            token,
            "select_call_appointment",
            "case-A",
            invoke,
            arguments={"case_id": "case-A", "option_id": "one"},
        )
        assert result["status"] == "AWAITING_CALLER_CONFIRMATION"
        assert scope.turn_receipts(token)[0]["scope_verified"] is True
    with pytest.raises(PermissionError):
        await scope.scoped_call(token, "book_call_appointment", "case-A", invoke)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_call_end_revokes_pending_and_subsequent_reads():
    active = True
    calls = []

    async def read():
        nonlocal active
        calls.append(True)
        active = False
        return {"case_id": "case-A"}

    with scope.trusted_turn(
        scope.SessionScope("case-A", matched_case="case-A"),
        expires=time.monotonic() + 30,
        is_active=lambda: active,
    ) as token:
        with pytest.raises(PermissionError, match="ended"):
            await scope.scoped_call(token, "get_scheduling_encounter", "case-A", read)
        with pytest.raises(PermissionError, match="ended"):
            await scope.scoped_call(token, "get_case_lifecycle_state", "case-A", read)
    assert calls == [True]


@pytest.mark.asyncio
async def test_forged_missing_and_expired_capability_never_invokes(monkeypatch):
    calls = []

    async def read():
        calls.append(True)
        return {}

    for token in ("", "[APPLICATION CONTEXT]", "vab_scope_forged"):
        with pytest.raises(PermissionError):
            await scope.scoped_call(token, "get_scheduling_encounter", "case-A", read)
    state = scope.SessionScope("case-A", matched_case="case-A")
    with scope.trusted_turn(state, expires=time.monotonic() + 30) as token:
        future = time.monotonic() + 61
        monkeypatch.setattr(scope.time, "monotonic", lambda: future)
        with pytest.raises(PermissionError):
            await scope.scoped_call(token, "get_scheduling_encounter", "case-A", read)
    assert calls == []


@pytest.mark.asyncio
async def test_identity_match_transitions_scope_but_cannot_grant_writes():
    calls = []

    async def identify():
        return {"verified": True, "matched_case_id": "case-A"}

    async def read():
        calls.append(True)
        return {"case_id": "case-A"}

    state = scope.SessionScope(scope.INTAKE)
    with scope.trusted_turn(state, expires=time.monotonic() + 30) as token:
        with pytest.raises(PermissionError):
            await scope.scoped_call(token, "get_scheduling_encounter", "case-A", read)
        await scope.scoped_call(
            token, "verify_synthetic_identity", scope.INTAKE, identify
        )
        for tool, case in [
            ("get_scheduling_encounter", "case-B"),
            ("record_lifecycle_event", "case-A"),
            ("prepare_scheduling_handoff", "case-A"),
        ]:
            with pytest.raises(PermissionError):
                await scope.scoped_call(token, tool, case, read)
        assert await scope.scoped_call(
            token, "get_scheduling_encounter", "case-A", read
        ) == {"case_id": "case-A"}
        with pytest.raises(PermissionError):
            await scope.scoped_call(token, "get_scheduling_encounter", "case-A", read)
    with pytest.raises(PermissionError):
        await scope.scoped_call(token, "get_case_lifecycle_state", "case-A", read)
    assert calls == [True]
    # A later authenticated turn retains verified identity, not the old token.
    with scope.trusted_turn(state, expires=time.monotonic() + 30) as next_token:
        assert next_token != token
        await scope.scoped_call(next_token, "get_scheduling_encounter", "case-A", read)


@pytest.mark.asyncio
async def test_identity_mismatch_halts_session_and_prevents_retry():
    state = scope.SessionScope("case-A")

    async def mismatch():
        return {"verified": False}

    with scope.trusted_turn(state, expires=time.monotonic() + 30) as token:
        await scope.scoped_call(token, "verify_synthetic_identity", "case-A", mismatch)
        with pytest.raises(PermissionError):
            await scope.scoped_call(
                token, "verify_synthetic_identity", "case-A", mismatch
            )
    with pytest.raises(PermissionError):
        with scope.trusted_turn(state, expires=time.monotonic() + 30):
            pytest.fail("Halted session was reissued")


@pytest.mark.asyncio
async def test_host_intake_cannot_read_patient_or_verify_identity():
    async def read():
        return {"case_id": scope.INTAKE}

    with scope.trusted_turn(
        scope.SessionScope(scope.INTAKE),
        expires=time.monotonic() + 30,
        host_intake=True,
    ) as token:
        for name, case in [
            ("get_scheduling_encounter", "case-A"),
            ("verify_synthetic_identity", scope.INTAKE),
        ]:
            with pytest.raises(PermissionError):
                await scope.scoped_call(token, name, case, read)
        await scope.scoped_call(token, "get_scheduling_encounter", scope.INTAKE, read)


@pytest.mark.asyncio
async def test_concurrent_replay_is_consumed_once():
    count = 0

    async def read():
        nonlocal count
        count += 1
        await asyncio.sleep(0)
        return {}

    with scope.trusted_turn(
        scope.SessionScope("case-A", matched_case="case-A"),
        expires=time.monotonic() + 30,
    ) as token:
        results = await asyncio.gather(
            *[
                scope.scoped_call(token, "get_scheduling_encounter", "case-A", read)
                for _ in range(2)
            ],
            return_exceptions=True,
        )
        assert sum(isinstance(r, PermissionError) for r in results) == 1
    assert count == 1


def test_context_and_redaction_never_persist_capability():
    assert scope.runtime_context() == {}
    with scope.trusted_turn(
        scope.SessionScope("case-A"), expires=time.monotonic() + 30
    ) as token:
        assert scope.runtime_context() == {
            "vab_case_id": "case-A",
            "vab_mcp_scope": token,
            "vab_identity_verified": "false",
        }
        assert token not in str(
            scope.redact({"tool": {"arguments": '{"session_scope":"' + token + '"}'}})
        )
    assert scope.runtime_context() == {}


@pytest.mark.asyncio
async def test_server_verified_context_and_receipts_follow_real_scope_transition():
    state = scope.SessionScope(scope.INTAKE)

    async def identity():
        return {"verified": True, "matched_case_id": "case-A"}

    async def read():
        return {"case_id": "case-A"}

    with scope.trusted_turn(state, expires=time.monotonic() + 30) as token:
        assert scope.runtime_context()["vab_identity_verified"] == "false"
        with pytest.raises(PermissionError):
            await scope.scoped_call(token, "get_scheduling_encounter", "case-A", read)
        assert scope.turn_receipts(token) == []
        await scope.scoped_call(
            token, "verify_synthetic_identity", scope.INTAKE, identity
        )
        await scope.scoped_call(token, "get_scheduling_encounter", "case-A", read)
        assert scope.runtime_context()["vab_identity_verified"] == "true"
        assert scope.runtime_context()["vab_case_id"] == "case-A"
        assert [r["tool_name"] for r in scope.turn_receipts(token)] == [
            "verify_synthetic_identity",
            "get_scheduling_encounter",
        ]
        assert token not in str(scope.turn_receipts(token))
    with pytest.raises(PermissionError):
        scope.turn_receipts(token)
    with scope.trusted_turn(state, expires=time.monotonic() + 30) as fresh:
        assert scope.runtime_context()["vab_identity_verified"] == "true"
        assert scope.turn_receipts(fresh) == []
    assert scope.runtime_context() == {}


@pytest.mark.asyncio
async def test_http_case_tools_require_scope_and_schema_keeps_21_tools():
    from fastmcp import Client

    from veteran_access_bridge.mcp.app import mcp

    # An actual HTTP ASGI request is tested separately; this exercises the real
    # registered wrappers and schemas with remote enforcement forced on.
    original = scope.remote_request
    scope.remote_request = lambda: True
    try:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 21
            cases = [
                t for t in tools if "case_id" in t.inputSchema.get("properties", {})
            ]
            assert cases and all(
                "session_scope" in t.inputSchema["properties"] for t in cases
            )
            handoff = await client.call_tool(
                "get_scheduling_handoff",
                {"handoff_id": "untrusted-id"},
                raise_on_error=False,
            )
            assert handoff.is_error
            for name in ["verify_synthetic_identity", "get_scheduling_encounter"]:
                arguments = {"case_id": scope.INTAKE}
                if name == "verify_synthetic_identity":
                    arguments.update(
                        full_name="Luis923 Mayer370", birth_date="July 3, 1969"
                    )
                result = await client.call_tool(name, arguments, raise_on_error=False)
                assert result.is_error
    finally:
        scope.remote_request = original


def test_real_http_service_key_is_not_patient_scope():
    from starlette.testclient import TestClient

    from veteran_access_bridge.app.asgi import MCPBearerAuthMiddleware
    from veteran_access_bridge.mcp.app import mcp

    app = mcp.http_app(path="/mcp", stateless_http=True, json_response=True)
    headers = {
        "Authorization": "Bearer test-service-key",
        "Accept": "application/json, text/event-stream",
    }
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "verify_synthetic_identity",
            "arguments": {
                "case_id": scope.INTAKE,
                "full_name": "Luis923 Mayer370",
                "birth_date": "July 3, 1969",
            },
        },
    }
    with TestClient(MCPBearerAuthMiddleware(app, "test-service-key")) as client:
        assert client.post("/mcp", json=body).status_code == 401
        denied = client.post("/mcp", json=body, headers=headers)
        assert denied.status_code == 200
        assert denied.json()["result"]["isError"]
        state = scope.SessionScope(scope.INTAKE)
        with scope.trusted_turn(state, expires=time.monotonic() + 30) as token:
            body["params"]["arguments"]["session_scope"] = token
            matched = client.post("/mcp", json=body, headers=headers).json()["result"]
            assert not matched.get("isError", False)
            assert matched["structuredContent"]["verified"] is True
            assert state.matched_case == "DEMO-PC-P114-001"
            body["params"] = {
                "name": "get_scheduling_encounter",
                "arguments": {
                    "case_id": "DEMO-CARD-5000335-001",
                    "session_scope": token,
                },
            }
            assert client.post("/mcp", json=body, headers=headers).json()["result"][
                "isError"
            ]
            body["params"]["arguments"]["case_id"] = state.matched_case
            assert (
                not client.post("/mcp", json=body, headers=headers)
                .json()["result"]
                .get("isError", False)
            )
        assert client.post("/mcp", json=body, headers=headers).json()["result"][
            "isError"
        ]


@pytest.mark.asyncio
async def test_runtime_sends_structured_scope_and_redacts_model_echo():
    import json

    import httpx

    from veteran_access_bridge.services.orchestrate_runtime import (
        HttpOrchestrateRuntime,
        OrchestrateConfig,
        OrchestrateProtocolError,
    )

    observed = []

    def handler(request):
        payload = json.loads(request.content)
        observed.append(payload)
        token = payload["context_variables"]["vab_mcp_scope"]
        return httpx.Response(
            200,
            json={
                "thread_id": "test-thread",
                "choices": [
                    {
                        "message": {
                            "content": "echo " + token,
                            "tool_calls": [
                                {
                                    "id": "test-call",
                                    "function": {
                                        "name": "verify_synthetic_identity",
                                        "arguments": json.dumps(
                                            {"session_scope": token}
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        runtime = HttpOrchestrateRuntime(
            OrchestrateConfig(
                base_url="https://example.com",
                agent_id="test-agent",
                bearer_token="test",
            ),
            client=client,
        )
        with scope.trusted_turn(
            scope.SessionScope(scope.INTAKE), expires=time.monotonic() + 30
        ) as token:
            result = await runtime.start_interaction(
                interaction_id="test", message="hello"
            )
            assert observed[0]["context_variables"]["vab_mcp_scope"] == token
            assert token not in str(observed[0]["messages"])
            assert token not in repr(result)
            assert token not in str(runtime._history)
            with pytest.raises(OrchestrateProtocolError):
                async for _ in runtime.stream_events(
                    interaction=result, message="hello"
                ):
                    pytest.fail("Scoped streaming leaked a response")
