"""Read-only fresh-connection recovery for a committed synthetic EPS booking.

This function never creates or repairs booking evidence. It verifies immutable
booking provenance, not current mutable authorization or decision readiness.
"""

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
class EPSRecoveryReceipt:
    booking_id: UUID
    case_id: str
    option_id: str
    slot_id: UUID
    scheduler_actor_id: str
    status: str


def recover_committed_eps_booking(
    connect,
    *,
    case_id,
    option_id,
    slot_id,
    authorization_id,
    idempotency_key,
    scheduler_actor_id,
):
    """Read a committed booking using its original identity and audit evidence.

    connect must open a NEW database connection, not reuse the write transaction.
    Expired authorizations and later decisions do not invalidate a prior booking.
    Missing or contradictory committed evidence always fails closed.
    """
    if not all((case_id, option_id, idempotency_key, scheduler_actor_id)) or not (
        isinstance(slot_id, UUID) and isinstance(authorization_id, UUID)
    ):
        raise ValueError("Complete recovery identity required")

    booking_id = persistent_uuid("appointment", idempotency_key)
    transition_id = uuid5(
        VAB_SYNTHETIC_NAMESPACE, "booking-transition:" + idempotency_key
    )
    audit_id = uuid5(VAB_SYNTHETIC_NAMESPACE, "booking-audit:" + idempotency_key)

    with connect() as conn:
        with conn.cursor() as cur:
            schema = assert_synthetic_scheduling_database(cur, conn, write=False)
            execute_scheduling_sql(cur, schema, 
                "SELECT a.appointment_id,a.slot_id,a.approved_by,a.status,"
                "s.channel,s.status,l.case_id,r.patient_id,a.patient_id,"
                "s.provider_id,s.source_id "
                "FROM vab.appointment a "
                "JOIN vab.slot s ON s.slot_id=a.slot_id "
                "JOIN vab.appointment_request r ON r.request_id=a.request_id "
                "JOIN vab.scheduling_case_link l ON l.request_id=r.request_id "
                "WHERE a.idempotency_key=%s",
                (idempotency_key,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            (
                appointment_id,
                stored_slot,
                approved_by,
                appointment_status,
                channel,
                slot_status,
                stored_case,
                request_patient,
                appointment_patient,
                provider_id,
                slot_source,
            ) = row
            if not (
                appointment_id == booking_id
                and stored_slot == slot_id
                and approved_by == scheduler_actor_id
                and stored_case == case_id
                and request_patient == appointment_patient
                and channel == "EPS"
                and slot_status == "BOOKED"
                and appointment_status == "BOOKED_SIMULATED"
                and provider_id
                and slot_source
            ):
                raise ValueError("Conflicting or incomplete committed EPS identity")

            execute_scheduling_sql(cur, schema, 
                "SELECT evidence,case_id,idempotency_key "
                "FROM vab.scheduling_transition "
                "WHERE transition_id=%s AND event_type='BOOKED_SIMULATED'",
                (transition_id,),
            )
            transition = cur.fetchone()
            execute_scheduling_sql(cur, schema, 
                "SELECT details,correlation_id,source_id "
                "FROM vab.audit_event "
                "WHERE event_id=%s AND event_type='BOOKED_SIMULATED'",
                (audit_id,),
            )
            audit = cur.fetchone()
            if transition is None or audit is None:
                raise ValueError("Committed booking missing atomic evidence")

            provenance = transition[0]
            expected = {
                "synthetic": True,
                "appointment_id": str(booking_id),
                "case_id": case_id,
                "option_id": option_id,
                "slot_id": str(slot_id),
                "authorization_id": str(authorization_id),
                "provider_id": provider_id,
                "scheduler_actor_id": scheduler_actor_id,
                "idempotency_key": idempotency_key,
                "slot_source_id": slot_source,
            }
            if (
                not isinstance(provenance, dict)
                or any(provenance.get(key) != value for key, value in expected.items())
                or not provenance.get("authorization_source_id")
                or transition[1:] != (case_id, "booking:" + idempotency_key)
                or audit[0] != provenance
                or audit[1:] != (idempotency_key, slot_source)
            ):
                raise ValueError("Conflicting committed booking provenance")

            return EPSRecoveryReceipt(
                booking_id=appointment_id,
                case_id=stored_case,
                option_id=option_id,
                slot_id=stored_slot,
                scheduler_actor_id=approved_by,
                status=appointment_status,
            )
