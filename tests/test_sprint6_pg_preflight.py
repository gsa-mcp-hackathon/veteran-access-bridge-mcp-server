"""Offline tests for the read-only Sprint 6 PostgreSQL preflight."""

import pytest

from veteran_access_bridge.adapters.supabase_sprint6_preflight import (
    REQUIRED_TABLES,
    assert_supabase_project_connection,
    inspect_isolated_scheduling_database,
)


class Cursor:
    def __init__(self, *, db="postgres", tables=None, identity=True,
                 unique=True, duplicates=(), bookings=()):
        self.db = db
        self.tables = set(REQUIRED_TABLES) if tables is None else set(tables)
        self.identity = identity
        self.unique = unique
        self.duplicates = duplicates
        self.bookings = bookings
        self.commands = []
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=None):
        self.commands.append(sql)
        if sql == "SELECT current_database()":
            self.rows = [(self.db,)]
        elif "FROM pg_catalog.pg_tables" in sql:
            self.rows = [(name,) for name in self.tables]
        elif "FROM pg_catalog.pg_attribute a" in sql:
            self.rows = [("decision_order", "a", True)] if self.identity else []
        elif "FROM pg_catalog.pg_constraint co" in sql:
            self.rows = [(self.unique,)]
        elif "GROUP BY request_id HAVING COUNT(*) > 1" in sql:
            self.rows = list(self.duplicates)
        elif "FROM vab.appointment a" in sql:
            self.rows = list(self.bookings)
        else:
            raise AssertionError(f"Unexpected SQL in mock: {sql}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, cursor, host="db.wntbjxjeaxngjrffmnis.supabase.co", user="postgres"):
        from types import SimpleNamespace

        self.cursor_instance = cursor
        self.info = SimpleNamespace(host=host, user=user)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance


def test_read_only_empty_synthetic_database_preflight():
    cur = Cursor()
    report = inspect_isolated_scheduling_database(
        lambda: Connection(cur), project_ref="wntbjxjeaxngjrffmnis"
    )
    assert all(report["checks"].values())
    assert report["counts"]["active_synthetic_bookings_checked"] == 0
    assert report["counts"]["requests_with_duplicate_active_bookings"] == 0
    assert not any(
        query.lstrip().upper().startswith(
            ("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP")
        )
        for query in cur.commands
    )


def test_wrong_database_refused_before_project_table_queries():
    cur = Cursor(db="production_db")
    with pytest.raises(ValueError, match="Supabase postgres database"):
        inspect_isolated_scheduling_database(
            lambda: Connection(cur), project_ref="wntbjxjeaxngjrffmnis"
        )
    assert cur.commands == ["SELECT current_database()"]


def test_missing_decision_order_fails_schema_gate():
    cur = Cursor(identity=False)
    report = inspect_isolated_scheduling_database(
            lambda: Connection(cur), project_ref="wntbjxjeaxngjrffmnis"
        )
    assert report["checks"]["serialized_decision_column"] is False
    assert report["checks"]["serialized_decision_unique"] is False


def test_missing_required_tables_fails_without_reading_bookings():
    cur = Cursor(tables={"appointment", "slot"})
    report = inspect_isolated_scheduling_database(
            lambda: Connection(cur), project_ref="wntbjxjeaxngjrffmnis"
        )
    assert report["checks"] == {"required_tables_present": False}
    assert not any("FROM vab.appointment" in sql for sql in cur.commands)


def test_duplicate_appointments_fail_preflight():
    cur = Cursor(duplicates=[("synthetic-request", 2)])
    report = inspect_isolated_scheduling_database(
            lambda: Connection(cur), project_ref="wntbjxjeaxngjrffmnis"
        )
    assert not report["checks"]["no_duplicate_active_bookings"]
    assert report["counts"]["requests_with_duplicate_active_bookings"] == 1


def test_unapproved_supabase_project_ref_denied_before_sql():
    cur = Cursor()
    with pytest.raises(ValueError, match="approved Supabase project"):
        inspect_isolated_scheduling_database(
            lambda: Connection(cur),
            project_ref="wrongproject",
        )
    assert not cur.commands


def test_supavisor_pooler_requires_matching_scoped_username():
    cur = Cursor()
    good = Connection(
        cur,
        host="aws-0-ca-central-1.pooler.supabase.com",
        user="postgres.wntbjxjeaxngjrffmnis",
    )
    assert_supabase_project_connection(good, "wntbjxjeaxngjrffmnis")
    bad = Connection(
        cur,
        host="aws-0-ca-central-1.pooler.supabase.com",
        user="postgres.anotherproject",
    )
    with pytest.raises(ValueError, match="approved Supabase project"):
        assert_supabase_project_connection(bad, "wntbjxjeaxngjrffmnis")
