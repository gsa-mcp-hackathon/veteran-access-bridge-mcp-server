"""Minimum-necessary browser proof from the trusted booking host only."""

import re
from datetime import datetime
from uuid import UUID

from veteran_access_bridge.voice.appointment_language import ZONES


def project_voice_options(payload: dict) -> dict:
    options = payload.get("options")
    zone = payload.get("patient_time_zone")
    if not isinstance(options, list) or len(options) > 3 or zone not in ZONES.values():
        return {}
    base = _call_binding(payload)
    if not base:
        return {}
    safe = []
    seen = set()
    for option in options:
        if not isinstance(option, dict):
            return {}
        proof = project_voice_booking({**payload, **option}, booked=False)
        option_id = option.get("option_id")
        if (
            not proof
            or not isinstance(option_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", option_id)
            or option_id in seen
        ):
            return {}
        seen.add(option_id)
        names = {}
        for key in ("provider_name", "clinic_name", "facility_name"):
            value = option.get(key)
            if value is not None and (
                not isinstance(value, str)
                or not 1 <= len(value) <= 120
                or any(ord(c) < 32 for c in value)
            ):
                return {}
            names[key] = value
        safe.append(
            {
                "option_id": option_id,
                "begins_at": proof["begins_at"],
                "ends_at": proof["ends_at"],
                "service": "PRIMARY_CARE",
                **names,
            }
        )
    return {
        "verified": True,
        "identity_verified": True,
        "booking_case_id": base["booking_case_id"],
        "voice_session_id": base["voice_session_id"],
        "patient_time_zone": zone,
        "options": safe,
    }


def _call_binding(payload: dict) -> dict:
    if (
        payload.get("verified") is not True
        or payload.get("identity_verified") is not True
    ):
        return {}
    case = payload.get("booking_case_id", "")
    voice = payload.get("voice_session_id", "")
    if not isinstance(case, str) or not re.fullmatch(
        r"(?:VAB-DEMO-20261113-CASE-\d{3}|VAB-CALL-[0-9a-f]{8}-[0-9a-f]{4}-5[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})",
        case,
    ):
        return {}
    if not isinstance(voice, str) or not re.fullmatch(r"vs-[A-Za-z0-9-]{1,100}", voice):
        return {}
    return {"booking_case_id": case, "voice_session_id": voice}


def project_voice_booking(payload: dict, *, booked: bool) -> dict:
    binding = _call_binding(payload)
    if not binding:
        return {}
    try:
        begins = datetime.fromisoformat(payload["begins_at"])
        ends = datetime.fromisoformat(payload["ends_at"])
        if begins.tzinfo is None or ends.tzinfo is None or ends <= begins:
            return {}
        appointment = str(UUID(payload["appointment_id"])) if booked else None
    except (ValueError, TypeError, KeyError, AttributeError):
        return {}
    if booked and payload.get("state") != "BOOKED_SIMULATED":
        return {}
    names = {}
    for key in ("clinic_name", "provider_name", "facility_name"):
        value = payload.get(key)
        if value is not None:
            if (
                not isinstance(value, str)
                or not 1 <= len(value) <= 120
                or any(ord(c) < 32 for c in value)
            ):
                return {}
            names[key] = value
    crm = {}
    if booked and payload.get("crm_note_status") == "PENDING":
        crm = {"crm_note_status": "PENDING", "crm_note_origin": "trusted_booking_host"}
    elif booked and payload.get("crm_note_status") == "SAVED":
        try:
            note = str(UUID(payload["crm_note_id"]))
            crm = {
                "crm_note_status": "SAVED",
                "crm_note_id": note,
                "crm_note_origin": "trusted_booking_host",
            }
        except (ValueError, TypeError, KeyError, AttributeError):
            pass
    return {
        "verified": True,
        "identity_verified": True,
        "state": "BOOKED_SIMULATED" if booked else "OFFERED",
        **binding,
        **names,
        "begins_at": begins.isoformat(),
        "ends_at": ends.isoformat(),
        **({"appointment_id": appointment} if booked else {}),
        **crm,
        **(
            {"patient_time_zone": payload["patient_time_zone"]}
            if payload.get("patient_time_zone") in ZONES.values()
            else {}
        ),
    }
