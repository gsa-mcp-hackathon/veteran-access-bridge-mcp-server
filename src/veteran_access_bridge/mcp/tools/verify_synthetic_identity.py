"""MCP tool: verify_synthetic_identity.

Read-only identity gate for approved synthetic demonstration cases. Compares
Veteran-supplied full name and date of birth against the governed synthetic
fixture and returns a verification status. For an inbound voice intake, a
successful match also returns the synthetic case ID and source match metadata
needed to scope subsequent synthetic reads.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Annotated, Any

from fastmcp import FastMCP

from veteran_access_bridge.mcp.cases import load_demo_encounter_case

_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr"}


def _normalize_name(value: str) -> str:
    """Normalize a synthetic display name while tolerating common honorifics."""
    if re.match(r"^(?:my name is\s+)?(?:spelled|spelt)\s+", value.strip(), re.I):
        from veteran_access_bridge.voice.spoken_identity import spoken_name

        value = spoken_name(value) or ""
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = re.findall(r"[a-z0-9]+", ascii_text)
    while tokens and tokens[0] in _HONORIFICS:
        tokens.pop(0)
    return " ".join(tokens)


def _normalize_birth_date(value: str) -> str | None:
    """Normalize common spoken/typed DOB formats to YYYY-MM-DD."""
    raw = value.strip()
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        pass

    cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned.replace(",", " ")).strip()
    for fmt in (
        "%B %d %Y",
        "%b %d %Y",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%m %d %Y",
    ):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    from veteran_access_bridge.voice.spoken_identity import spoken_birth_date

    return spoken_birth_date(raw)


def run(case_id: str, full_name: str, birth_date: str) -> dict[str, Any]:
    """Verify synthetic identity without returning protected fixture details.

    ``verified`` reports the name-and-birth-date match. The separate
    ``patient_match_enabled`` fixture property does not veto a successful match.
    """
    # The inbound LiveKit caller has not been selected or identified in the UI.
    # Resolve strictly against the seven approved, local synthetic fixtures.
    # Retain the intake ID as the canonical voice-session correlation key;
    # matched_case_id authorizes a subsequent case-scoped MCP read only.
    if case_id == "DEMO-PC-VOICE-INTAKE-001":
        from veteran_access_bridge.mcp.voice_demo_patients import (
            list_voice_demo_patients,
        )

        normalized_birth = _normalize_birth_date(birth_date)
        if normalized_birth is None:
            return {
                "verified": False,
                "synthetic": True,
                "case_id": case_id,
                "reason": "INVALID_BIRTH_DATE_FORMAT",
            }
        for candidate in list_voice_demo_patients():
            if (
                _normalize_name(full_name) == _normalize_name(candidate["name"])
                and normalized_birth == candidate["birthdate"]
            ):
                return {
                    "verified": True,
                    "synthetic": True,
                    "case_id": case_id,
                    "matched_case_id": candidate["case_id"],
                    "reason": "MATCH",
                    "patient_match_enabled": candidate["enabled_for_patient_match"],
                }
        # Approved sandbox exports are optional and *never* queried remotely.
        # Matching requires an explicit server-only manifest and a complete,
        # caller-stated synthetic full name and DOB.
        from veteran_access_bridge.mcp.approved_sandbox_patients import (
            list_approved_sandbox_patients,
        )

        try:
            approved_sandbox = list_approved_sandbox_patients()
        except ValueError:
            return {
                "verified": False,
                "synthetic": True,
                "case_id": case_id,
                "reason": "SANDBOX_MAPPING_UNAVAILABLE",
            }
        for candidate in approved_sandbox:
            if (
                _normalize_name(full_name) == _normalize_name(candidate["name"])
                and normalized_birth == candidate["birthdate"]
            ):
                return {
                    "verified": True,
                    "synthetic": True,
                    "case_id": case_id,
                    "matched_case_id": candidate["case_id"],
                    "reason": "MATCH",
                    "patient_match_enabled": True,
                    "verification_source": "APPROVED_SYNTHETIC_SANDBOX_EXPORT",
                }
        return {
            "verified": False,
            "synthetic": True,
            "case_id": case_id,
            "reason": "NO_MATCH",
        }

    try:
        patient, _ = load_demo_encounter_case(case_id)
    except ValueError:
        return {
            "verified": False,
            "synthetic": True,
            "case_id": case_id,
            "reason": "UNKNOWN_SYNTHETIC_CASE",
        }

    supplied_birth_date = _normalize_birth_date(birth_date)
    if supplied_birth_date is None:
        return {
            "verified": False,
            "synthetic": True,
            "case_id": case_id,
            "reason": "INVALID_BIRTH_DATE_FORMAT",
        }

    verified = (
        _normalize_name(full_name) == _normalize_name(patient.display_name)
        and supplied_birth_date == patient.birth_date
    )
    return {
        "verified": verified,
        "synthetic": True,
        "case_id": case_id,
        "reason": "MATCH" if verified else "NO_MATCH",
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="verify_synthetic_identity",
        annotations={
            "title": "Verify Synthetic Veteran Identity",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def verify_synthetic_identity_tool(
        case_id: Annotated[
            str,
            "Approved case ID or DEMO-PC-VOICE-INTAKE-001 for incoming calls.",
        ],
        full_name: Annotated[
            str,
            "Veteran-stated full name for synthetic verification.",
        ],
        birth_date: Annotated[
            str,
            "Veteran-stated date of birth; common spoken or typed "
            "formats are accepted.",
        ],
    ) -> dict[str, Any]:
        """Match a caller's stated full name and DOB against synthetic fixtures.

        For the inbound intake case, a verified match returns the target synthetic
        scheduling case ID, without revealing names, DOB, ICNs, phone or address.
        Use ``verified`` for the match result; ``patient_match_enabled`` is
        separate fixture metadata and does not prohibit an identity match. A
        missing match means the caller must not access that patient's scheduling
        data.
        """
        return run(case_id, full_name, birth_date)
