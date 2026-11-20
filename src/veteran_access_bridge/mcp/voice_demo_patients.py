"""Local-only synthetic caller roster for the VAB Autonomous Scheduling Command Center.

Test personas are not authenticated VA patients. The patient-match-enabled
attribute reports the supplied sandbox property, NOT an identity verification.
Never place names, dates of birth, addresses, ICNs or phones in LiveKit metadata.
"""

from __future__ import annotations

import json
from importlib.resources import files


def _roster() -> list[dict]:
    return json.loads(
        files("veteran_access_bridge.mcp.fixtures")
        .joinpath("synthetic-primary-care-caller-roster.json")
        .read_text(encoding="utf-8")
    )["patients"]


def voice_demo_patient_for_case(case_id: str) -> dict | None:
    return next(
        (patient for patient in _roster() if patient["case_id"] == case_id),
        None,
    )


def list_voice_demo_patients() -> list[dict]:
    """Minimum-necessary chooser projection; only served behind a service-key gate."""
    return [
        {
            "id": patient["id"],
            "case_id": patient["case_id"],
            "name": patient["first_name"] + " " + patient["last_name"],
            "sex": patient["sex"],
            "birthdate": patient["birthdate"],
            "city": patient["city"],
            "state": patient["state"],
            "enabled_for_patient_match": patient["enabled_for_patient_match"],
            "synthetic": True,
        }
        for patient in _roster()
    ]
