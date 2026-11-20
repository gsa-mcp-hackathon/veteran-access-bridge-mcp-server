"""Protected server-only Supabase connection factory for synthetic scheduling.

This is not registered as an MCP tool, browser endpoint, or API route.
The dedicated login remains NOLOGIN until a separately approved credential
bootstrap. Never use the postgres owner, anon, or service_role credentials.
"""

from __future__ import annotations

import os

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    SUPABASE_PROJECT_REF,
    SUPABASE_SCHEDULING_ROLE,
    SUPABASE_TEST_ROLE,
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.supabase_sprint6_preflight import (
    assert_supabase_project_connection,
)


def _require_session_mode(conn) -> None:
    """SET ROLE must not run through Supavisor transaction pooling (6543)."""
    info = getattr(conn, "info", None)
    port = str(getattr(info, "port", "5432"))
    if port != "5432":
        raise PermissionError(
            "Role-scoped scheduling requires direct/session port 5432"
        )


def connect_private_supabase_scheduling():
    """Return a DB connection with a restricted effective SQL role.

    Callers own commit/rollback and must still verify actor identity and the
    synthetic business gates in the existing service layer.
    """
    if os.getenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES") != "true":
        raise PermissionError("Supabase scheduling writes are disabled")
    if os.getenv("VAB_SUPABASE_PROJECT_REF") != SUPABASE_PROJECT_REF:
        raise PermissionError("Approved Supabase project required")

    dsn = os.getenv("VAB_SUPABASE_SCHEDULING_DATABASE_URL")
    if not dsn:
        raise PermissionError("Private scheduling database credential not configured")

    import psycopg

    conn = psycopg.connect(dsn, connect_timeout=8, sslmode="require")
    try:
        assert_supabase_project_connection(conn, SUPABASE_PROJECT_REF)
        _require_session_mode(conn)
        with conn.cursor() as cur:
            # Fixed role name, never user-supplied SQL; the dedicated login
            # must be explicitly granted SET ROLE by DB administrators.
            cur.execute(f"SET ROLE {SUPABASE_SCHEDULING_ROLE}")
            assert_synthetic_scheduling_database(cur, conn, write=True)
        return conn
    except BaseException:
        conn.close()
        raise


def connect_private_supabase_test_scheduling():
    """Open only the private synthetic test role; not registered via MCP/HTTP.

    Requires separate TEST credentials. The operational scheduling credentials,
    role, flags and schema are never substituted for this test connection.
    Both test roles are NOLOGIN in Supabase until an approved credential setup.
    """
    return _connect_private_supabase_test_scheduling(write=True)


def connect_private_supabase_test_scheduling_readonly():
    """Open the dedicated test role in a read-only transaction."""
    return _connect_private_supabase_test_scheduling(write=False)


def _connect_private_supabase_test_scheduling(*, write: bool):
    if os.getenv("VAB_SUPABASE_TEST_MODE") != "true":
        raise PermissionError("Hosted synthetic test mode is disabled")
    if write and os.getenv("VAB_ENABLE_SUPABASE_TEST_WRITES") != "true":
        raise PermissionError("Hosted synthetic test writes are disabled")
    if os.getenv("VAB_SUPABASE_PROJECT_REF") != SUPABASE_PROJECT_REF:
        raise PermissionError("Approved Supabase project required")
    dsn = os.getenv("VAB_SUPABASE_TEST_DATABASE_URL")
    if not dsn:
        raise PermissionError("Dedicated Supabase test credential not configured")

    import psycopg

    conn = psycopg.connect(dsn, connect_timeout=8, sslmode="verify-full")
    try:
        assert_supabase_project_connection(conn, SUPABASE_PROJECT_REF)
        _require_session_mode(conn)
        with conn.cursor() as cur:
            if not write:
                cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(f"SET ROLE {SUPABASE_TEST_ROLE}")
            schema = assert_synthetic_scheduling_database(cur, conn, write=write)
            if schema != "vab_test":
                raise PermissionError("Test database connection escaped test schema")
        return conn
    except BaseException:
        conn.close()
        raise
