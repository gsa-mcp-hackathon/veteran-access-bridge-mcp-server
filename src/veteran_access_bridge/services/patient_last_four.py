"""Private comparison against an already identity-matched VA test Patient.

This helper grants no identity or booking authority and returns no identifiers.
It must not be used with caller-supplied FHIR data or an unmatched patient.
"""

import hmac
import re

SSN_SYSTEM = "http://hl7.org/fhir/sid/us-ssn"
IDENTIFIER_TYPES = "http://terminology.hl7.org/CodeSystem/v2-0203"


def matches_patient_last_four(patient: dict, supplied: str) -> bool:
    """Fail closed for absent, masked, ambiguous or malformed identifiers.

    Do not fall back to ICN, record ID, DOB, or arbitrary trailing digits.
    Leading zeroes are significant. Never return or log the expected value.
    """
    if not isinstance(supplied, str) or not re.fullmatch(r"[0-9]{4}", supplied):
        return False
    if not isinstance(patient, dict) or patient.get("resourceType") != "Patient":
        return False
    identifiers = patient.get("identifier")
    if not isinstance(identifiers, list):
        return False
    candidates = []
    for identifier in identifiers:
        if not isinstance(identifier, dict):
            return False
        kind = identifier.get("type")
        coding = kind.get("coding", []) if isinstance(kind, dict) else []
        if not isinstance(coding, list):
            return False
        ss_type = any(
            isinstance(c, dict)
            and c.get("system") == IDENTIFIER_TYPES
            and c.get("code") == "SS"
            for c in coding
        )
        system = identifier.get("system")
        if system != SSN_SYSTEM and not ss_type:
            continue
        # Conflicting namespaces are not accepted based on a type label alone.
        if system != SSN_SYSTEM or identifier.get("use") in {"old", "temp"}:
            return False
        value = identifier.get("value")
        if not isinstance(value, str) or not re.fullmatch(
            r"(?:[0-9]{9}|[0-9]{3}-[0-9]{2}-[0-9]{4})", value
        ):
            return False
        candidates.append(value.replace("-", "")[-4:])
    return len(candidates) == 1 and hmac.compare_digest(candidates[0], supplied)
