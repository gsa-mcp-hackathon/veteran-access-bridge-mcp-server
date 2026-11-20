"""Private durable synthetic INTERNAL VA booking (VistA/Federal EHR only).

Reuses the existing vab_test case, slot, appointment, decision and audit schema.
This is NOT an MCP tool or HTTP route. It never talks to real VA, EPS or HSRM.
An independently authenticated trusted host must issue narrowly scoped service
assertions; this module intentionally provides no issuer or token minting.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid5

import jwt

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.pg_scheduling_sql import execute_scheduling_sql
from veteran_access_bridge.adapters.synthetic_ids import (
    VAB_SYNTHETIC_NAMESPACE,
    persistent_uuid,
)

ISSUER = "vab-trusted-host"
AUDIENCE = "vab-synthetic-internal-va-booking"
SCOPE = "va_primary_care:book"
VA_CHANNELS = ("VISTA", "FEDERAL_EHR")
POLICY_VERSION = "INTERNAL_VA_PRIMARY_CARE_AUTONOMOUS_V2"


@dataclass(frozen=True)
class VABookingRequest:
    case_id: str
    option_id: str
    slot_id: UUID
    idempotency_key: str


@dataclass(frozen=True)
class VABookingReceipt:
    state: str
    case_id: str
    appointment_id: str | None
    begins_at: datetime | None
    ends_at: datetime | None
    verified: bool
    voice_session_id: str | None = None
    clinic_name: str | None = None
    provider_name: str | None = None


def _validate_voice_session_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise PermissionError("Invalid trusted voice session binding")
    return value


def _require_voice_evidence(cur, schema, request, claims, *, lock=False):
    """Recheck persisted call evidence; this does not authenticate a LiveKit caller."""
    if "voice_session_id" not in claims:
        return
    call_id = _validate_voice_session_id(claims["voice_session_id"])
    execute_scheduling_sql(
        cur,
        schema,
        "SELECT i.correlation_id,d.correlation_id,t.correlation_id "
        "FROM vab.audit_event i "
        "JOIN vab.scheduling_decision d ON d.case_id=%s "
        "JOIN vab.scheduling_transition t ON t.case_id=d.case_id "
        "AND t.idempotency_key=d.idempotency_key "
        "AND t.correlation_id=d.correlation_id "
        "WHERE i.event_id=%s AND i.event_type='SYNTHETIC_IDENTITY_VERIFICATION' "
        "AND i.details->>'case_id'=%s AND i.actor=%s "
        "AND i.details->>'verified'='true' AND i.details->>'outcome'='VERIFIED' "
        "AND d.decision_id=%s AND d.option_id=%s "
        "AND d.decision_kind='VETERAN_CONFIRMED' "
        "AND d.decision_status='ACCEPTED' AND d.actor_role='VETERAN' "
        "AND t.event_type='VETERAN_CONFIRMATION_RECORDED' "
        "AND t.actor_role=d.actor_role AND t.actor_id=d.actor_id "
        "AND t.evidence=d.evidence" + (" FOR SHARE OF i,d,t" if lock else ""),
        (
            request.case_id,
            claims["identity_verification_id"],
            request.case_id,
            claims["sub"],
            claims["veteran_confirmation_id"],
            request.option_id,
        ),
    )
    row = cur.fetchone()
    if row is None or tuple(row) != (call_id,) * 3:
        raise PermissionError("Identity and consent must belong to the signed call")


def _verified_booking_claims(
    assertion: str, secret: str, request: VABookingRequest
) -> dict:
    """Verify trusted-host service authority; never trust a caller's actor header."""
    if not isinstance(secret, str) or len(secret.encode()) < 32:
        raise PermissionError("Protected verifier configuration required")
    if not isinstance(request, VABookingRequest):
        raise TypeError("Typed internal VA booking request required")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (request.case_id, request.option_id, request.idempotency_key)
    ) or not isinstance(request.slot_id, UUID):
        raise ValueError("Complete internal VA booking identity required")
    try:
        claims = jwt.decode(
            assertion,
            secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={
                "require": [
                    "exp",
                    "iat",
                    "iss",
                    "aud",
                    "sub",
                    "role",
                    "scope",
                    "case_id",
                    "option_id",
                    "slot_id",
                    "synthetic",
                    "jti",
                    "idempotency_key",
                    "identity_verified",
                    "identity_case_id",
                    "identity_verification_id",
                    "identity_verification_expires_at",
                    "veteran_confirmation_id",
                    "policy_version",
                    "policy_decision",
                    "policy_evidence_reference",
                    "human_review_required",
                ]
            },
            leeway=0,
        )
    except jwt.PyJWTError as exc:
        raise PermissionError("Invalid trusted booking assertion") from exc
    confirmation_id = claims.get("veteran_confirmation_id")
    try:
        parsed_confirmation_id = UUID(confirmation_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise PermissionError("Trusted grant must bind a Veteran confirmation") from exc
    if str(parsed_confirmation_id) != confirmation_id:
        raise PermissionError("Trusted grant Veteran confirmation ID is invalid")
    actor = claims.get("sub")
    if (
        not isinstance(actor, str)
        or not actor.strip()
        or claims.get("role") != "SERVICE"
        or claims.get("scope") != SCOPE
        or claims.get("case_id") != request.case_id
        or claims.get("option_id") != request.option_id
        or claims.get("slot_id") != str(request.slot_id)
        or claims.get("synthetic") is not True
        or claims.get("idempotency_key") != request.idempotency_key
        or claims.get("identity_verified") is not True
        or claims.get("identity_case_id") != request.case_id
        or not isinstance(claims.get("identity_verification_id"), str)
        or not claims["identity_verification_id"].strip()
        or type(claims.get("identity_verification_expires_at")) is not int
        or claims["identity_verification_expires_at"] <= int(time.time())
        or claims.get("policy_version") != POLICY_VERSION
        or claims.get("policy_decision") != "ALLOW"
        or claims.get("human_review_required") is not False
        or not isinstance(claims.get("policy_evidence_reference"), str)
        or not claims["policy_evidence_reference"].strip()
        or not isinstance(claims.get("jti"), str)
        or not claims["jti"].strip()
        or claims["exp"] - claims["iat"] > 120
    ):
        raise PermissionError("Trusted service booking scope mismatch")
    if "voice_session_id" in claims:
        _validate_voice_session_id(claims["voice_session_id"])
    return claims


def _verified_machine_actor(
    assertion: str, secret: str, request: VABookingRequest
) -> str:
    """Return the service subject only after validating the complete booking grant."""
    return _verified_booking_claims(assertion, secret, request)["sub"]


def _verified_decision_row(
    row,
    *,
    expected_kind: str,
    expected_event: str,
    expected_role: str,
    expected_option_id: str,
):
    if row is None:
        return None
    (
        decision_id,
        status,
        option_id,
        kind,
        actor_role,
        actor_id,
        decision_order,
        decision_evidence,
        transition_id,
        event_type,
        transition_role,
        transition_actor,
        transition_evidence,
    ) = row
    evidence_ref = (
        decision_evidence.get("service_evidence_reference")
        if isinstance(decision_evidence, dict)
        else None
    )
    if (
        status != "ACCEPTED"
        or option_id != expected_option_id
        or kind != expected_kind
        or actor_role != expected_role
        or not isinstance(actor_id, str)
        or not actor_id.strip()
        or not isinstance(decision_order, int)
        or transition_id is None
        or event_type != expected_event
        or transition_role != expected_role
        or transition_actor != actor_id
        or not evidence_ref
        or transition_evidence != decision_evidence
    ):
        return None
    return decision_id, decision_order, actor_id


def _ids(request: VABookingRequest) -> tuple[UUID, UUID, UUID]:
    return (
        persistent_uuid("appointment", request.idempotency_key),
        uuid5(
            VAB_SYNTHETIC_NAMESPACE, "va-booking-transition:" + request.idempotency_key
        ),
        uuid5(VAB_SYNTHETIC_NAMESPACE, "va-booking-audit:" + request.idempotency_key),
    )


def _readback(conn, request: VABookingRequest, claims: dict) -> VABookingReceipt:
    appointment_id, transition_id, audit_id = _ids(request)
    actor = claims["sub"]
    with conn.cursor() as cur:
        schema = assert_synthetic_scheduling_database(cur, conn, write=False)
        # Explicitly segregate from the operational knowledge base and EPS.
        if schema != "vab_test":
            raise PermissionError(
                "Only the isolated synthetic VA test schema is allowed"
            )
        execute_scheduling_sql(
            cur,
            schema,
            "SELECT a.appointment_id, a.status, a.approved_by, a.slot_id, "
            "s.channel,s.status,s.begins_at,s.ends_at,l.case_id,r.request_kind, "
            "r.patient_id,a.patient_id,c.name,"
            "c.rules->'provider_names'->>s.provider_id "
            "FROM vab.appointment a "
            "JOIN vab.slot s ON s.slot_id=a.slot_id "
            "LEFT JOIN vab.clinic c ON c.clinic_id=s.clinic_id "
            "JOIN vab.appointment_request r ON r.request_id=a.request_id "
            "JOIN vab.scheduling_case_link l ON l.request_id=r.request_id "
            "WHERE a.idempotency_key=%s",
            (request.idempotency_key,),
        )
        row = cur.fetchone()
        if row is None:
            return VABookingReceipt(
                "NOT_FOUND_UNCONFIRMED", request.case_id, None, None, None, False
            )
        (
            aid,
            status,
            approved_by,
            slot_id,
            channel,
            slot_status,
            begins,
            ends,
            case_id,
            kind,
            request_patient,
            booked_patient,
            clinic_name,
            provider_name,
        ) = row
        if (
            aid != appointment_id
            or status != "BOOKED_SIMULATED"
            or slot_id != request.slot_id
            or channel not in VA_CHANNELS
            or slot_status != "BOOKED"
            or case_id != request.case_id
            or kind != "PRIMARY_CARE"
            or request_patient != booked_patient
        ):
            raise ValueError(
                "Internal VA booking receipt conflicts with persisted state"
            )
        execute_scheduling_sql(
            cur,
            schema,
            "SELECT evidence,actor_id FROM vab.scheduling_transition "
            "WHERE transition_id=%s AND event_type='BOOKED_SIMULATED'",
            (transition_id,),
        )
        transition = cur.fetchone()
        execute_scheduling_sql(
            cur,
            schema,
            "SELECT details,actor FROM vab.audit_event "
            "WHERE event_id=%s AND event_type='BOOKED_SIMULATED'",
            (audit_id,),
        )
        audit = cur.fetchone()
        evidence = transition[0] if transition is not None else None
        expected = {
            "synthetic": True,
            "care_pathway": "INTERNAL_VA",
            "appointment_id": str(appointment_id),
            "case_id": request.case_id,
            "option_id": request.option_id,
            "slot_id": str(request.slot_id),
            "idempotency_key": request.idempotency_key,
            "service_actor": actor,
            "identity_verified": True,
            "identity_case_id": request.case_id,
            "identity_verification_id": claims["identity_verification_id"],
            "identity_verification_expires_at": claims[
                "identity_verification_expires_at"
            ],
            "policy_version": POLICY_VERSION,
            "scheduler_approval_required": False,
            "authorization_mode": "TRUSTED_SERVICE_POLICY_GRANT",
            "policy_decision": "ALLOW",
            "policy_evidence_reference": claims["policy_evidence_reference"],
            "human_review_required": False,
            "veteran_confirmation_id": claims["veteran_confirmation_id"],
            "channel": channel,
        }
        if "voice_session_id" in claims:
            expected["voice_session_id"] = claims["voice_session_id"]
        if isinstance(evidence, dict) and evidence.get(
            "voice_session_id"
        ) != claims.get("voice_session_id"):
            raise PermissionError("Recovery requires the original signed call binding")
        if (
            transition is None
            or audit is None
            or transition[1] != actor
            or audit[1] != actor
            or not isinstance(transition[0], dict)
            or any(transition[0].get(key) != value for key, value in expected.items())
            or audit[0] != transition[0]
            or not isinstance(transition[0].get("service_assertion_id"), str)
            or not transition[0]["service_assertion_id"].strip()
            or not isinstance(evidence.get("veteran_confirmation_id"), str)
            or approved_by != actor
        ):
            raise ValueError("Internal VA booking lacks matching atomic audit evidence")
        try:
            veteran_decision_id = UUID(evidence["veteran_confirmation_id"])
        except ValueError as exc:
            raise ValueError(
                "Internal VA booking decision evidence is invalid"
            ) from exc
        execute_scheduling_sql(
            cur,
            schema,
            "SELECT d.decision_id,d.decision_status,d.option_id,d.decision_kind,"
            "d.actor_role,d.actor_id,d.decision_order,d.evidence,t.transition_id,"
            "t.event_type,t.actor_role,t.actor_id,t.evidence "
            "FROM vab.scheduling_decision d "
            "JOIN vab.scheduling_transition t ON t.case_id=d.case_id "
            "AND t.idempotency_key=d.idempotency_key "
            "AND t.correlation_id=d.correlation_id "
            "WHERE d.decision_id = ANY(%s)",
            ([veteran_decision_id],),
        )
        decisions = {str(row[0]): row for row in cur.fetchall()}
        veteran_decision = _verified_decision_row(
            decisions.get(str(veteran_decision_id)),
            expected_kind="VETERAN_CONFIRMED",
            expected_event="VETERAN_CONFIRMATION_RECORDED",
            expected_role="VETERAN",
            expected_option_id=request.option_id,
        )
        if veteran_decision is None:
            raise ValueError("Internal VA booking has no verified Veteran consent")
        _require_voice_evidence(cur, schema, request, claims)
        return VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            str(aid),
            begins,
            ends,
            True,
            voice_session_id=claims.get("voice_session_id"),
            clinic_name=clinic_name,
            provider_name=provider_name,
        )


def readback_internal_va_booking(
    connect, *, assertion: str, verifier_secret: str, request: VABookingRequest
) -> VABookingReceipt:
    """Read-only recovery with the original case/option/slot-bound trusted actor."""
    claims = _verified_booking_claims(assertion, verifier_secret, request)
    with connect() as conn:
        return _readback(conn, request, claims)


def commit_internal_va_booking(
    connect, *, assertion: str, verifier_secret: str, request: VABookingRequest
) -> VABookingReceipt:
    """One atomic VA booking submission; uncertain outcomes require readback, not retry.

    Consent must have been persisted by the authenticated Veteran path. This
    service cannot mint consent, identity assertions or scheduling authority.
    """
    claims = _verified_booking_claims(assertion, verifier_secret, request)
    actor = claims["sub"]
    appointment_id, transition_id, audit_id = _ids(request)
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                schema = assert_synthetic_scheduling_database(cur, conn, write=True)
                if schema != "vab_test":
                    raise PermissionError(
                        "Only the isolated synthetic VA test schema is writable"
                    )
                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT l.request_id,r.patient_id,r.request_kind,r.status,"
                    "r.requested_service,"
                    "p.synthetic FROM vab.scheduling_case_link l "
                    "JOIN vab.appointment_request r ON r.request_id=l.request_id "
                    "JOIN vab.patient p ON p.patient_id=r.patient_id "
                    "WHERE l.case_id=%s AND l.synthetic=true FOR UPDATE OF l",
                    (request.case_id,),
                )
                case = cur.fetchone()
                if case is None or case[2] != "PRIMARY_CARE" or case[5] is not True:
                    raise ValueError("Active synthetic VA Primary Care case required")
                request_id, patient_id = case[:2]

                # Recover receipts even if availability or consent later changes.
                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT appointment_id FROM vab.appointment "
                    "WHERE idempotency_key=%s",
                    (request.idempotency_key,),
                )
                if cur.fetchone() is not None:
                    receipt = _readback(conn, request, claims)
                    if not receipt.verified:
                        raise ValueError("Conflicting prior booking")
                    return receipt

                if case[3] not in ("OPEN", "OPTIONS"):
                    raise ValueError("Active synthetic VA Primary Care case required")

                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT appointment_id FROM vab.appointment "
                    "WHERE request_id=%s AND status='BOOKED_SIMULATED' LIMIT 1",
                    (request_id,),
                )
                if cur.fetchone() is not None:
                    raise ValueError("Primary Care request already booked")

                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT s.channel,s.status,s.begins_at,s.ends_at,s.verified_at,"
                    "s.source_id,c.specialty,c.active "
                    "FROM vab.slot s JOIN vab.clinic c ON c.clinic_id=s.clinic_id "
                    "WHERE s.slot_id=%s FOR UPDATE OF s",
                    (request.slot_id,),
                )
                slot = cur.fetchone()
                if slot is None:
                    raise ValueError("Selected internal VA slot not found")
                (
                    channel,
                    status,
                    begins,
                    ends,
                    verified_at,
                    source_id,
                    specialty,
                    active,
                ) = slot
                if channel not in VA_CHANNELS or status != "AVAILABLE" or not active:
                    raise ValueError("Selected VA slot unavailable or not internal VA")
                if specialty.strip().upper() != case[4].strip().upper():
                    raise ValueError(
                        "VA clinic service does not match Primary Care request"
                    )

                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT source_kind,provenance FROM vab.data_source "
                    "WHERE source_id=%s",
                    (source_id,),
                )
                origin = cur.fetchone()
                binding = None
                if origin is not None and isinstance(origin[1], dict):
                    bindings = origin[1].get("slot_bindings")
                    if isinstance(bindings, dict):
                        binding = bindings.get(str(request.slot_id))
                if (
                    origin is None
                    or origin[0] != "synthetic_fixture"
                    or not isinstance(binding, dict)
                    or binding.get("case_id") != request.case_id
                    or binding.get("option_id") != request.option_id
                ):
                    raise ValueError(
                        "Synthetic VA slot provenance and case/option binding required"
                    )

                execute_scheduling_sql(cur, schema, "SELECT clock_timestamp()", None)
                now = cur.fetchone()[0]
                if (
                    now.timestamp() >= claims["exp"]
                    or now.timestamp() >= claims["identity_verification_expires_at"]
                ):
                    raise PermissionError(
                        "Booking authority expired while awaiting lock"
                    )
                if (
                    verified_at is None
                    or verified_at > now
                    or verified_at < now - timedelta(minutes=15)
                    or begins <= now
                    or ends <= begins
                ):
                    raise ValueError(
                        "VA slot availability is stale or appointment time invalid"
                    )

                # The latest case-wide Veteran decision must be paired and accepted.
                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT d.decision_id,d.decision_status,d.option_id,"
                    "d.decision_kind,d.actor_role,d.actor_id,d.decision_order,d.evidence,"
                    "t.transition_id,t.event_type,t.actor_role,t.actor_id,t.evidence "
                    "FROM vab.scheduling_decision d "
                    "LEFT JOIN vab.scheduling_transition t ON t.case_id=d.case_id "
                    "AND t.idempotency_key=d.idempotency_key "
                    "AND t.correlation_id=d.correlation_id "
                    "WHERE d.case_id=%s "
                    "AND d.decision_kind='VETERAN_CONFIRMED' "
                    "AND d.actor_role='VETERAN' "
                    "ORDER BY d.decision_order DESC LIMIT 1",
                    (request.case_id,),
                )
                veteran_decision = _verified_decision_row(
                    cur.fetchone(),
                    expected_kind="VETERAN_CONFIRMED",
                    expected_event="VETERAN_CONFIRMATION_RECORDED",
                    expected_role="VETERAN",
                    expected_option_id=request.option_id,
                )
                if veteran_decision is None:
                    raise ValueError(
                        "Latest verified Veteran consent must match selected VA option"
                    )
                if str(veteran_decision[0]) != claims["veteran_confirmation_id"]:
                    raise ValueError(
                        "Latest Veteran confirmation differs from confirmation "
                        "evaluated by policy grant"
                    )

                _require_voice_evidence(cur, schema, request, claims, lock=True)
                # The independently trusted host signs an explicit policy ALLOW
                # decision after its own authentication and deterministic policy
                # evaluation. This service enforces primary care, synthetic
                # provenance, case/option/slot, freshness and current consent.
                # An unresolved exception must result in human_review_required
                # rather than a booking grant. No Scheduler is impersonated.
                if claims["human_review_required"] is not False:
                    raise PermissionError("Human-review case cannot be auto-booked")

                evidence = {
                    "synthetic": True,
                    "care_pathway": "INTERNAL_VA",
                    "appointment_id": str(appointment_id),
                    "case_id": request.case_id,
                    "option_id": request.option_id,
                    "slot_id": str(request.slot_id),
                    "idempotency_key": request.idempotency_key,
                    "service_actor": actor,
                    "service_assertion_id": claims["jti"],
                    "identity_verified": True,
                    "identity_case_id": request.case_id,
                    "identity_verification_id": claims["identity_verification_id"],
                    "identity_verification_expires_at": claims[
                        "identity_verification_expires_at"
                    ],
                    "policy_version": POLICY_VERSION,
                    "scheduler_approval_required": False,
                    "authorization_mode": "TRUSTED_SERVICE_POLICY_GRANT",
                    "policy_decision": "ALLOW",
                    "policy_evidence_reference": claims["policy_evidence_reference"],
                    "human_review_required": False,
                    "veteran_confirmation_id": claims["veteran_confirmation_id"],
                    "channel": channel,
                    "slot_source_id": source_id,
                }
                if "voice_session_id" in claims:
                    evidence["voice_session_id"] = claims["voice_session_id"]
                execute_scheduling_sql(
                    cur,
                    schema,
                    "UPDATE vab.slot SET status='BOOKED' WHERE slot_id=%s "
                    "AND channel IN ('VISTA','FEDERAL_EHR') AND status='AVAILABLE'",
                    (request.slot_id,),
                )
                if cur.rowcount != 1:
                    raise ValueError("VA slot was concurrently taken")
                execute_scheduling_sql(
                    cur,
                    schema,
                    "INSERT INTO vab.appointment "
                    "(appointment_id,patient_id,request_id,slot_id,status,"
                    "idempotency_key,approved_by) "
                    "VALUES (%s,%s,%s,%s,'BOOKED_SIMULATED',%s,%s)",
                    (
                        appointment_id,
                        patient_id,
                        request_id,
                        request.slot_id,
                        request.idempotency_key,
                        actor,
                    ),
                )
                execute_scheduling_sql(
                    cur,
                    schema,
                    "INSERT INTO vab.scheduling_transition "
                    "(transition_id,case_id,event_type,to_state,actor_role,actor_id,"
                    "idempotency_key,correlation_id,evidence) "
                    "VALUES (%s,%s,'BOOKED_SIMULATED','BOOKED_SIMULATED','SYSTEM',"
                    "%s,%s,%s,%s::jsonb)",
                    (
                        transition_id,
                        request.case_id,
                        actor,
                        "va-booking:" + request.idempotency_key,
                        request.idempotency_key,
                        json.dumps(evidence),
                    ),
                )
                execute_scheduling_sql(
                    cur,
                    schema,
                    "INSERT INTO vab.audit_event "
                    "(event_id,correlation_id,actor,event_type,source_id,details) "
                    "VALUES (%s,%s,%s,'BOOKED_SIMULATED',%s,%s::jsonb)",
                    (
                        audit_id,
                        request.idempotency_key,
                        actor,
                        source_id,
                        json.dumps(evidence),
                    ),
                )
        # A new connection, after commit, establishes the actual booking result.
    except (ValueError, PermissionError, TypeError):
        raise
    except Exception:
        return VABookingReceipt(
            "RECOVERY_REQUIRED", request.case_id, None, None, None, False
        )

    try:
        receipt = readback_internal_va_booking(
            connect,
            assertion=assertion,
            verifier_secret=verifier_secret,
            request=request,
        )
    except Exception:
        return VABookingReceipt(
            "RECOVERY_REQUIRED", request.case_id, None, None, None, False
        )
    if not receipt.verified:
        return VABookingReceipt(
            "RECOVERY_REQUIRED", request.case_id, None, None, None, False
        )
    return receipt
