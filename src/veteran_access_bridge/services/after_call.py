"""Host-triggered after-call records; no new booking or delivery authority."""

import hashlib
import os
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
)
from veteran_access_bridge.services.crm import _encode, _scope


def prepare_wrapup(
    *,
    case_id,
    voice_session_id,
    reason,
    receipt,
    patient_zone,
    declined=False,
    facility_name=None,
):
    if reason not in {"CALLER_ENDED", "DISCONNECTED", "TIME_LIMIT"}:
        raise ValueError("Unsupported call end reason")
    letter = None
    disposition = "FOLLOW_UP_NEEDED"
    summary = (
        f"After-call scheduling summary. Call ended: {reason}. "
        "Identity verified during this call. No appointment was confirmed "
        "in this call. Scheduling remains unresolved. "
        "Review CRM history for other requests or follow-up."
    )
    if declined and receipt is None:
        disposition = "CALLER_DECLINED"
        summary = (
            f"After-call scheduling summary. Call ended: {reason}. "
            "Identity verified during this call. Caller declined the offered booking. "
            "No appointment was confirmed in this call. "
            "Review CRM history for other requests or follow-up."
        )
    if receipt is not None:
        if (
            receipt.get("verified") is not True
            or receipt.get("synthetic") is not True
            or receipt.get("state") != "BOOKED_SIMULATED"
            or receipt.get("case_id") != case_id
            or receipt.get("voice_session_id") != voice_session_id
            or not patient_zone
        ):
            raise PermissionError(
                "Verified call-bound appointment and timezone required"
            )
        appointment = str(UUID(receipt["appointment_id"]))
        begins, ends = receipt["begins_at"], receipt["ends_at"]
        if begins.tzinfo is None or ends.tzinfo is None or ends <= begins:
            raise PermissionError("Verified appointment times required")
        zone = ZoneInfo(patient_zone)
        local = begins.astimezone(zone)
        when = local.strftime("%A, %B %d, %Y at %I:%M %p %Z")
        details = ""
        if facility_name is not None:
            if (
                not isinstance(facility_name, str)
                or not 1 <= len(facility_name.strip()) <= 120
                or any(ord(c) < 32 for c in facility_name)
            ):
                raise ValueError("Invalid verified facility name")
            details += f"Demo inventory facility: {facility_name}\n"
        for field, label in (("clinic_name", "Clinic"), ("provider_name", "Provider")):
            value = receipt.get(field)
            if (
                isinstance(value, str)
                and 0 < len(value.strip()) <= 200
                and not any(ord(c) < 32 or ord(c) == 127 for c in value)
            ):
                details += f"{label}: {value.strip()}\n"
            else:
                details += f"{label}: Not supplied by the scheduling source\n"
        disposition = "INFORMATION_PROVIDED"
        summary = (
            f"After-call scheduling summary. Call ended: {reason}. "
            f"Identity verified; Primary Care appointment {appointment} independently "
            f"confirmed for {when} ({patient_zone}). Confirmation letter generated, "
            "not sent. Review CRM history for other requests or follow-up."
        )
        letter = {
            "filename": "appointment-confirmation.txt",
            "content_type": "text/plain",
            "delivery_status": "NOT_SENT",
            "text": (
                "VETERAN ACCESS BRIDGE\nAPPOINTMENT CONFIRMATION\n"
                "Demonstration record — not a live VA appointment\n\n"
                f"Appointment reference: {appointment}\n"
                f"Service: Primary Care\nDate and time: {when}\n"
                f"Appointment display time zone: {patient_zone}\n"
                f"Scheduled end: {ends.astimezone(zone).strftime('%I:%M %p %Z')}\n\n"
                + details
                + "\nStreet address and arrival instructions were not supplied in "
                "the verified booking receipt. Contact the scheduling team for "
                "those details.\n\n"
                "Generated after the call from an independently verified booking. "
                "This letter has not been mailed, emailed or texted.\n"
            ),
        }
    return {
        "summary": summary,
        "disposition": disposition,
        "letter": letter,
        "reason": reason,
        "follow_up_task_created": False,
    }


def record_after_call(*, case_id, interaction_id, voice_session_id, verify):
    """Persist note and letter atomically using existing scoped CRM tables.

    verify is a private host callback, never supplied through model or browser input.
    """
    if os.getenv("VAB_ENABLE_CRM") != "true" or not interaction_id:
        raise PermissionError("CRM and canonical interaction required")
    payload = verify()
    digest = hashlib.sha256(_encode(payload).encode()).hexdigest()
    key = "after-call:" + voice_session_id
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
                if previous[0] != digest or verify() != payload:
                    raise PermissionError("After-call evidence changed")
                return {**previous[1], "replayed": True}
            record = str(uuid4())
            result = {
                **payload,
                "status": "COMPLETE",
                "persisted": True,
                "record_id": record,
                "voice_session_id": voice_session_id,
                "invoked_by": "host",
                "trigger": "call_ended",
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
            if verify() != payload:
                raise PermissionError("After-call evidence changed before commit")
    return result
