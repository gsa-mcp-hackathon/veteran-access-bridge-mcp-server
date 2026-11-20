"""Optional, reviewed VA API sandbox *synthetic export* roster.

This is a private, explicit allowlist for staging an approved test identity,
NOT a network lookup, production patient search, or VA identity proof.
Never include the JSON manifest in a Git commit or browser response.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any

from veteran_access_bridge.mcp.voice_demo_patients import list_voice_demo_patients

_ENV = "VAB_APPROVED_SANDBOX_PATIENTS_JSON"
_CASE_ID = re.compile(r"^DEMO-PC-SBX-[A-Z0-9]{3,20}-001$")
_SOURCE_REF = re.compile(r"^(?:Patient|SyntheticPatient)/[A-Za-z0-9._-]{1,48}$")
_MAX_BYTES = 16384
_MAX_PATIENTS = 12


def _bounded(value: Any, limit: int) -> bool:
    return isinstance(value, str) and 1 <= len(value.strip()) <= limit


def list_approved_sandbox_patients() -> list[dict[str, Any]]:
    """Return only explicitly approved synthetic source-export identities.

    Fail closed if the optional private allowlist is malformed. Even after a
    match, case data remains a synthetic fixture, not live VA inventory.
    """
    raw = os.getenv(_ENV, "")
    if not raw:
        return []
    if len(raw.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("Approved sandbox identity mapping unavailable.")
    try:
        manifest = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("Approved sandbox identity mapping unavailable.") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("synthetic") is not True
        or manifest.get("source_system") != "VA_API_SANDBOX_APPROVED_EXPORT"
        or not isinstance(manifest.get("patients"), list)
        or not 1 <= len(manifest["patients"]) <= _MAX_PATIENTS
    ):
        raise ValueError("Approved sandbox identity mapping unavailable.")

    local = {
        (person["name"].casefold().strip(), person["birthdate"])
        for person in list_voice_demo_patients()
    }
    seen_cases: set[str] = set()
    seen_identities: set[tuple[str, str]] = set()
    approved: list[dict[str, Any]] = []
    for entry in manifest["patients"]:
        if not isinstance(entry, dict):
            raise ValueError("Approved sandbox identity mapping unavailable.")
        case_id = entry.get("case_id")
        name = entry.get("full_name")
        birth = entry.get("birth_date")
        source_ref = entry.get("source_record_ref")
        city = entry.get("city")
        state = entry.get("state")
        postal = entry.get("postal_code")
        if (
            entry.get("approved") is not True
            or entry.get("synthetic") is not True
            or not isinstance(case_id, str)
            or not _CASE_ID.fullmatch(case_id)
            or not _bounded(name, 100)
            or not _bounded(birth, 10)
            or not isinstance(source_ref, str)
            or not _SOURCE_REF.fullmatch(source_ref)
            or not _bounded(city, 80)
            or not isinstance(state, str)
            or not re.fullmatch(r"[A-Z]{2}", state)
            or not isinstance(postal, str)
            or not re.fullmatch(r"[0-9]{5}", postal)
        ):
            raise ValueError("Approved sandbox identity mapping unavailable.")
        try:
            if date.fromisoformat(birth).isoformat() != birth:
                raise ValueError("Invalid date.")
        except ValueError as exc:
            raise ValueError("Approved sandbox identity mapping unavailable.") from exc
        identity = (name.casefold().strip(), birth)
        if case_id in seen_cases or identity in seen_identities or identity in local:
            raise ValueError("Approved sandbox identity mapping unavailable.")
        seen_cases.add(case_id)
        seen_identities.add(identity)
        approved.append(
            {
                "case_id": case_id,
                "name": name.strip(),
                "birthdate": birth,
                "city": city.strip(),
                "state": state,
                "postal_code": postal,
                "source_record_ref": source_ref,
                "enabled_for_patient_match": True,
            }
        )
    return approved


def approved_sandbox_patient_for_case(case_id: str) -> dict[str, Any] | None:
    return next(
        (p for p in list_approved_sandbox_patients() if p["case_id"] == case_id),
        None,
    )
