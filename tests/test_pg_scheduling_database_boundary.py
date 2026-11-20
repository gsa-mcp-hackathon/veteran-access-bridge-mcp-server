"""Fail-closed scheduling DB boundary for local fixtures and Supabase hosting."""

from types import SimpleNamespace

import pytest

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)


class Cursor:
    def __init__(
        self,
        database="postgres",
        role="vab_scheduling_writer",
        login="vab_scheduling_login",
    ):
        self.database = database
        self.role = role
        self.login = login
        self.queries = []
        self.result = None

    def execute(self, sql):
        self.queries.append(sql)
        if sql == "SELECT current_database()":
            self.result = (self.database,)
        elif sql == "SELECT current_user, session_user":
            self.result = (self.role, self.login)
        else:
            raise AssertionError("Unexpected database query")

    def fetchone(self):
        return self.result


def connection(
    host="db.wntbjxjeaxngjrffmnis.supabase.co",
    username="vab_scheduling_login",
):
    return SimpleNamespace(info=SimpleNamespace(host=host, user=username))


@pytest.mark.parametrize("write", [True, False])
def test_local_dev_still_works_without_hosted_credentials(monkeypatch, write):
    monkeypatch.delenv("VAB_SUPABASE_PROJECT_REF", raising=False)
    monkeypatch.delenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", raising=False)
    cur = Cursor(database="veteran_access_bridge_dev")
    assert_synthetic_scheduling_database(cur, SimpleNamespace(), write=write)
    assert cur.queries == ["SELECT current_database()"]


def test_hosted_writer_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", "wntbjxjeaxngjrffmnis")
    monkeypatch.delenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", raising=False)
    cur = Cursor()
    with pytest.raises(PermissionError, match="disabled"):
        assert_synthetic_scheduling_database(cur, connection(), write=True)
    assert cur.queries == ["SELECT current_database()"]


def test_readback_can_check_role_without_write_opt_in(monkeypatch):
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", "wntbjxjeaxngjrffmnis")
    monkeypatch.delenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", raising=False)
    cur = Cursor()
    assert_synthetic_scheduling_database(cur, connection(), write=False)
    assert "SELECT current_user, session_user" in cur.queries


@pytest.mark.parametrize(
    "database,role,login,host,username",
    [
        ("unexpected", "vab_scheduling_writer", "vab_scheduling_login",
         "db.wntbjxjeaxngjrffmnis.supabase.co", "vab_scheduling_login"),
        ("postgres", "postgres", "postgres",
         "db.wntbjxjeaxngjrffmnis.supabase.co", "postgres"),
        ("postgres", "vab_scheduling_writer", "postgres",
         "db.wntbjxjeaxngjrffmnis.supabase.co", "postgres"),
        ("postgres", "vab_scheduling_writer", "vab_scheduling_login",
         "db.wrongproject.supabase.co", "vab_scheduling_login"),
    ],
)
def test_hosted_connection_refuses_unauthorized_database_role_or_host(
    monkeypatch, database, role, login, host, username
):
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", "wntbjxjeaxngjrffmnis")
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", "true")
    with pytest.raises((ValueError, PermissionError)):
        assert_synthetic_scheduling_database(
            Cursor(database=database, role=role, login=login),
            connection(host, username),
            write=True,
        )


def test_supavisor_scoped_username_and_role(monkeypatch):
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", "wntbjxjeaxngjrffmnis")
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES", "true")
    cur = Cursor()
    assert_synthetic_scheduling_database(
        cur,
        connection(
            "aws-0-ca-central-1.pooler.supabase.com",
            "vab_scheduling_login.wntbjxjeaxngjrffmnis",
        ),
        write=True,
    )
    assert "SELECT current_user, session_user" in cur.queries
