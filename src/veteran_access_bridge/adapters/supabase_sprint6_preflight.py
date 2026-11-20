"""Read-only Sprint 6 Supabase preflight for the approved VAB project.

Run explicitly with VAB_RUN_SPRINT6_SUPABASE_PREFLIGHT=true and VAB_DATABASE_URL.
Never applies migrations, inserts fixtures, or books appointments.
"""

from __future__ import annotations

import os
from collections import Counter
from uuid import uuid5

from veteran_access_bridge.adapters.synthetic_ids import (
    VAB_SYNTHETIC_NAMESPACE,
    persistent_uuid,
)

EXPECTED_DATABASE = "postgres"
REQUIRED_TABLES = (
    "scheduling_case_link",
    "scheduling_decision",
    "scheduling_transition",
    "appointment",
    "slot",
    "audit_event",
    "authorization",
    "referral",
    "data_source",
)


def assert_supabase_project_connection(conn, project_ref: str) -> None:
    """Reject other database hosts or projects before any VAB reads.

    For direct connections, validate the exact project hostname. For Supavisor
    pooler connections, validate the pooler hostname AND scoped username.
    Database name alone is not a sufficient hosted-project identity check.
    """
    if not project_ref or not project_ref.isalnum():
        raise ValueError("Approved Supabase project reference required")
    info = getattr(conn, "info", None)
    host = str(getattr(info, "host", "") or "").lower()
    username = str(getattr(info, "user", "") or "")
    direct = host == f"db.{project_ref}.supabase.co"
    pooler = host.endswith(".pooler.supabase.com") and username.endswith(
        f".{project_ref}"
    )
    if not (direct or pooler):
        raise ValueError("Connection does not match approved Supabase project")


def inspect_isolated_scheduling_database(
    connect, *, project_ref: str
) -> dict:
    """Read only schema and synthetic appointment integrity.

    Caller supplies a database factory. This function never writes data and
    leaves the database transaction read-only throughout inspection.
    """
    checks: dict[str, bool] = {}
    counts: dict[str, int] = {}

    with connect() as conn:
        assert_supabase_project_connection(conn, project_ref)
        # Guard before accessing project tables. No SQL mutations are made.
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            database = cur.fetchone()[0]
            if database != EXPECTED_DATABASE:
                raise ValueError("Sprint 6 preflight requires the Supabase postgres database")
            cur.execute(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname='vab'"
            )
            tables = {row[0] for row in cur.fetchall()}
            checks["required_tables_present"] = set(REQUIRED_TABLES).issubset(tables)
            if not checks["required_tables_present"]:
                return {"database": database, "checks": checks, "counts": counts}

            cur.execute(
                "SELECT a.attname,a.attidentity,a.attnotnull "
                "FROM pg_catalog.pg_attribute a "
                "JOIN pg_catalog.pg_class c ON c.oid=a.attrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='vab' AND c.relname='scheduling_decision' "
                "AND a.attname='decision_order' AND NOT a.attisdropped"
            )
            decision_order = cur.fetchone()
            checks["serialized_decision_column"] = (
                decision_order is not None
                and decision_order[0] == "decision_order"
                and decision_order[1] == "a"
                and decision_order[2] is True
            )
            if checks["serialized_decision_column"]:
                cur.execute(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM pg_catalog.pg_constraint co "
                    "JOIN pg_catalog.pg_class c ON c.oid=co.conrelid "
                    "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                    "JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid "
                    "WHERE n.nspname='vab' AND c.relname='scheduling_decision' "
                    "AND a.attname='decision_order' AND co.contype='u' "
                    "AND co.conkey=ARRAY[a.attnum]::smallint[]"
                    ")"
                )
                checks["serialized_decision_unique"] = cur.fetchone()[0]
            else:
                checks["serialized_decision_unique"] = False

            cur.execute(
                "SELECT request_id,COUNT(*) FROM vab.appointment "
                "WHERE status='BOOKED_SIMULATED' "
                "GROUP BY request_id HAVING COUNT(*) > 1"
            )
            duplicates = cur.fetchall()
            counts["requests_with_duplicate_active_bookings"] = len(duplicates)
            checks["no_duplicate_active_bookings"] = not duplicates

            cur.execute(
                "SELECT a.appointment_id,a.idempotency_key,a.slot_id,"
                "a.approved_by,l.case_id,s.provider_id,s.source_id "
                "FROM vab.appointment a "
                "JOIN vab.scheduling_case_link l ON l.request_id=a.request_id "
                "JOIN vab.slot s ON s.slot_id=a.slot_id "
                "WHERE a.status='BOOKED_SIMULATED'"
            )
            bookings = cur.fetchall()
            counts["active_synthetic_bookings_checked"] = len(bookings)
            mismatches = Counter()
            for (
                appointment_id, key, slot_id, actor, case_id, provider_id, source_id
            ) in bookings:
                if appointment_id != persistent_uuid("appointment", key):
                    mismatches["appointment_id"] += 1
                transition_id = uuid5(
                    VAB_SYNTHETIC_NAMESPACE, "booking-transition:" + key
                )
                audit_id = uuid5(
                    VAB_SYNTHETIC_NAMESPACE, "booking-audit:" + key
                )
                cur.execute(
                    "SELECT evidence,case_id,idempotency_key FROM "
                    "vab.scheduling_transition WHERE transition_id=%s "
                    "AND event_type='BOOKED_SIMULATED'",
                    (transition_id,),
                )
                transition = cur.fetchone()
                cur.execute(
                    "SELECT details,correlation_id,source_id FROM "
                    "vab.audit_event WHERE event_id=%s "
                    "AND event_type='BOOKED_SIMULATED'",
                    (audit_id,),
                )
                audit = cur.fetchone()
                if transition is None or audit is None:
                    mismatches["missing_evidence"] += 1
                    continue
                evidence = transition[0]
                expected = {
                    "synthetic": True,
                    "appointment_id": str(appointment_id),
                    "idempotency_key": key,
                    "case_id": case_id,
                    "slot_id": str(slot_id),
                    "scheduler_actor_id": actor,
                    "provider_id": provider_id,
                    "slot_source_id": source_id,
                }
                if (
                    not isinstance(evidence, dict)
                    or any(evidence.get(k) != v for k, v in expected.items())
                    or not evidence.get("option_id")
                    or not evidence.get("authorization_id")
                    or not evidence.get("authorization_source_id")
                    or transition[1:] != (case_id, "booking:" + key)
                    or audit[0] != evidence
                    or audit[1:] != (key, source_id)
                ):
                    mismatches["conflicting_evidence"] += 1

            counts["bookings_with_inconsistent_evidence"] = sum(
                mismatches.values()
            )
            checks["booking_evidence_consistent"] = not mismatches

    return {"database": EXPECTED_DATABASE, "checks": checks, "counts": counts}


def main() -> int:
    """Explicit opt-in: fail closed without isolated DB and correct switch."""
    if os.getenv("VAB_RUN_SPRINT6_SUPABASE_PREFLIGHT") != "true":
        raise SystemExit(
            "Preflight disabled. Set VAB_RUN_SPRINT6_SUPABASE_PREFLIGHT=true."
        )
    dsn = os.getenv("VAB_DATABASE_URL")
    if not dsn:
        raise SystemExit("VAB_DATABASE_URL is required (do not print its contents).")

    project_ref = os.getenv("VAB_SUPABASE_PROJECT_REF", "")
    if not project_ref:
        raise SystemExit("VAB_SUPABASE_PROJECT_REF is required.")

    import psycopg

    # Read-only at connection startup, before even the database-name query.
    def connect():
        return psycopg.connect(dsn, options="-c default_transaction_read_only=on")

    report = inspect_isolated_scheduling_database(connect, project_ref=project_ref)
    for name, passed in report["checks"].items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    for name, value in report["counts"].items():
        print(f"{name}: {value}")
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
