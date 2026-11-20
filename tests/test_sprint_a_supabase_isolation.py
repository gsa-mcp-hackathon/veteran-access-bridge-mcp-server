"""Sprint A offline isolation and application boundary tests (never networked)."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest

from veteran_access_bridge.adapters.pg_eps_recovery import (
    recover_committed_eps_booking,
)
from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.pg_scheduling_sql import execute_scheduling_sql
from veteran_access_bridge.adapters.pg_synthetic_eps_booking import (
    EPSBookingRequest,
    commit_synthetic_eps_booking,
)
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
    connect_private_supabase_test_scheduling_readonly,
)
from veteran_access_bridge.services.pg_signed_decisions import (
    persist_signed_scheduling_decision,
)

REF = "wntbjxjeaxngjrffmnis"


class Cursor:
    def __init__(
        self, login="vab_test_scheduling_login", role="vab_test_scheduling_writer"
    ):
        self.login = login
        self.role = role
        self.commands = []
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.commands.append((sql, params))
        if sql == "SELECT current_database()":
            self.result = ("postgres",)
        elif sql == "SELECT current_user, session_user":
            self.result = (self.role, self.login)
        elif sql.startswith("SELECT l.request_id FROM vab_test.scheduling_case_link"):
            self.result = None
        elif "FROM vab_test.scheduling_case_link l" in sql:
            self.result = None
        elif sql.startswith("SET ROLE "):
            assert sql == "SET ROLE vab_test_scheduling_writer"
        elif sql == "SET TRANSACTION READ ONLY":
            pass
        elif "FROM vab_test.appointment a" in sql:
            self.result = None
        else:
            raise AssertionError(f"Unexpected scoped SQL: {sql}")

    def fetchone(self):
        return self.result


class Connection:
    def __init__(
        self,
        cursor=None,
        *,
        host=f"db.{REF}.supabase.co",
        login="vab_test_scheduling_login",
    ):
        self.instance = cursor or Cursor(login=login)
        self.info = SimpleNamespace(host=host, user=login)
        self.closed = False

    def cursor(self):
        return self.instance

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def close(self):
        self.closed = True


@pytest.fixture
def test_mode(monkeypatch):
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", REF)
    monkeypatch.setenv("VAB_SUPABASE_TEST_MODE", "true")
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_TEST_WRITES", "true")
    monkeypatch.delenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", raising=False)


def test_test_role_selects_only_test_schema(test_mode):
    conn = Connection()
    assert (
        assert_synthetic_scheduling_database(conn.instance, conn, write=True)
        == "vab_test"
    )


def test_test_role_refuses_operational_sql_and_schema_spoof(test_mode):
    conn = Connection()
    with pytest.raises(PermissionError):
        execute_scheduling_sql(conn.instance, "vab_test;", "SELECT 1")
    with pytest.raises(ValueError, match="Mixed"):
        execute_scheduling_sql(
            conn.instance, "vab_test", "SELECT * FROM vab_test.appointment"
        )
    execute_scheduling_sql(
        conn.instance,
        "vab_test",
        "SELECT l.request_id FROM vab.scheduling_case_link l WHERE l.case_id=%s",
        ("missing",),
    )
    query, params = conn.instance.commands[-1]
    assert "vab_test.scheduling_case_link" in query
    assert "vab.scheduling_case_link" not in query
    assert params == ("missing",)


def test_booking_uses_test_schema_and_denies_missing_case(test_mode):
    conn = Connection()
    req = EPSBookingRequest(
        case_id="synthetic-case",
        option_id="synthetic-option",
        slot_id=uuid4(),
        authorization_id=uuid4(),
        idempotency_key="synthetic-key",
        scheduler_actor_id="scheduler",
    )
    with pytest.raises(ValueError, match="Unknown synthetic scheduling case"):
        commit_synthetic_eps_booking(conn, req)
    assert any("vab_test.scheduling_case_link" in q for q, _ in conn.instance.commands)
    assert not any("FROM vab." in q for q, _ in conn.instance.commands)


def test_signed_decision_uses_test_schema(test_mode, monkeypatch):
    from veteran_access_bridge.services import pg_signed_decisions

    monkeypatch.setattr(
        pg_signed_decisions,
        "_trusted_claims",
        lambda *_args: {"role": "VETERAN", "sub": "synthetic-actor"},
    )
    conn = Connection()
    with pytest.raises(ValueError, match="Synthetic scheduling case not found"):
        persist_signed_scheduling_decision(
            lambda: conn,
            assertion="test-only-assertion",
            verifier_secret="unused-in-monkeypatch",
            case_id="synthetic-case",
            option_id="synthetic-option",
            idempotency_key="synthetic-veteran",
            correlation_id="synthetic-correlation",
            service_evidence_reference="synthetic-evidence",
        )
    assert any("vab_test.scheduling_case_link" in q for q, _ in conn.instance.commands)


def test_test_role_cannot_be_used_without_test_opt_in(monkeypatch):
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", REF)
    monkeypatch.delenv("VAB_SUPABASE_TEST_MODE", raising=False)
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", "true")
    conn = Connection()
    with pytest.raises(PermissionError, match="Synthetic test mode"):
        assert_synthetic_scheduling_database(conn.instance, conn, write=True)


def test_private_test_factory_requires_separate_credentials(test_mode, monkeypatch):
    monkeypatch.delenv("VAB_SUPABASE_TEST_DATABASE_URL", raising=False)
    with pytest.raises(PermissionError, match="test credential"):
        connect_private_supabase_test_scheduling()
    monkeypatch.setenv("VAB_SUPABASE_TEST_DATABASE_URL", "test-only-placeholder")
    conn = Connection()
    seen = []

    def connect(dsn, **options):
        seen.append((dsn, options))
        return conn

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    assert connect_private_supabase_test_scheduling() is conn
    assert seen == [
        ("test-only-placeholder", {"connect_timeout": 8, "sslmode": "verify-full"})
    ]
    assert conn.instance.commands[0][0] == "SET ROLE vab_test_scheduling_writer"


def test_readonly_factory_never_requires_test_writes(test_mode, monkeypatch):
    monkeypatch.delenv("VAB_ENABLE_SUPABASE_TEST_WRITES", raising=False)
    monkeypatch.setenv("VAB_SUPABASE_TEST_DATABASE_URL", "test-only-placeholder")
    conn = Connection()
    monkeypatch.setitem(
        sys.modules, "psycopg", SimpleNamespace(connect=lambda *_a, **_kw: conn)
    )
    assert connect_private_supabase_test_scheduling_readonly() is conn
    assert [query for query, _ in conn.instance.commands[:2]] == [
        "SET TRANSACTION READ ONLY",
        "SET ROLE vab_test_scheduling_writer",
    ]
    with pytest.raises(PermissionError, match="writes are disabled"):
        connect_private_supabase_test_scheduling()


def test_test_factory_denies_admin_login_even_with_role_switch(test_mode, monkeypatch):
    monkeypatch.setenv("VAB_SUPABASE_TEST_DATABASE_URL", "test-only-placeholder")
    conn = Connection(login="postgres")
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_a, **_kw: conn),
    )
    with pytest.raises(PermissionError, match="Dedicated scheduling"):
        connect_private_supabase_test_scheduling()
    assert conn.closed


def test_recovery_reads_test_schema_without_creating_booking(test_mode):
    conn = Connection()
    result = recover_committed_eps_booking(
        lambda: conn,
        case_id="synthetic-case",
        option_id="synthetic-option",
        slot_id=uuid4(),
        authorization_id=uuid4(),
        idempotency_key="synthetic-booking",
        scheduler_actor_id="scheduler",
    )
    assert result is None
    assert any("vab_test.appointment a" in q for q, _ in conn.instance.commands)


def test_test_factory_rejects_transaction_pooler(test_mode, monkeypatch):
    monkeypatch.setenv("VAB_SUPABASE_TEST_DATABASE_URL", "test-only-placeholder")
    conn = Connection(
        host="aws-0-ca-central-1.pooler.supabase.com",
        login=f"vab_test_scheduling_login.{REF}",
    )
    conn.info.port = 6543
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_args, **_kwargs: conn),
    )
    with pytest.raises(PermissionError, match="port 5432"):
        connect_private_supabase_test_scheduling()
    assert conn.closed
