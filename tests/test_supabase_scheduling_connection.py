"""No hosted booking connections without explicit, scoped server authority."""

import sys
from types import SimpleNamespace

import pytest

from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_scheduling,
)

REF = "wntbjxjeaxngjrffmnis"


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        self.conn.sql.append(sql)
        if sql == "SELECT current_database()":
            self.result = ("postgres",)
        elif sql == "SELECT current_user, session_user":
            self.result = (
                "vab_scheduling_writer",
                self.conn.session_user,
            )
        else:
            assert sql == "SET ROLE vab_scheduling_writer"

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(
        self,
        host=f"db.{REF}.supabase.co",
        user="vab_scheduling_login",
        session_user="vab_scheduling_login",
    ):
        self.info = SimpleNamespace(host=host, user=user)
        self.session_user = session_user
        self.sql = []
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


def test_hosted_writes_are_off_by_default(monkeypatch):
    monkeypatch.delenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", raising=False)
    with pytest.raises(PermissionError, match="disabled"):
        connect_private_supabase_scheduling()


def test_wrong_project_ref_and_missing_credentials_denied(monkeypatch):
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", "true")
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", "otherproject")
    with pytest.raises(PermissionError, match="Approved"):
        connect_private_supabase_scheduling()
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", REF)
    monkeypatch.delenv("VAB_SUPABASE_SCHEDULING_DATABASE_URL", raising=False)
    with pytest.raises(PermissionError, match="credential"):
        connect_private_supabase_scheduling()


def test_server_connection_sets_and_verifies_dedicated_role(monkeypatch):
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", "true")
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", REF)
    monkeypatch.setenv("VAB_SUPABASE_SCHEDULING_DATABASE_URL", "placeholder-not-real")
    conn = FakeConnection()
    calls = []

    def connect(dsn, **kwargs):
        calls.append((dsn, kwargs))
        return conn

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))
    assert connect_private_supabase_scheduling() is conn
    assert calls == [("placeholder-not-real", {"connect_timeout": 8, "sslmode": "require"})]
    assert conn.sql == [
        "SET ROLE vab_scheduling_writer",
        "SELECT current_database()",
        "SELECT current_user, session_user",
    ]


@pytest.mark.parametrize(
    "conn",
    [
        FakeConnection(host="db.otherproject.supabase.co"),
        FakeConnection(session_user="postgres"),
    ],
)
def test_reject_wrong_host_or_admin_session_and_close_connection(monkeypatch, conn):
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", "true")
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", REF)
    monkeypatch.setenv("VAB_SUPABASE_SCHEDULING_DATABASE_URL", "placeholder-not-real")
    monkeypatch.setitem(
        sys.modules,
        "psycopg",
        SimpleNamespace(connect=lambda *_args, **_kwargs: conn),
    )
    with pytest.raises((PermissionError, ValueError)):
        connect_private_supabase_scheduling()
    assert conn.closed
