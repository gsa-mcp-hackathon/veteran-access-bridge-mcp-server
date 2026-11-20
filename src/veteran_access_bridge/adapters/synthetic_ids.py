"""Stable synthetic MCP identifier to PostgreSQL UUID mapping.

Pure mapping only: no database access and no scheduling state changes.
External MCP identifiers are retained without modification.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

# Fixed project namespace. Do not change after persistence begins.
VAB_SYNTHETIC_NAMESPACE = UUID("b15938cf-2fcb-4a19-9930-bcc8b31002e7")

_KINDS = frozenset({"patient", "request", "consult", "slot", "appointment"})


def persistent_uuid(kind: str, external_id: str) -> UUID:
    """Return a stable, type-separated UUID for one approved synthetic source ID."""
    if kind not in _KINDS:
        raise ValueError(f"Unsupported persistent identifier kind: {kind!r}")
    if not isinstance(external_id, str) or not external_id.strip():
        raise ValueError("External identifier must be a nonblank string")
    if external_id != external_id.strip():
        raise ValueError("External identifier must be canonical (no edge whitespace)")
    return uuid5(VAB_SYNTHETIC_NAMESPACE, f"{kind}:{external_id}")


@dataclass(frozen=True)
class CaseIdentifiers:
    case_id: str
    request_external_id: str
    request_uuid: UUID
    patient_external_id: str
    patient_uuid: UUID
    consult_external_id: str | None
    consult_uuid: UUID | None


def resolve_case_identifiers(case_id: str) -> CaseIdentifiers:
    """Resolve approved packaged MCP cases without SQL or side effects."""
    from veteran_access_bridge.mcp.cases import _load_demo_payload

    payload = _load_demo_payload(case_id)
    request = payload["scheduling_request"]
    patient = payload["patient_context"]
    consult = payload.get("clinical_consult")
    request_id = request["request_id"]
    patient_id = patient["patient_id"]
    if request_id != str(request_id) or patient_id != str(patient_id):
        raise ValueError("Invalid source identifier")
    if payload.get("case_id") != case_id:
        raise ValueError("Case fixture identifier mismatch")
    if payload["clinic_relationship"]["patient_id"] != patient_id:
        raise ValueError("Case patient/clinic relationship mismatch")
    if consult and consult["patient_id"] != patient_id:
        raise ValueError("Case consult/patient mismatch")
    consult_id = consult["consult_id"] if consult else None
    return CaseIdentifiers(
        case_id=case_id,
        request_external_id=request_id,
        request_uuid=persistent_uuid("request", request_id),
        patient_external_id=patient_id,
        patient_uuid=persistent_uuid("patient", patient_id),
        consult_external_id=consult_id,
        consult_uuid=persistent_uuid("consult", consult_id) if consult_id else None,
    )
