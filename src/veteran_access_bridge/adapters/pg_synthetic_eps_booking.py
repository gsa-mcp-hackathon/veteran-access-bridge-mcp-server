"""Dev-only, caller-transaction synthetic EPS booking with persisted HSRM evidence.

No VA/WellHive network calls. Does NOT authenticate actors; the caller must.
Only accepts explicit synthetic records already in the isolated dev database.
The caller owns commit/rollback; a return value is NOT durable acknowledgment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID, uuid5

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.pg_scheduling_sql import execute_scheduling_sql
from veteran_access_bridge.adapters.synthetic_ids import (
    VAB_SYNTHETIC_NAMESPACE,
    persistent_uuid,
)


@dataclass(frozen=True)
class EPSBookingRequest:
    case_id: str
    option_id: str
    slot_id: UUID
    authorization_id: UUID
    idempotency_key: str
    scheduler_actor_id: str


def commit_synthetic_eps_booking(conn, request: EPSBookingRequest) -> UUID:
    """Book a bound EPS slot after verifying consent, approval and HSRM.

    The authorization evidence must explicitly bind the case, option, slot and
    provider and identify synthetic provenance. No fields are inferred from
    the availability or eligibility responses. This routine does not commit.
    """
    if not all(
        (
            request.case_id.strip(),
            request.option_id.strip(),
            request.idempotency_key.strip(),
            request.scheduler_actor_id.strip(),
        )
    ):
        raise ValueError("Required EPS booking fields cannot be blank")
    if not isinstance(request.slot_id, UUID) or not isinstance(
        request.authorization_id, UUID
    ):
        raise ValueError("EPS slot and HSRM authorization IDs must be UUIDs")

    booking_id = persistent_uuid("appointment", request.idempotency_key)
    booking_transition_id = uuid5(
        VAB_SYNTHETIC_NAMESPACE, "booking-transition:" + request.idempotency_key
    )
    booking_audit_id = uuid5(
        VAB_SYNTHETIC_NAMESPACE, "booking-audit:" + request.idempotency_key
    )
    with conn.cursor() as cur:
        schema = assert_synthetic_scheduling_database(cur, conn, write=True)

        # Serialize case and the exact slot before making a booking decision.
        execute_scheduling_sql(cur, schema, 
            "SELECT l.request_id, r.patient_id, r.requested_service, "
            "r.request_kind "
            "FROM vab.scheduling_case_link l "
            "JOIN vab.appointment_request r ON r.request_id=l.request_id "
            "WHERE l.case_id=%s AND l.synthetic=true FOR UPDATE OF l",
            (request.case_id,),
        )
        case = cur.fetchone()
        if case is None:
            raise ValueError("Unknown synthetic scheduling case")
        request_id, patient_id, service, request_kind = case
        # Demo scope: specialty requires a separately reviewed consult gate.
        if request_kind != "PRIMARY_CARE":
            raise ValueError("Only primary-care synthetic booking is enabled")

        # With the case lock held, resolve an existing committed key BEFORE
        # mutable EPS verification, authorization, eligibility, or decisions.
        # An acknowledged booking remains recoverable after those change.
        execute_scheduling_sql(cur, schema, 
            "SELECT a.appointment_id,a.request_id,a.slot_id,a.approved_by,"
            "a.status,a.patient_id,s.status,s.channel,s.provider_id,s.source_id "
            "FROM vab.appointment a "
            "JOIN vab.slot s ON s.slot_id=a.slot_id "
            "WHERE a.idempotency_key=%s FOR UPDATE OF a,s",
            (request.idempotency_key,),
        )
        prior = cur.fetchone()
        if prior is not None:
            (
                stored_id,
                stored_request,
                stored_slot,
                stored_actor,
                stored_status,
                stored_patient,
                stored_slot_status,
                stored_channel,
                stored_provider,
                stored_source,
            ) = prior
            if (
                stored_id != booking_id
                or stored_request != request_id
                or stored_slot != request.slot_id
                or stored_actor != request.scheduler_actor_id
                or stored_status != "BOOKED_SIMULATED"
                or stored_patient != patient_id
                or stored_slot_status != "BOOKED"
                or stored_channel != "EPS"
                or not stored_provider
                or not stored_source
            ):
                raise ValueError("Conflicting EPS booking idempotency key")
            execute_scheduling_sql(cur, schema, 
                "SELECT evidence,case_id,idempotency_key "
                "FROM vab.scheduling_transition "
                "WHERE transition_id=%s AND event_type='BOOKED_SIMULATED'",
                (booking_transition_id,),
            )
            transition = cur.fetchone()
            execute_scheduling_sql(cur, schema, 
                "SELECT details,correlation_id,source_id "
                "FROM vab.audit_event "
                "WHERE event_id=%s AND event_type='BOOKED_SIMULATED'",
                (booking_audit_id,),
            )
            audit = cur.fetchone()
            if transition is None or audit is None:
                raise ValueError("Committed booking missing matching atomic evidence")
            stored_evidence = transition[0]
            required = {
                "synthetic": True,
                "appointment_id": str(booking_id),
                "case_id": request.case_id,
                "option_id": request.option_id,
                "slot_id": str(request.slot_id),
                "authorization_id": str(request.authorization_id),
                "provider_id": stored_provider,
                "scheduler_actor_id": request.scheduler_actor_id,
                "idempotency_key": request.idempotency_key,
                "slot_source_id": stored_source,
            }
            if (
                not isinstance(stored_evidence, dict)
                or any(stored_evidence.get(k) != v for k, v in required.items())
                or not stored_evidence.get("authorization_source_id")
                or transition[1:] != (request.case_id, "booking:" + request.idempotency_key)
                or audit[0] != stored_evidence
                or audit[1:] != (request.idempotency_key, stored_source)
            ):
                raise ValueError("Committed booking has conflicting provenance")
            return booking_id

        # The case row remains locked until commit. Different idempotency keys
        # must not create a second active appointment for this request.
        execute_scheduling_sql(cur, schema, 
            "SELECT appointment_id FROM vab.appointment "
            "WHERE request_id=%s AND status='BOOKED_SIMULATED' "
            "LIMIT 1 FOR UPDATE",
            (request_id,),
        )
        if cur.fetchone() is not None:
            raise ValueError("Case already has an active synthetic appointment")

        execute_scheduling_sql(cur, schema, 
            "SELECT channel,status,provider_id,verified_at,source_id,begins_at "
            "FROM vab.slot WHERE slot_id=%s FOR UPDATE",
            (request.slot_id,),
        )
        slot = cur.fetchone()
        if slot is None or slot[0] != "EPS":
            raise ValueError("Expected persisted synthetic EPS slot")
        channel, status, provider_id, verified_at, source_id, begins_at = slot
        if not provider_id or not source_id:
            raise ValueError("EPS slot requires provider and provenance source")
        execute_scheduling_sql(cur, schema, 
            "SELECT source_kind,provenance FROM vab.data_source WHERE source_id=%s",
            (source_id,),
        )
        source = cur.fetchone()
        if source is None or source[0] != "synthetic_fixture":
            raise ValueError("EPS booking requires synthetic fixture provenance")
        # Persisted ownership and eligibility are authoritative, not preflight.
        bindings = source[1].get("slot_bindings") if isinstance(source[1], dict) else None
        binding = bindings.get(str(request.slot_id)) if isinstance(bindings, dict) else None
        if (
            not isinstance(binding, dict)
            or binding.get("case_id") != request.case_id
            or binding.get("option_id") != request.option_id
            or binding.get("initial_consult_eligible") is not True
        ):
            raise ValueError("EPS slot case/option ownership or eligibility denied")

        # Authorization + referral are locked together. Authorization is never
        # inferred from the returned EPS availability, nor from HTTP 200.
        execute_scheduling_sql(cur, schema, 
            "SELECT a.status,a.valid_from,a.valid_until,a.service_scope,"
            "a.evidence,a.source_id,f.patient_id,f.status,f.evidence "
            "FROM vab.authorization a "
            "JOIN vab.referral f ON f.referral_id=a.referral_id "
            "WHERE a.authorization_id=%s FOR UPDATE OF a,f",
            (request.authorization_id,),
        )
        auth = cur.fetchone()
        if auth is None:
            raise ValueError("Persisted HSRM authorization missing")
        (
            auth_status,
            valid_from,
            valid_until,
            auth_service,
            evidence,
            auth_source,
            referral_patient,
            referral_status,
            referral_evidence,
        ) = auth
        if (
            auth_status != "ACTIVE"
            or referral_status != "ACTIVE"
            or referral_patient != patient_id
        ):
            raise ValueError("HSRM authorization/referral not active for patient")
        if auth_service.strip().upper() != service.strip().upper():
            raise ValueError("HSRM service does not match scheduling request")
        expected = {
            "case_id": request.case_id,
            "option_id": request.option_id,
            "slot_id": str(request.slot_id),
            "provider_id": provider_id,
        }
        if not all(evidence.get(key) == value for key, value in expected.items()):
            raise ValueError(
                "HSRM evidence does not bind exact case/option/slot/provider"
            )
        if evidence.get("synthetic") is not True or not evidence.get("provenance_ref"):
            raise ValueError("HSRM synthetic source provenance missing")
        if referral_evidence.get("case_id") != request.case_id:
            raise ValueError("HSRM referral case mismatch")
        if not auth_source:
            raise ValueError("HSRM authorization source missing")
        execute_scheduling_sql(cur, schema, 
            "SELECT source_kind FROM vab.data_source WHERE source_id=%s",
            (auth_source,),
        )
        origin = cur.fetchone()
        if origin is None or origin[0] != "synthetic_fixture":
            raise ValueError("HSRM source must be a synthetic fixture")

        # Re-check timestamps using DB time, not caller-reported time.
        execute_scheduling_sql(cur, schema, 
            "SELECT (%s <= clock_timestamp() AND %s >= clock_timestamp() AND "
            "%s BETWEEN clock_timestamp() - interval '15 minutes' "
            "AND clock_timestamp() AND %s > clock_timestamp())",
            (valid_from, valid_until, verified_at, begins_at),
        )
        if not cur.fetchone()[0]:
            raise ValueError("HSRM or EPS verification is outside validity window")

        # The latest signed decision for each role/option is authoritative.
        # A newer rejection must supersede any older accepted decision.
        decision_orders = {}
        for event_type, kind, role in (
            ("VETERAN_CONFIRMATION_RECORDED", "VETERAN_CONFIRMED", "VETERAN"),
            ("SCHEDULER_REVIEW_RECORDED", "SCHEDULER_APPROVED", "SCHEDULER"),
        ):
            execute_scheduling_sql(cur, schema, 
                "SELECT d.decision_status,d.decision_order FROM vab.scheduling_decision d "
                "JOIN vab.scheduling_transition e "
                "ON e.case_id=d.case_id "
                "AND e.idempotency_key=d.idempotency_key "
                "AND e.correlation_id=d.correlation_id "
                "WHERE d.case_id=%s AND d.decision_kind=%s "
                "AND d.actor_role=%s AND d.option_id=%s "
                "AND e.event_type=%s "
                "AND e.evidence ? 'service_evidence_reference' "
                "AND (%s <> 'SCHEDULER' OR d.actor_id=%s) "
                "ORDER BY d.decision_order DESC LIMIT 1",
                (
                    request.case_id,
                    kind,
                    role,
                    request.option_id,
                    event_type,
                    role,
                    request.scheduler_actor_id,
                ),
            )
            current = cur.fetchone()
            if current is None or current[0] != "ACCEPTED":
                raise ValueError(f"Current {kind} decision is not accepted")
            decision_orders[role] = current[1]
        if decision_orders["SCHEDULER"] <= decision_orders["VETERAN"]:
            raise ValueError("Scheduler approval predates latest Veteran consent")

        booking_evidence = {
            "synthetic": True,
            "appointment_id": str(booking_id),
            "case_id": request.case_id,
            "option_id": request.option_id,
            "slot_id": str(request.slot_id),
            "authorization_id": str(request.authorization_id),
            "provider_id": provider_id,
            "scheduler_actor_id": request.scheduler_actor_id,
            "idempotency_key": request.idempotency_key,
            "slot_source_id": source_id,
            "authorization_source_id": auth_source,
        }
        event_key = "booking:" + request.idempotency_key

        if status != "AVAILABLE":
            raise ValueError("EPS slot is unavailable or already booked")

        execute_scheduling_sql(cur, schema, 
            "UPDATE vab.slot SET status='BOOKED' "
            "WHERE slot_id=%s AND channel='EPS' AND status='AVAILABLE'",
            (request.slot_id,),
        )
        if cur.rowcount != 1:
            raise ValueError("EPS slot concurrently unavailable")
        execute_scheduling_sql(cur, schema, 
            "INSERT INTO vab.appointment "
            "(appointment_id,patient_id,request_id,slot_id,status,"
            "idempotency_key,approved_by) "
            "VALUES (%s,%s,%s,%s,'BOOKED_SIMULATED',%s,%s)",
            (
                booking_id,
                patient_id,
                request_id,
                request.slot_id,
                request.idempotency_key,
                request.scheduler_actor_id,
            ),
        )
        # Both audit records share the caller-owned booking transaction.
        # An insertion failure must roll back the slot and appointment as well.
        execute_scheduling_sql(cur, schema, 
            "INSERT INTO vab.scheduling_transition "
            "(transition_id,case_id,event_type,to_state,actor_role,"
            "actor_id,idempotency_key,correlation_id,evidence) "
            "VALUES (%s,%s,'BOOKED_SIMULATED','BOOKED_SIMULATED',"
            "'SYSTEM',%s,%s,%s,%s::jsonb)",
            (
                booking_transition_id,
                request.case_id,
                "synthetic-eps-booking",
                event_key,
                request.idempotency_key,
                json.dumps(booking_evidence),
            ),
        )
        execute_scheduling_sql(cur, schema, 
            "INSERT INTO vab.audit_event "
            "(event_id,correlation_id,actor,event_type,source_id,details) "
            "VALUES (%s,%s,%s,'BOOKED_SIMULATED',%s,%s::jsonb)",
            (
                booking_audit_id,
                request.idempotency_key,
                "synthetic-eps-booking",
                source_id,
                json.dumps(booking_evidence),
            ),
        )
        return booking_id
