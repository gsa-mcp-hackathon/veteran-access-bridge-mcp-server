import time
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from veteran_access_bridge.mcp import session_scope as scope
from veteran_access_bridge.services import crm


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,matched,interaction",
    [
        (False, "A", "call"),
        (True, None, "call"),
        (True, "B", "call"),
        (True, "A", None),
    ],
)
async def test_crm_requires_explicit_verified_call(enabled, matched, interaction):
    state = scope.SessionScope("A", matched_case=matched, interaction_id=interaction)
    invoked = []

    async def action():
        invoked.append(True)

    with scope.trusted_turn(
        state, expires=time.monotonic() + 30, crm_enabled=enabled
    ) as token:
        with pytest.raises(PermissionError):
            await scope.scoped_call(token, "record_crm_interaction", "A", action)
    assert invoked == []


@pytest.mark.asyncio
async def test_canonical_context_and_revocation(monkeypatch):
    monkeypatch.setenv("VAB_ENABLE_CRM", "true")
    state = scope.SessionScope("A", matched_case="A", interaction_id="server-call")

    async def action():
        assert crm._authorized("A", "get_crm_case") == "server-call"
        with pytest.raises(PermissionError):
            crm._authorized("B", "get_crm_case")
        with pytest.raises(PermissionError):
            crm._authorized("A", "record_crm_interaction")
        return {}

    with scope.trusted_turn(
        state, expires=time.monotonic() + 30, crm_enabled=True
    ) as token:
        await scope.scoped_call(token, "get_crm_case", "A", action)
    with pytest.raises(PermissionError):
        crm._authorized("A", "get_crm_case")
    with pytest.raises(PermissionError):
        await scope.scoped_call(token, "get_crm_case", "A", action)


@pytest.mark.parametrize(
    "payload",
    [
        {"summary": "", "disposition": "FOLLOW_UP_NEEDED"},
        {"summary": "x" * 2001, "disposition": "FOLLOW_UP_NEEDED"},
        {"summary": "yes", "disposition": "BOOKED"},
        {"summary": "yes", "disposition": "FOLLOW_UP_NEEDED", "consent": True},
    ],
)
def test_note_rejects_invalid_or_authority_fields(payload):
    with pytest.raises(ValidationError):
        crm.InteractionNote.model_validate(payload)


def test_task_requires_timezone_and_bounded_queue():
    with pytest.raises(ValidationError):
        crm.FollowUp(
            description="Call back", owner_queue="MSA", due_at="2026-11-20T10:00:00"
        )
    with pytest.raises(ValidationError):
        crm.FollowUp(
            description="Call back",
            owner_queue="external-url",
            due_at="2026-11-20T10:00:00Z",
        )
    with pytest.raises(ValidationError):
        crm.TaskUpdate(
            task_id="00000000-0000-0000-0000-000000000001",
            expected_version=1,
            status="COMPLETED",
            reason="agent says done",
        )


@pytest.fixture
def database(monkeypatch):
    monkeypatch.setenv("VAB_ENABLE_CRM", "true")
    conn = MagicMock()
    cur = MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    monkeypatch.setattr(crm, "connect_private_supabase_test_scheduling", lambda: conn)
    monkeypatch.setattr(crm, "_authorized", lambda *args: "canonical-call")
    return conn, cur


def test_note_and_audit_share_transaction(database):
    conn, cur = database
    cur.fetchone.side_effect = [(1,), None]
    result = crm.mutate(
        "A",
        "record_crm_interaction",
        {"summary": "Caller requests a callback", "disposition": "FOLLOW_UP_NEEDED"},
        "note-1",
    )
    assert result["persisted"] and not result["booking_created"]
    sql = [call.args[0] for call in cur.execute.call_args_list]
    assert any("INSERT INTO vab_test.crm_interaction" in q for q in sql)
    assert any("INSERT INTO vab_test.crm_event" in q for q in sql)
    assert not any("INSERT INTO vab_test.appointment" in q for q in sql)
    assert conn.__exit__.call_args.args[0] is None


def test_retry_returns_existing_receipt_without_new_write(database):
    _, cur = database
    data = {"summary": "Caller requests a callback", "disposition": "FOLLOW_UP_NEEDED"}
    digest = crm.hashlib.sha256(
        crm._encode({"operation": "record_crm_interaction", "data": data}).encode()
    ).hexdigest()
    cur.fetchone.side_effect = [
        (1,),
        (digest, {"persisted": True, "record_id": "saved"}),
    ]
    result = crm.mutate("A", "record_crm_interaction", data, "note-1")
    assert result["replayed"] and result["record_id"] == "saved"
    assert not any("INSERT" in c.args[0] for c in cur.execute.call_args_list)


def test_changed_retry_rolls_back(database):
    conn, cur = database
    cur.fetchone.side_effect = [(1,), ("different", {})]
    with pytest.raises(ValueError, match="different content"):
        crm.mutate(
            "A",
            "record_crm_interaction",
            {"summary": "new", "disposition": "FOLLOW_UP_NEEDED"},
            "same",
        )
    assert conn.__exit__.call_args.args[0] is ValueError


def test_stale_task_version_prevents_write(database):
    _, cur = database
    cur.fetchone.side_effect = [(1,), None, ("OPEN", 2)]
    with pytest.raises(ValueError, match="version conflict"):
        crm.mutate(
            "A",
            "update_crm_follow_up",
            {
                "task_id": "00000000-0000-0000-0000-000000000001",
                "expected_version": 1,
                "status": "IN_PROGRESS",
                "reason": "requested",
            },
            "task-1",
        )
    assert not any(
        "UPDATE" in c.args[0] and "SET status" in c.args[0]
        for c in cur.execute.call_args_list
    )


def test_revocation_before_commit_rolls_back(database, monkeypatch):
    conn, cur = database
    cur.fetchone.side_effect = [(1,), None]
    auth = MagicMock(side_effect=["canonical-call", PermissionError("expired")])
    monkeypatch.setattr(crm, "_authorized", auth)
    with pytest.raises(PermissionError):
        crm.mutate(
            "A",
            "record_crm_interaction",
            {"summary": "callback", "disposition": "FOLLOW_UP_NEEDED"},
            "note-1",
        )
    assert conn.__exit__.call_args.args[0] is PermissionError


def test_no_local_or_bearer_only_bypass(monkeypatch):
    monkeypatch.setenv("VAB_ENABLE_CRM", "true")
    connect = MagicMock()
    monkeypatch.setattr(crm, "connect_private_supabase_test_scheduling", connect)
    with pytest.raises(PermissionError):
        crm.mutate(
            "A",
            "record_crm_interaction",
            {"summary": "callback", "disposition": "FOLLOW_UP_NEEDED"},
            "note-1",
        )
    connect.assert_not_called()


@pytest.mark.asyncio
async def test_opt_in_registers_25_tools_with_scope(monkeypatch):
    from fastmcp import Client, FastMCP

    from veteran_access_bridge.mcp.tools import register_tools

    monkeypatch.setenv("VAB_ENABLE_CRM", "true")
    server = FastMCP("CRM tests")
    register_tools(server)
    async with Client(server) as client:
        tools = await client.list_tools()
        assert len(tools) == 25
        crm_tools = [tool for tool in tools if tool.name in scope.CRM_TOOLS]
        assert len(crm_tools) == 4
        for tool in crm_tools:
            assert "session_scope" in tool.inputSchema["properties"]
            assert "interaction_id" not in tool.inputSchema["properties"]
            assert "actor_id" not in tool.inputSchema["properties"]
