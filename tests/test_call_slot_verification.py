from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from veteran_access_bridge.services import call_slot_verification as mod


@pytest.fixture
def inventory(monkeypatch):
    monkeypatch.setenv("VAB_ENABLE_AGENT_SCHEDULING", "true")
    monkeypatch.setattr(
        mod, "assert_synthetic_scheduling_database", lambda *a, **k: "vab_test"
    )
    now = datetime.now(timezone.utc)
    identity = SimpleNamespace(
        verified=True,
        expires_at=now + timedelta(minutes=2),
        event_id=uuid4(),
        correlation_id="vs-test",
        case_id="case-A",
        patient_id=uuid4(),
    )
    queries = []
    replies = [(1,), (uuid4(),), (now,)]
    cur = SimpleNamespace(
        execute=lambda sql, *a: queries.append(sql), fetchone=lambda: replies.pop(0)
    )
    conn = SimpleNamespace(cursor=lambda: nullcontext(cur))

    def check():
        return mod.verify_test_inventory(
            lambda: nullcontext(conn),
            identity=identity,
            slot_id=uuid4(),
            option_id="one",
            host_subject="test-host",
        )

    return check, identity, queries, replies


def test_recheck_records_actual_test_source_and_locked_slot(inventory):
    check, _, queries, _ = inventory
    assert check().tzinfo is not None
    assert any("FOR UPDATE OF s" in q for q in queries)
    assert sum(q.startswith("UPDATE") for q in queries) == 1
    assert any("SYNTHETIC_SLOT_SOURCE_RECHECKED" in q for q in queries)


@pytest.mark.parametrize("missing", [0, 1])
def test_no_identity_or_unavailable_slot_never_refreshes(inventory, missing):
    check, _, queries, replies = inventory
    replies[missing] = None
    with pytest.raises(PermissionError):
        check()
    assert not any(q.startswith(("UPDATE", "INSERT")) for q in queries)


def test_expired_identity_never_queries_or_refreshes(inventory):
    check, identity, queries, _ = inventory
    identity.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(PermissionError):
        check()
    assert not queries


def test_disabled_workflow_never_refreshes(inventory, monkeypatch):
    check, _, queries, _ = inventory
    monkeypatch.delenv("VAB_ENABLE_AGENT_SCHEDULING")
    with pytest.raises(PermissionError):
        check()
    assert not queries
