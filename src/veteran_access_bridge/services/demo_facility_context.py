"""Explicit demo inventory association, never an inferred patient assignment."""

import json
import os
import re

from veteran_access_bridge.adapters.va_facilities import read_health_facility
from veteran_access_bridge.voice.appointment_language import ZONES


def configured_facilities():
    raw = os.getenv("VAB_DEMO_CLINIC_FACILITIES", "").strip()
    if not raw:
        return {}
    try:
        mapping = json.loads(raw)
    except ValueError as exc:
        raise ValueError("Invalid demo clinic facility mapping") from exc
    if not isinstance(mapping, dict) or not 1 <= len(mapping) <= 10:
        raise ValueError("Explicit bounded demo clinic mapping required")
    for clinic, facility in mapping.items():
        if (
            not re.fullmatch(r"VAB-DEMO-CL-[0-9]{2}", clinic)
            or not isinstance(facility, str)
            or not re.fullmatch(r"vha_[A-Za-z0-9]{1,32}", facility)
        ):
            raise ValueError("Invalid demo clinic facility mapping")
    return mapping


def resolve_demo_facility(clinic_id, *, reader=None):
    facility_id = configured_facilities().get(clinic_id)
    if facility_id is None:
        raise PermissionError("No explicit facility mapping for this demo clinic")
    result = (reader or read_health_facility)(facility_id)
    if (
        result.get("facility_id") != facility_id
        or result.get("source_verified") is not True
        or result.get("source") != "VA_FACILITIES_API_SANDBOX"
        or result.get("time_zone") not in ZONES.values()
    ):
        raise PermissionError("Verified supported facility context required")
    return {
        **result,
        "clinic_id": clinic_id,
        "mapping_kind": "EXPLICIT_DEMO_INVENTORY",
        "patient_assignment_verified": False,
        "booking_authority": False,
    }
