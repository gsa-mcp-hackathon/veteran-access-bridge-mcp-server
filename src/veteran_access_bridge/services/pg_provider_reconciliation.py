"""Dev-only append-only synthetic provider status reconciliation.

This is deliberately a private service. It never updates a VA/EPS endpoint or
the canonical appointment status and is not registered over MCP or HTTP.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from uuid import UUID, uuid5

import jwt

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.pg_scheduling_sql import execute_scheduling_sql
from veteran_access_bridge.adapters.synthetic_ids import VAB_SYNTHETIC_NAMESPACE

ISSUER = "vab-local-synthetic-provider-authority"
AUDIENCE = "vab-synthetic-provider-reconciliation"
EVENT_TYPE = "SYNTHETIC_PROVIDER_STATUS"
ALLOWED = frozenset({"CONFIRMED", "COMPLETED", "CANCELLED", "NO_SHOW"})
TERMINAL = frozenset({"COMPLETED", "CANCELLED", "NO_SHOW"})


@dataclass(frozen=True)
class ProviderStatusReceipt:
    case_id: str
    appointment_id: str
    provider_status: str
    event_id: str
    replay: bool


def _allow_local() -> None:
    if (
        os.getenv("APP_ENV", os.getenv("VAB_ENV", "local_synthetic"))
        != "local_synthetic"
        or os.getenv("VAB_ENABLE_LOCAL_PROVIDER_RECONCILIATION") != "true"
        or os.getenv("VAB_MCP_TRANSPORT", "stdio") != "stdio"
    ):
        raise PermissionError("Local synthetic provider reconciliation disabled")


def _allow_test_database() -> None:
    if (
        os.getenv("VAB_RUN_SPRINT_A_DB_ACCEPTANCE") != "true"
        or os.getenv("VAB_SUPABASE_TEST_MODE") != "true"
        or os.getenv("VAB_ENABLE_SUPABASE_TEST_WRITES") != "true"
    ):
        raise PermissionError("Opt-in isolated provider reconciliation is disabled")


def _claims(
    assertion: str,
    *,
    secret: str,
    case_id: str,
    appointment_id: UUID,
    provider_id: str,
    status: str,
    event_key: str,
) -> dict:
    if not isinstance(secret, str) or len(secret.encode()) < 32:
        raise PermissionError("Strong provider assertion verifier secret required")
    try:
        claims = jwt.decode(
            assertion,
            secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "role", "case_id"]},
            leeway=0,
        )
    except jwt.PyJWTError as exc:
        raise PermissionError("Invalid or expired provider assertion") from exc
    if (
        claims.get("synthetic") is not True
        or claims.get("role") != "PROVIDER"
        or not isinstance(claims.get("sub"), str)
        or not claims["sub"].strip()
        or claims.get("case_id") != case_id
        or claims.get("appointment_id") != str(appointment_id)
        or claims.get("provider_id") != provider_id
        or claims.get("status") != status
        or claims.get("event_key") != event_key
    ):
        raise PermissionError("Provider assertion scope/status mismatch")
    return claims


def _record_signed_provider_status(
    connect,
    *,
    assertion: str,
    verifier_secret: str,
    case_id: str,
    appointment_id: UUID,
    provider_id: str,
    status: str,
    event_key: str,
    test_database: bool,
) -> ProviderStatusReceipt:
    """Append a signed synthetic status event with exact-identity replay rules."""
    if test_database:
        _allow_test_database()
    else:
        _allow_local()
    if (
        not isinstance(appointment_id, UUID)
        or not all(
            isinstance(value, str) and value.strip()
            for value in (case_id, provider_id, status, event_key)
        )
        or status not in ALLOWED
    ):
        raise ValueError("Complete valid synthetic provider status required")
    claims = _claims(
        assertion,
        secret=verifier_secret,
        case_id=case_id,
        appointment_id=appointment_id,
        provider_id=provider_id,
        status=status,
        event_key=event_key,
    )
    event_id = uuid5(VAB_SYNTHETIC_NAMESPACE, "provider-event:" + event_key)
    expected = {
        "synthetic": True,
        "case_id": case_id,
        "appointment_id": str(appointment_id),
        "provider_id": provider_id,
        "status": status,
        "event_key": event_key,
        "issuer": ISSUER,
    }
    with connect() as conn:
        with conn.cursor() as cur:
            if test_database:
                schema = assert_synthetic_scheduling_database(cur, conn, write=True)
                if schema != "vab_test":
                    raise PermissionError(
                        "Provider writes require the isolated test schema"
                    )
            else:
                cur.execute("SELECT current_database()")
                if cur.fetchone()[0] != "veteran_access_bridge_dev":
                    raise ValueError("Only isolated synthetic development database")
                schema = "vab"
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT s.provider_id,a.status,s.source_id "
                "FROM vab.appointment a "
                "JOIN vab.appointment_request r ON r.request_id=a.request_id "
                "JOIN vab.scheduling_case_link l ON l.request_id=r.request_id "
                "JOIN vab.slot s ON s.slot_id=a.slot_id "
                "JOIN vab.data_source d ON d.source_id=s.source_id "
                "AND d.source_kind='synthetic_fixture' "
                "WHERE a.appointment_id=%s AND l.case_id=%s "
                "AND l.synthetic=true AND a.synthetic=true AND s.channel='EPS' "
                "FOR UPDATE OF a",
                (appointment_id, case_id),
            )
            row = cur.fetchone()
            if row is None or row[0] != provider_id:
                raise ValueError("Provider appointment scope mismatch")
            _, appointment_status, source_id = row
            if appointment_status != "BOOKED_SIMULATED":
                raise ValueError("Appointment is not an active simulated booking")
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT details,correlation_id,actor,event_type,source_id "
                "FROM vab.audit_event WHERE event_id=%s",
                (event_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                if (
                    not isinstance(existing[0], dict)
                    or any(existing[0].get(k) != v for k, v in expected.items())
                    or not isinstance(existing[0].get("provider_order"), int)
                    or existing[0]["provider_order"] < 1
                    or existing[1:]
                    != (
                        event_key,
                        "synthetic-provider:" + claims["sub"],
                        EVENT_TYPE,
                        source_id,
                    )
                ):
                    raise ValueError("Conflicting provider event idempotency key")
                return ProviderStatusReceipt(
                    case_id, str(appointment_id), status, str(event_id), True
                )
            # The appointment row lock serializes all writers for this case.
            # Transaction-start occurred_at cannot order lock-waiting writers.
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT details->>'status',"
                "COALESCE((details->>'provider_order')::bigint,0) "
                "FROM vab.audit_event WHERE event_type=%s "
                "AND details->>'appointment_id'=%s "
                "ORDER BY COALESCE((details->>'provider_order')::bigint,0) "
                "DESC,occurred_at DESC,event_id DESC LIMIT 1",
                (EVENT_TYPE, str(appointment_id)),
            )
            latest = cur.fetchone()
            if latest is not None:
                prior = latest[0]
                if prior in TERMINAL or status == prior:
                    raise ValueError("Provider event would regress or repeat status")
            expected["provider_order"] = (latest[1] if latest else 0) + 1
            execute_scheduling_sql(
                cur,
                schema,
                "INSERT INTO vab.audit_event "
                "(event_id,correlation_id,actor,event_type,source_id,details) "
                "VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                (
                    event_id,
                    event_key,
                    "synthetic-provider:" + claims["sub"],
                    EVENT_TYPE,
                    source_id,
                    json.dumps(expected),
                ),
            )
        conn.commit()
    return ProviderStatusReceipt(
        case_id, str(appointment_id), status, str(event_id), False
    )


def record_signed_provider_status(
    connect,
    *,
    assertion: str,
    verifier_secret: str,
    case_id: str,
    appointment_id: UUID,
    provider_id: str,
    status: str,
    event_key: str,
) -> ProviderStatusReceipt:
    return _record_signed_provider_status(
        connect,
        assertion=assertion,
        verifier_secret=verifier_secret,
        case_id=case_id,
        appointment_id=appointment_id,
        provider_id=provider_id,
        status=status,
        event_key=event_key,
        test_database=False,
    )


def record_signed_test_provider_status(
    connect,
    *,
    assertion: str,
    verifier_secret: str,
    case_id: str,
    appointment_id: UUID,
    provider_id: str,
    status: str,
    event_key: str,
) -> ProviderStatusReceipt:
    """Append provider evidence only under the isolated opt-in test boundary."""
    return _record_signed_provider_status(
        connect,
        assertion=assertion,
        verifier_secret=verifier_secret,
        case_id=case_id,
        appointment_id=appointment_id,
        provider_id=provider_id,
        status=status,
        event_key=event_key,
        test_database=True,
    )


def _read_provider_status(
    connect, *, case_id: str, appointment_id: UUID, test_database: bool
) -> dict:
    """Fresh-connection readback: status event is never booking authority."""
    if test_database:
        _allow_test_database()
    else:
        _allow_local()
    if not isinstance(appointment_id, UUID) or not case_id:
        raise ValueError("Case and appointment identity required")
    with connect() as conn:
        with conn.cursor() as cur:
            if test_database:
                schema = assert_synthetic_scheduling_database(cur, conn, write=False)
                if schema != "vab_test":
                    raise PermissionError(
                        "Provider reads require the isolated test schema"
                    )
            else:
                cur.execute("SELECT current_database()")
                if cur.fetchone()[0] != "veteran_access_bridge_dev":
                    raise ValueError("Only isolated synthetic development database")
                schema = "vab"
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT a.status,s.provider_id,s.source_id "
                "FROM vab.appointment a "
                "JOIN vab.appointment_request r ON r.request_id=a.request_id "
                "JOIN vab.scheduling_case_link l ON l.request_id=r.request_id "
                "JOIN vab.slot s ON s.slot_id=a.slot_id "
                "JOIN vab.data_source d ON d.source_id=s.source_id "
                "AND d.source_kind='synthetic_fixture' "
                "WHERE l.case_id=%s AND a.appointment_id=%s "
                "AND l.synthetic=true AND a.synthetic=true AND s.channel='EPS'",
                (case_id, appointment_id),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError("Synthetic appointment not found for case")
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT event_id,details,correlation_id,actor,source_id,"
                "event_type,occurred_at "
                "FROM vab.audit_event WHERE event_type=%s "
                "AND details->>'appointment_id'=%s "
                "ORDER BY COALESCE((details->>'provider_order')::bigint,0) "
                "DESC,occurred_at DESC,event_id DESC LIMIT 1",
                (EVENT_TYPE, str(appointment_id)),
            )
            latest = cur.fetchone()
    if latest is not None:
        details = latest[1]
        event_key = details.get("event_key") if isinstance(details, dict) else None
        if (
            not isinstance(details, dict)
            or details.get("synthetic") is not True
            or details.get("case_id") != case_id
            or details.get("appointment_id") != str(appointment_id)
            or details.get("provider_id") != row[1]
            or details.get("issuer") != ISSUER
            or not isinstance(details.get("status"), str)
            or details.get("status") not in ALLOWED
            or type(details.get("provider_order")) is not int
            or details["provider_order"] < 1
            or not isinstance(event_key, str)
            or not event_key
            or latest[0]
            != uuid5(VAB_SYNTHETIC_NAMESPACE, "provider-event:" + event_key)
            or latest[2] != event_key
            or not isinstance(latest[3], str)
            or not latest[3].startswith("synthetic-provider:")
            or latest[3] == "synthetic-provider:"
            or latest[4] != row[2]
            or latest[5] != EVENT_TYPE
        ):
            raise ValueError("Conflicting provider audit provenance")
    return {
        "case_id": case_id,
        "appointment_id": str(appointment_id),
        "appointment_status": row[0],
        "provider_id": row[1],
        "provider_status": latest[1]["status"] if latest else "NOT_REPORTED",
        "provider_event_id": str(latest[0]) if latest else None,
        "provider_updated_at": latest[6].isoformat() if latest else None,
        "provider_order": latest[1]["provider_order"] if latest else None,
        "synthetic": True,
        "read_only": True,
        "changes_booking": False,
    }


def read_provider_status(connect, *, case_id: str, appointment_id: UUID) -> dict:
    return _read_provider_status(
        connect, case_id=case_id, appointment_id=appointment_id, test_database=False
    )


def read_test_provider_status(connect, *, case_id: str, appointment_id: UUID) -> dict:
    """Fresh-connection provider readback within the isolated test schema."""
    return _read_provider_status(
        connect, case_id=case_id, appointment_id=appointment_id, test_database=True
    )
