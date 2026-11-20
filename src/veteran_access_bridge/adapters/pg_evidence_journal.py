"""PostgreSQL evidence journal for *already validated* synthetic service outcomes.

This module does not authorize approvals, confirmations, or bookings.
Call only after the existing deterministic service has accepted a transition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid5

from veteran_access_bridge.adapters.synthetic_ids import VAB_SYNTHETIC_NAMESPACE

_ALLOWED_EVENTS = frozenset(
    {
        "OPTION_SELECTED",
        "VETERAN_CONFIRMATION_RECORDED",
        "SCHEDULER_REVIEW_RECORDED",
        "HUMAN_HANDOFF",
    }
)


@dataclass(frozen=True)
class ValidatedTransition:
    case_id: str
    event_type: str
    from_state: str | None
    to_state: str
    actor_role: str
    actor_id: str
    idempotency_key: str
    correlation_id: str
    evidence_reference: str


def persist_validated_transition(conn, event: ValidatedTransition) -> bool:
    """Journal a prior service result; return False on identical replay.

    Caller owns the transaction. A conflicting key fails closed.
    This low-level writer cannot itself verify an external approval.
    """
    if event.event_type not in _ALLOWED_EVENTS:
        raise ValueError("Unsupported evidence event")
    if event.actor_role not in {"VETERAN", "SCHEDULER", "SYSTEM"}:
        raise ValueError("Unsupported actor role")
    if not all(
        (
            event.case_id,
            event.to_state,
            event.actor_id,
            event.idempotency_key,
            event.correlation_id,
            event.evidence_reference,
        )
    ):
        raise ValueError("Evidence journal fields must be nonempty")
    if event.event_type == "VETERAN_CONFIRMATION_RECORDED":
        if event.actor_role != "VETERAN":
            raise ValueError("Veteran confirmation requires Veteran actor")
    if event.event_type == "SCHEDULER_REVIEW_RECORDED":
        if event.actor_role != "SCHEDULER":
            raise ValueError("Scheduler review requires Scheduler actor")

    evidence = {"service_evidence_reference": event.evidence_reference}
    event_id = uuid5(VAB_SYNTHETIC_NAMESPACE, "transition:" + event.idempotency_key)
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        if not cur.fetchone()[0].endswith("_dev"):
            raise ValueError("Evidence writes require a development database")
        cur.execute(
            "INSERT INTO vab.scheduling_transition "
            "(transition_id, case_id, event_type, from_state, to_state, "
            "actor_role, actor_id, idempotency_key, correlation_id, evidence) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) "
            "ON CONFLICT (idempotency_key) DO NOTHING RETURNING transition_id",
            (
                str(event_id),
                event.case_id,
                event.event_type,
                event.from_state,
                event.to_state,
                event.actor_role,
                event.actor_id,
                event.idempotency_key,
                event.correlation_id,
                json.dumps(evidence),
            ),
        )
        if cur.fetchone() is not None:
            return True
        cur.execute(
            "SELECT case_id,event_type,from_state,to_state,actor_role,"
            "actor_id,correlation_id,evidence "
            "FROM vab.scheduling_transition WHERE idempotency_key=%s",
            (event.idempotency_key,),
        )
        row = cur.fetchone()
        expected = (
            event.case_id,
            event.event_type,
            event.from_state,
            event.to_state,
            event.actor_role,
            event.actor_id,
            event.correlation_id,
            evidence,
        )
        if row is None or tuple(row) != expected:
            raise ValueError("Conflicting transition idempotency key")
        return False
