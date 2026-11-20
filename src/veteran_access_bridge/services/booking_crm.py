"""Private trusted-host booking summaries; never exposed as an MCP tool.

The caller must supply a host-only verifier that independently recovers the
booking under the current signed call binding. No model text enters the note.
"""

import hashlib
import os
from uuid import UUID, uuid4

from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
)
from veteran_access_bridge.services.crm import _encode, _scope


def record_booking_note(*, case_id, interaction_id, voice_session_id, verify):
    if os.getenv("VAB_ENABLE_CRM") != "true" or not interaction_id:
        raise PermissionError("CRM and canonical interaction required")
    receipt = verify()
    if (
        receipt.get("verified") is not True
        or receipt.get("synthetic") is not True
        or receipt.get("state") != "BOOKED_SIMULATED"
        or receipt.get("case_id") != case_id
        or receipt.get("voice_session_id") != voice_session_id
    ):
        raise PermissionError("Verified call-bound booking required")
    appointment = str(UUID(receipt["appointment_id"]))
    begins, ends = receipt["begins_at"], receipt["ends_at"]
    if begins.tzinfo is None or ends.tzinfo is None or ends <= begins:
        raise PermissionError("Verified appointment times required")
    payload = {
        "summary": (
            "Automatic trusted booking-service summary: synthetic Primary Care "
            f"appointment {appointment} independently verified for "
            f"{begins.isoformat()} through {ends.isoformat()}. "
            "No live VA appointment or staff notification was created."
        ),
        "disposition": "INFORMATION_PROVIDED",
        "invoked_by": "host",
        "trigger": "verified_booking",
        "appointment_id": appointment,
        "voice_session_id": voice_session_id,
    }
    digest = hashlib.sha256(_encode(payload).encode()).hexdigest()
    key = "booking-summary:" + appointment
    with connect_private_supabase_test_scheduling() as conn:
        with conn.cursor() as cur:
            _scope(cur, case_id, interaction_id)
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (_encode([case_id, interaction_id, key]),),
            )
            cur.execute(
                "SELECT payload_hash,receipt FROM vab_test.crm_event "
                "WHERE case_id=%s AND interaction_id=%s AND idempotency_key=%s",
                (case_id, interaction_id, key),
            )
            previous = cur.fetchone()
            if previous:
                if previous[0] != digest:
                    raise ValueError("Booking summary conflict")
                if verify() != receipt:
                    raise PermissionError("Booking binding changed")
                return {**previous[1], "replayed": True}
            record = str(uuid4())
            result = {
                "persisted": True,
                "synthetic": True,
                "case_id": case_id,
                "interaction_id": interaction_id,
                "voice_session_id": voice_session_id,
                "appointment_id": appointment,
                "record_id": record,
                "version": 1,
                "operation": "record_crm_interaction",
                "actor": "AVERY",
                "invoked_by": "host",
                "trigger": "verified_booking",
                "booking_created": False,
                "replayed": False,
            }
            cur.execute(
                "INSERT INTO vab_test.crm_interaction "
                "(record_id,case_id,interaction_id,summary,disposition) "
                "VALUES (%s,%s,%s,%s,%s)",
                (
                    record,
                    case_id,
                    interaction_id,
                    payload["summary"],
                    payload["disposition"],
                ),
            )
            cur.execute(
                "INSERT INTO vab_test.crm_event "
                "(event_id,case_id,interaction_id,operation,idempotency_key,"
                "payload_hash,payload,receipt) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
                (
                    str(uuid4()),
                    case_id,
                    interaction_id,
                    "record_crm_interaction",
                    key,
                    digest,
                    _encode(payload),
                    _encode(result),
                ),
            )
            if verify() != receipt:
                raise PermissionError("Booking binding changed before CRM commit")
    return result
