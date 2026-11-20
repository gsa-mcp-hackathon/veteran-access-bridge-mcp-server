"""Trusted local synthetic approval persistence (not exposed via MCP/HTTP).

A separately trusted issuer must create short-lived, case-scoped assertions.
No demo persona header, actor ID parameter, or browser-supplied claim is trusted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid5

import jwt

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.pg_scheduling_sql import execute_scheduling_sql
from veteran_access_bridge.adapters.synthetic_ids import VAB_SYNTHETIC_NAMESPACE

ISSUER = "vab-local-scheduler-authority"
AUDIENCE = "vab-synthetic-eps-booking"

DECISIONS = {
    "VETERAN": ("VETERAN_CONFIRMED", "VETERAN_CONFIRMATION_RECORDED"),
    "SCHEDULER": ("SCHEDULER_APPROVED", "SCHEDULER_REVIEW_RECORDED"),
}


@dataclass(frozen=True)
class DecisionReceipt:
    case_id: str
    option_id: str
    actor_role: str
    status: str
    decision_id: str
    transition_id: str
    idempotent_replay: bool


def _trusted_claims(assertion: str, secret: str, case_id: str) -> dict:
    if not isinstance(secret, str) or len(secret.encode()) < 32:
        raise PermissionError("Trusted assertion verifier secret required")
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
        raise PermissionError("Invalid or expired actor assertion") from exc
    if (
        claims.get("synthetic") is not True
        or claims.get("case_id") != case_id
        or claims.get("role") not in DECISIONS
        or not isinstance(claims.get("sub"), str)
        or not claims["sub"].strip()
    ):
        raise PermissionError("Actor assertion case/role/provenance mismatch")
    return claims


def _persist_signed_scheduling_decision(
    connect,
    *,
    assertion: str,
    verifier_secret: str,
    case_id: str,
    option_id: str,
    idempotency_key: str,
    correlation_id: str,
    service_evidence_reference: str,
    allowed_channels: tuple[str, ...],
    accepted: bool = True,
) -> DecisionReceipt:
    """Atomically persist signed actor decision plus its matching transition.

    Only signed, explicitly issued local synthetic assertions are accepted.
    This is a private service, not an MCP endpoint or credential issuer.
    """
    values = (case_id, option_id, idempotency_key, correlation_id)
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError("Case, option, idempotency and correlation required")
    if (
        not isinstance(service_evidence_reference, str)
        or not service_evidence_reference.strip()
    ):
        raise ValueError("Validated service evidence reference required")
    claims = _trusted_claims(assertion, verifier_secret, case_id)
    role = claims["role"]
    kind, event_type = DECISIONS[role]
    actor = claims["sub"]
    status = "ACCEPTED" if accepted else "REJECTED"
    decision_id = uuid5(VAB_SYNTHETIC_NAMESPACE, "signed-decision:" + idempotency_key)
    transition_id = uuid5(
        VAB_SYNTHETIC_NAMESPACE, "signed-transition:" + idempotency_key
    )
    evidence = json.dumps(
        {
            "synthetic": True,
            "service_evidence_reference": service_evidence_reference,
            "trusted_issuer": ISSUER,
            "assertion_subject": actor,
        }
    )
    with connect() as conn:
        with conn.cursor() as cur:
            schema = assert_synthetic_scheduling_database(cur, conn, write=True)
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT l.request_id FROM vab.scheduling_case_link l "
                "WHERE l.case_id=%s AND l.synthetic=true FOR UPDATE OF l",
                (case_id,),
            )
            if cur.fetchone() is None:
                raise ValueError("Synthetic scheduling case not found")
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT EXISTS ("
                "SELECT 1 FROM vab.slot s "
                "JOIN vab.data_source d ON d.source_id=s.source_id "
                "WHERE d.source_kind='synthetic_fixture' "
                "AND s.channel = ANY(%s) "
                "AND d.provenance->'slot_bindings'->(s.slot_id::text)"
                "->>'case_id'=%s "
                "AND d.provenance->'slot_bindings'->(s.slot_id::text)"
                "->>'option_id'=%s AND d.source_id=%s)",
                (
                    list(allowed_channels),
                    case_id,
                    option_id,
                    service_evidence_reference,
                ),
            )
            if not cur.fetchone()[0]:
                raise ValueError(
                    "Option or evidence not owned by synthetic scheduling case"
                )
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT decision_id,case_id,option_id,decision_kind,"
                "decision_status,actor_role,actor_id,correlation_id,evidence "
                "FROM vab.scheduling_decision "
                "WHERE idempotency_key=%s FOR UPDATE",
                (idempotency_key,),
            )
            prior = cur.fetchone()
            expected = (
                decision_id,
                case_id,
                option_id,
                kind,
                status,
                role,
                actor,
                correlation_id,
            )
            if prior is not None:
                if (
                    tuple(prior[:8]) != expected
                    or prior[8].get("service_evidence_reference")
                    != service_evidence_reference
                ):
                    raise ValueError("Conflicting signed decision replay")
                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT transition_id,case_id,event_type,actor_role,"
                    "actor_id,correlation_id,evidence "
                    "FROM vab.scheduling_transition "
                    "WHERE idempotency_key=%s",
                    (idempotency_key,),
                )
                event = cur.fetchone()
                if (
                    event is None
                    or event[:6]
                    != (
                        transition_id,
                        case_id,
                        event_type,
                        role,
                        actor,
                        correlation_id,
                    )
                    or event[6].get("service_evidence_reference")
                    != service_evidence_reference
                ):
                    raise ValueError("Missing or conflicting paired transition")
                return DecisionReceipt(
                    case_id,
                    option_id,
                    role,
                    status,
                    str(decision_id),
                    str(transition_id),
                    True,
                )
            if role == "SCHEDULER" and accepted:
                # The latest Veteran decision supersedes historical approvals.
                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT d.decision_status,d.option_id,d.actor_id,d.evidence,"
                    "e.transition_id,e.event_type,e.actor_role,e.actor_id,e.evidence "
                    "FROM vab.scheduling_decision d "
                    "LEFT JOIN vab.scheduling_transition e "
                    "ON e.case_id=d.case_id "
                    "AND e.idempotency_key=d.idempotency_key "
                    "AND e.correlation_id=d.correlation_id "
                    "WHERE d.case_id=%s "
                    "AND d.decision_kind='VETERAN_CONFIRMED' "
                    "AND d.actor_role='VETERAN' "
                    "ORDER BY d.decision_order DESC LIMIT 1",
                    (case_id,),
                )
                veteran = cur.fetchone()
                if (
                    veteran is None
                    or veteran[0] != "ACCEPTED"
                    or veteran[1] != option_id
                    or veteran[4] is None
                    or veteran[5] != "VETERAN_CONFIRMATION_RECORDED"
                    or veteran[6] != "VETERAN"
                    or veteran[7] != veteran[2]
                    or not isinstance(veteran[3], dict)
                    or not isinstance(veteran[8], dict)
                    or not veteran[3].get("service_evidence_reference")
                    or veteran[8] != veteran[3]
                ):
                    raise ValueError("Current Veteran confirmation required")
            execute_scheduling_sql(
                cur,
                schema,
                "INSERT INTO vab.scheduling_decision "
                "(decision_id,case_id,option_id,decision_kind,decision_status,"
                "actor_role,actor_id,idempotency_key,correlation_id,evidence) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                (
                    decision_id,
                    case_id,
                    option_id,
                    kind,
                    status,
                    role,
                    actor,
                    idempotency_key,
                    correlation_id,
                    evidence,
                ),
            )
            execute_scheduling_sql(
                cur,
                schema,
                "INSERT INTO vab.scheduling_transition "
                "(transition_id,case_id,event_type,to_state,actor_role,"
                "actor_id,idempotency_key,correlation_id,evidence) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                (
                    transition_id,
                    case_id,
                    event_type,
                    "PENDING_SCHEDULER_APPROVAL"
                    if role == "VETERAN" and accepted
                    else "READY_FOR_BOOKING"
                    if role == "SCHEDULER" and accepted
                    else "HUMAN_REVIEW",
                    role,
                    actor,
                    idempotency_key,
                    correlation_id,
                    evidence,
                ),
            )
        conn.commit()
    return DecisionReceipt(
        case_id,
        option_id,
        role,
        status,
        str(decision_id),
        str(transition_id),
        False,
    )


def persist_signed_scheduling_decision(
    connect,
    *,
    assertion: str,
    verifier_secret: str,
    case_id: str,
    option_id: str,
    idempotency_key: str,
    correlation_id: str,
    service_evidence_reference: str,
    accepted: bool = True,
) -> DecisionReceipt:
    """Persist signed Community Care decisions against EPS-bound options."""
    return _persist_signed_scheduling_decision(
        connect,
        assertion=assertion,
        verifier_secret=verifier_secret,
        case_id=case_id,
        option_id=option_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        service_evidence_reference=service_evidence_reference,
        allowed_channels=("EPS",),
        accepted=accepted,
    )


def persist_signed_va_scheduling_decision(
    connect,
    *,
    assertion: str,
    verifier_secret: str,
    case_id: str,
    option_id: str,
    idempotency_key: str,
    correlation_id: str,
    service_evidence_reference: str,
    accepted: bool = True,
) -> DecisionReceipt:
    """Persist signed internal-VA decisions without admitting EPS slots."""
    return _persist_signed_scheduling_decision(
        connect,
        assertion=assertion,
        verifier_secret=verifier_secret,
        case_id=case_id,
        option_id=option_id,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        service_evidence_reference=service_evidence_reference,
        allowed_channels=("VISTA", "FEDERAL_EHR"),
        accepted=accepted,
    )
