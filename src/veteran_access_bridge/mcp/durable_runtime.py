"""Private durable-mode routing for existing scheduling MCP tool names.

Default demo mode preserves historic in-memory fixtures. Selecting supabase_test
NEVER falls back to memory: the database's test-only connection and independently
trusted actor context are required. No database URL, assertion or role is accepted
as a public MCP parameter.
"""

from __future__ import annotations

import os
from typing import Any

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)

_DEMO = "demo"
_TEST = "supabase_test"


def scheduling_mode() -> str:
    value = os.getenv("VAB_SCHEDULING_RUNTIME_MODE", _DEMO)
    if value not in {_DEMO, _TEST}:
        raise PermissionError("Unknown scheduling runtime mode; refusing fallback")
    return value


def require_private_durable_writer() -> None:
    """Public MCP mutations cannot self-attest identity in durable mode."""
    if scheduling_mode() == _TEST:
        raise PermissionError(
            "Durable scheduling mutation requires a trusted signed actor "
            "assertion from a private server boundary; demo actor IDs are not proof"
        )


def read_case_from_supabase(
    case_id: str, *, include_history: bool = False, connect=None
) -> dict[str, Any]:
    """Read the persisted synthetic case; no merged or in-memory fallback.

    Not a general VA patient search. All SQL identifiers are literal and scoped
    to the private test schema, and the test database login cannot access vab.
    """
    if scheduling_mode() != _TEST:
        raise PermissionError("Durable read requires explicit Supabase test mode")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("A case ID is required")
    if connect is None:
        raise PermissionError(
            "Public durable case reads require independently verified actor "
            "identity and case scope from a private server boundary"
        )
    factory = connect
    with factory() as conn:
        with conn.cursor() as cur:
            schema = assert_synthetic_scheduling_database(cur, conn, write=False)
            if schema != "vab_test":
                raise PermissionError("Durable reads require the isolated test schema")
            cur.execute(
                "SELECT l.case_id,r.request_id,r.request_kind,r.requested_service,"
                "r.status,r.created_at FROM vab_test.scheduling_case_link l "
                "JOIN vab_test.appointment_request r ON l.request_id=r.request_id "
                "WHERE l.case_id=%s AND l.synthetic=true",
                (case_id,),
            )
            record = cur.fetchone()
            if record is None:
                return {
                    "case_id": case_id,
                    "found": False,
                    "synthetic": True,
                    "read_only": True,
                    "persistence": "supabase_test",
                }
            cur.execute(
                "SELECT a.appointment_id,a.status,a.slot_id "
                "FROM vab_test.appointment a "
                "WHERE a.request_id=%s ORDER BY a.confirmed_at DESC "
                "LIMIT 1",
                (record[1],),
            )
            appointment = cur.fetchone()
            cur.execute(
                "SELECT d.decision_kind,d.decision_status,d.actor_role,"
                "d.option_id,d.decision_order "
                "FROM vab_test.scheduling_decision d WHERE d.case_id=%s "
                "ORDER BY d.decision_order DESC LIMIT 1",
                (case_id,),
            )
            latest_decision = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM vab_test.scheduling_transition WHERE case_id=%s",
                (case_id,),
            )
            event_count = cur.fetchone()[0]
            history = []
            if include_history:
                cur.execute(
                    "SELECT event_type,to_state,actor_role,actor_id,"
                    "occurred_at,correlation_id "
                    "FROM vab_test.scheduling_transition WHERE case_id=%s "
                    "ORDER BY occurred_at,transition_id",
                    (case_id,),
                )
                for event in cur.fetchall():
                    (
                        event_type,
                        to_state,
                        role,
                        actor,
                        occurred_at,
                        correlation_id,
                    ) = event
                    history.append(
                        {
                            "event_type": event_type,
                            "to_state": to_state,
                            "actor_role": role,
                            "actor_id": actor,
                            "occurred_at": occurred_at.isoformat(),
                            "correlation_id": correlation_id,
                        }
                    )
    if appointment and appointment[1] == "BOOKED_SIMULATED":
        current_state = "BOOKED_SIMULATED"
    elif latest_decision and latest_decision[0] == "SCHEDULER_APPROVED":
        current_state = (
            "READY_FOR_BOOKING" if latest_decision[1] == "ACCEPTED" else "HUMAN_REVIEW"
        )
    elif latest_decision and latest_decision[0] == "VETERAN_CONFIRMED":
        current_state = (
            "PENDING_SCHEDULER_APPROVAL"
            if latest_decision[1] == "ACCEPTED"
            else "HUMAN_REVIEW"
        )
    else:
        current_state = "UNDETERMINED" if event_count else "REQUESTED"
    result = {
        "case_id": case_id,
        "found": True,
        "synthetic": True,
        "read_only": True,
        "persistence": "supabase_test",
        "current_state": current_state,
        "status_authoritative": current_state == "BOOKED_SIMULATED",
        "request_id": str(record[1]),
        "request_kind": record[2],
        "requested_service": record[3],
        "request_status": record[4],
        "created_at": record[5].isoformat(),
        "event_count": event_count,
        "booking_id": str(appointment[0]) if appointment else None,
        "booking_status": appointment[1] if appointment else None,
        "slot_id": str(appointment[2]) if appointment else None,
        "latest_decision": (
            {
                "kind": latest_decision[0],
                "status": latest_decision[1],
                "role": latest_decision[2],
                "option_id": latest_decision[3],
                "decision_order": latest_decision[4],
            }
            if latest_decision
            else None
        ),
    }
    if include_history:
        result["event_history"] = history
        result["history_order_authoritative"] = False
    return result
