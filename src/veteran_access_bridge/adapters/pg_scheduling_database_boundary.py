"""Database boundary for private synthetic scheduling operations.

Keep the original isolated-local development path. Hosted Supabase writes
require an explicit protected-server opt-in, exact project identity, and a
dedicated least-privilege SQL role. Never trust a browser-supplied flag.
"""

from __future__ import annotations

import os

SUPABASE_PROJECT_REF = "wntbjxjeaxngjrffmnis"
SUPABASE_SCHEDULING_ROLE = "vab_scheduling_writer"
SUPABASE_LOGIN_ROLE = "vab_scheduling_login"
SUPABASE_TEST_ROLE = "vab_test_scheduling_writer"
SUPABASE_TEST_LOGIN = "vab_test_scheduling_login"
LOCAL_DEV_DATABASE = "veteran_access_bridge_dev"


def assert_synthetic_scheduling_database(cur, conn, *, write: bool) -> str:
    """Return only an explicitly authorized schema for scheduling SQL.

    Hosted test credentials can access only vab_test. Hosted operational login
    stays disabled until a separate deployment review. Local synthetic
    development retains the original vab schema.
    """
    cur.execute("SELECT current_database()")
    database = cur.fetchone()[0]
    if database == LOCAL_DEV_DATABASE:
        return "vab"
    if database != "postgres":
        raise ValueError("Scheduling access restricted to synthetic development DB")
    if os.getenv("VAB_SUPABASE_PROJECT_REF") != SUPABASE_PROJECT_REF:
        raise PermissionError("Approved Supabase project setting required")

    allow_operational = os.getenv("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES") == "true"
    allow_test = (
        os.getenv("VAB_SUPABASE_TEST_MODE") == "true"
        and os.getenv("VAB_ENABLE_SUPABASE_TEST_WRITES") == "true"
    )
    if write and not (allow_operational or allow_test):
        raise PermissionError("Hosted scheduling writes are disabled")

    info = getattr(conn, "info", None)
    host = str(getattr(info, "host", "") or "").lower()
    username = str(getattr(info, "user", "") or "")
    direct = host == f"db.{SUPABASE_PROJECT_REF}.supabase.co"
    pooler = host.endswith(".pooler.supabase.com") and username.endswith(
        f".{SUPABASE_PROJECT_REF}"
    )
    if not (direct or pooler):
        raise PermissionError("Supabase project connection identity mismatch")

    # The authenticated login must match the effective, explicitly SET role.
    # A DBA's SET ROLE cannot impersonate the dedicated login's session_user.
    cur.execute("SELECT current_user, session_user")
    role, login = cur.fetchone()
    if role == SUPABASE_SCHEDULING_ROLE and login == SUPABASE_LOGIN_ROLE:
        if write and not allow_operational:
            raise PermissionError("Operational scheduling writes are disabled")
        return "vab"
    if role == SUPABASE_TEST_ROLE and login == SUPABASE_TEST_LOGIN:
        if os.getenv("VAB_SUPABASE_TEST_MODE") != "true":
            raise PermissionError("Synthetic test mode is disabled")
        if write and not allow_test:
            raise PermissionError("Synthetic test writes are disabled")
        return "vab_test"
    raise PermissionError("Dedicated scheduling login and effective role required")
