"""Explicit hosted synthetic CRM acceptance; retains labelled test records.

Uses the existing protected test connection. Never supplies or logs credentials.
This service harness is not evidence of IBM agent tool selection.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from psycopg.errors import InsufficientPrivilege

from veteran_access_bridge.mcp import session_scope as scope
from veteran_access_bridge.services import crm


async def main():
    if os.getenv("VAB_RUN_CRM_ACCEPTANCE") != "true":
        raise PermissionError("Explicit synthetic CRM acceptance opt-in required")
    case = "VAB-DEMO-20261113-CASE-001"
    other = "VAB-DEMO-20261113-CASE-002"
    interaction = "crm-acceptance-" + str(uuid4())
    state = scope.SessionScope(case, matched_case=case, interaction_id=interaction)
    checks = []

    async def call(name, payload=None, key=None, selected_case=case):
        async def invoke():
            if name == "get_crm_case":
                return crm.get_case(selected_case)
            return crm.mutate(selected_case, name, payload, key)

        with scope.trusted_turn(
            state, expires=time.monotonic() + 60, crm_enabled=True
        ) as token:
            return await scope.scoped_call(token, name, selected_case, invoke)

    with crm.connect_private_supabase_test_scheduling_readonly() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM vab_test.appointment")
            before = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
                "ON n.oid=c.relnamespace WHERE n.nspname='vab_test' "
                "AND c.relname IN ('crm_interaction','crm_follow_up','crm_event') "
                "AND c.relrowsecurity AND c.relforcerowsecurity"
            )
            assert cur.fetchone()[0] == 3
            for table in ("crm_interaction", "crm_follow_up", "crm_event"):
                cur.execute(
                    "SELECT has_table_privilege('anon',%s,'SELECT'), "
                    "has_table_privilege('authenticated',%s,'INSERT'), "
                    "has_table_privilege(current_user,%s,'DELETE')",
                    ("vab_test." + table,) * 3,
                )
                assert cur.fetchone() == (False, False, False)
    checks.append("forced_rls_and_restricted_grants")
    note = {
        "summary": "SYNTHETIC CRM ACCEPTANCE ONLY: verify saved call context. "
        "No actual caller request, appointment change or staff contact.",
        "disposition": "FOLLOW_UP_NEEDED",
    }
    saved = await call("record_crm_interaction", note, "note-1")
    assert saved["persisted"] and not saved["booking_created"]
    retry = await call("record_crm_interaction", note, "note-1")
    assert retry["replayed"] and retry["record_id"] == saved["record_id"]
    checks.extend(["note_persisted", "retry_returns_same_receipt"])
    try:
        await call("record_crm_interaction", {**note, "summary": "changed"}, "note-1")
        raise AssertionError("Changed retry was accepted")
    except ValueError:
        checks.append("changed_retry_denied")
    task = await call(
        "create_crm_follow_up",
        {
            "description": "SYNTHETIC ACCEPTANCE ONLY. Do not contact anyone.",
            "owner_queue": "MSA",
            "due_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        },
        "task-1",
    )
    updated = await call(
        "update_crm_follow_up",
        {
            "task_id": task["record_id"],
            "expected_version": 1,
            "status": "CANCELLED",
            "reason": "Acceptance fixture complete; no staff work requested.",
        },
        "task-cancel",
    )
    assert updated["version"] == 2
    checks.append("task_created_and_cancelled_with_version")
    try:
        await call(
            "update_crm_follow_up",
            {
                "task_id": task["record_id"],
                "expected_version": 1,
                "status": "IN_PROGRESS",
                "reason": "Stale acceptance request must fail",
            },
            "task-stale",
        )
        raise AssertionError("Stale update accepted")
    except ValueError:
        checks.append("stale_task_update_denied")
    history = await call("get_crm_case")
    assert any(r["record_id"] == saved["record_id"] for r in history["interactions"])
    assert any(
        r["task_id"] == task["record_id"] and r["status"] == "CANCELLED"
        for r in history["follow_ups"]
    )
    checks.append("fresh_connection_readback")
    try:
        await call("get_crm_case", selected_case=other)
        raise AssertionError("Cross-case tool call accepted")
    except PermissionError:
        checks.append("cross_case_service_denied")
    with crm.connect_private_supabase_test_scheduling_readonly() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM vab_test.crm_interaction")
            assert cur.fetchone()[0] == 0
            cur.execute("SELECT set_config('vab.crm_case_id',%s,true)", (other,))
            cur.execute(
                "SELECT count(*) FROM vab_test.crm_interaction WHERE record_id=%s",
                (saved["record_id"],),
            )
            assert cur.fetchone()[0] == 0
    checks.extend(["missing_database_scope_hides_rows", "cross_case_rls_hides_rows"])
    try:
        with crm.connect_private_supabase_test_scheduling() as conn:
            with conn.cursor() as cur:
                crm._scope(cur, other, interaction)
                cur.execute(
                    "INSERT INTO vab_test.crm_interaction "
                    "(record_id,case_id,interaction_id,summary,disposition) "
                    "VALUES (%s,%s,%s,'must fail','FOLLOW_UP_NEEDED')",
                    (str(uuid4()), case, interaction),
                )
                raise AssertionError("RLS accepted cross-case insert")
    except InsufficientPrivilege:
        checks.append("cross_case_rls_write_denied")
    with crm.connect_private_supabase_test_scheduling_readonly() as conn:
        with conn.cursor() as cur:
            crm._scope(cur, case, interaction)
            cur.execute(
                "SELECT count(*) FROM vab_test.crm_event WHERE interaction_id=%s",
                (interaction,),
            )
            assert cur.fetchone()[0] == 3
            cur.execute(
                "SELECT count(*) FROM vab_test.crm_interaction WHERE interaction_id=%s",
                (interaction,),
            )
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT count(*) FROM vab_test.appointment")
            after = cur.fetchone()[0]
            assert before == after
    checks.extend(["three_audit_events_one_note", "appointment_count_unchanged"])
    print(
        json.dumps(
            {
                "status": "passed",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "evidence_kind": "service_harness_not_agent_selected",
                "case_id": case,
                "interaction_id": interaction,
                "note_id": saved["record_id"],
                "task_id": task["record_id"],
                "task_status": "CANCELLED",
                "appointments_before": before,
                "appointments_after": after,
                "checks": checks,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        # Avoid database exception text that may contain protected connection info.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
