"""Synthetic demo case resolver used by the MCP vertical slices."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from importlib.resources import files

from veteran_access_bridge.domain.models import (
    AppointmentIntent,
    CareCategory,
    ClinicalConsult,
    PatientClinicClassification,
    PatientClinicRelationship,
    PatientContext,
    RequestSource,
    ResourceType,
    SchedulingRequest,
    SlotTemplateType,
    SourceProvenance,
)

_DEMO_CASE_FIXTURES = {
    "DEMO-CARD-5000335-001": "mariano-cardiology-case.json",
    "DEMO-PC-5000999-001": "primary-care-established-case.json",
    "DEMO-PC-5000335-001": "primary-care-sandbox-mariano-case.json",
    "DEMO-PC-VOICE-INTAKE-001": "primary-care-unidentified-voice-intake.json",
}
_AS_OF = datetime(2026, 10, 16, tzinfo=timezone.utc)


def _load_demo_payload(case_id: str) -> dict:
    fixture_name = _DEMO_CASE_FIXTURES.get(case_id)
    if fixture_name is None:
        # An external sandbox identity never directly becomes a VAB patient.
        # Only an explicitly reviewed, synthetic source-export identity may
        # receive its OWN synthetic fixture case (not another person's case).
        from veteran_access_bridge.mcp.approved_sandbox_patients import (
            approved_sandbox_patient_for_case,
        )
        from veteran_access_bridge.mcp.voice_demo_patients import (
            voice_demo_patient_for_case,
        )

        patient = voice_demo_patient_for_case(case_id)
        sandbox = (
            approved_sandbox_patient_for_case(case_id) if patient is None else None
        )
        if patient is None and sandbox is None:
            raise ValueError(f"Unknown synthetic case_id {case_id!r}.")
        payload = json.loads(
            files("veteran_access_bridge.mcp.fixtures")
            .joinpath("primary-care-established-case.json")
            .read_text(encoding="utf-8")
        )
        payload["case_id"] = case_id
        if sandbox is not None:
            # This pseudo-ID is VAB-owned; never use an external ICN as
            # a primary key or claim data came from a live VA API query.
            patient_id = "SYNTHETIC-" + case_id
            display_name = sandbox["name"]
            birth_date = sandbox["birthdate"]
            city, state, postal_code = (
                sandbox["city"],
                sandbox["state"],
                sandbox["postal_code"],
            )
            source_system = "VA_API_SANDBOX_APPROVED_EXPORT"
            source_record_id = sandbox["source_record_ref"]
            classification = "synthetic-approved-sandbox-identity"
            request_id = "REQ-" + case_id
            environment = "synthetic-sandbox-export"
            freshness = "reviewed-staged-fixture"
            gender = "unknown"
        else:
            patient_id = patient["icn"]
            display_name = patient["first_name"] + " " + patient["last_name"]
            birth_date = patient["birthdate"]
            city, state, postal_code = (
                patient["city"],
                patient["state"],
                patient["postal_code"],
            )
            source_system = "SYNTHETIC_VOICE_DEMO_ROSTER"
            source_record_id = "SyntheticPatient/" + str(patient["id"])
            classification = "synthetic-voice-persona"
            request_id = "REQ-PC-P" + str(patient["id"]) + "-001"
            environment = "local-demo"
            freshness = "fixture-deterministic"
            gender = "female" if patient["sex"] == "F" else "male"

        payload["classification"] = classification
        payload["patient_context"] = {
            "patient_id": patient_id,
            "display_name": display_name,
            "birth_date": birth_date,
            "gender": gender,
            "address": {
                "city": city,
                "state": state,
                "postal_code": postal_code,
            },
            "active_conditions": [],
            "provenance": [
                {
                    "source_system": source_system,
                    "source_record_id": source_record_id,
                    "environment": environment,
                    "synthetic": True,
                    "freshness": freshness,
                }
            ],
        }
        request = payload["scheduling_request"]
        request["request_id"] = request_id
        request["patient_indicated_date"] = "2026-11-09"
        request["appointment_intent"] = None
        request["required_template_types"] = []
        request["required_modality"] = None
        request["preferred_days_of_week"] = []
        request["preferred_time_of_day"] = []
        relationship = payload["clinic_relationship"]
        relationship["patient_id"] = patient_id
        relationship["last_completed_visit"] = None
        return payload

    return json.loads(
        files("veteran_access_bridge.mcp.fixtures")
        .joinpath(fixture_name)
        .read_text(encoding="utf-8")
    )


def _patient_from_payload(payload: dict) -> PatientContext:
    patient_data = payload["patient_context"]
    address = patient_data["address"]
    provenance = tuple(
        SourceProvenance(
            source_system=item["source_system"],
            source_record_id=item["source_record_id"],
            retrieved_at=_AS_OF,
            synthetic=bool(item["synthetic"]),
            environment=item["environment"],
            freshness=item.get("freshness"),
        )
        for item in patient_data.get("provenance", [])
    )
    return PatientContext(
        patient_id=patient_data["patient_id"],
        display_name=patient_data["display_name"],
        birth_date=patient_data["birth_date"],
        gender=patient_data["gender"],
        city=address["city"],
        state=address["state"],
        postal_code=address["postal_code"],
        active_conditions=tuple(patient_data.get("active_conditions", [])),
        provenance=provenance,
    )


def _consult_from_payload(payload: dict) -> ClinicalConsult | None:
    consult_data = payload.get("clinical_consult")
    if consult_data is None:
        return None

    return ClinicalConsult(
        consult_id=consult_data["consult_id"],
        patient_id=consult_data["patient_id"],
        specialty=consult_data["specialty"],
        status=consult_data["status"],
        requested_at=_AS_OF,
        valid=bool(consult_data["valid"]),
        source=consult_data["source"],
        reason=consult_data.get("reason"),
        blockers=tuple(consult_data.get("blockers", [])),
    )


def load_demo_case(case_id: str) -> tuple[PatientContext, ClinicalConsult]:
    """Return a legacy consult-based synthetic case.

    The legacy workflow/search tools remain specialty-consult oriented. Direct
    Primary Care requests are intentionally exposed through Scheduling Encounter
    instead of being forced through the specialty consult gate.
    """
    payload = _load_demo_payload(case_id)
    patient = _patient_from_payload(payload)
    consult = _consult_from_payload(payload)
    if consult is None:
        raise ValueError(
            f"Synthetic case_id {case_id!r} has no specialty consult; "
            "use get_scheduling_encounter."
        )
    return patient, consult


def load_demo_encounter_case(
    case_id: str,
) -> tuple[PatientContext, ClinicalConsult | None]:
    """Return patient context plus optional consult for the unified encounter."""
    payload = _load_demo_payload(case_id)
    return _patient_from_payload(payload), _consult_from_payload(payload)


def load_demo_access_standard_context(case_id: str) -> tuple[str, date]:
    """Return the synthetic care category and immutable canonical PID."""
    payload = _load_demo_payload(case_id)
    request = payload["scheduling_request"]
    pid = date.fromisoformat(request["patient_indicated_date"])
    return request["care_category"], pid


def demo_as_of() -> datetime:
    return _AS_OF


def load_demo_facility_name(case_id: str) -> str | None:
    """Return the configured demo facility display name, when available."""
    payload = _load_demo_payload(case_id)
    request = payload.get("scheduling_request", {})
    value = request.get("facility_name")
    return str(value) if value else None


def load_demo_scheduling_context(
    case_id: str,
) -> tuple[SchedulingRequest, PatientClinicRelationship]:
    """Return the approved synthetic M6.3 scheduling request and clinic context."""
    payload = _load_demo_payload(case_id)
    request_data = payload["scheduling_request"]
    relationship_data = payload["clinic_relationship"]
    consult_data = payload.get("clinical_consult")

    appointment_intent = request_data.get("appointment_intent")
    if appointment_intent is None and consult_data is not None:
        appointment_intent = AppointmentIntent.INITIAL_CONSULT.value

    request = SchedulingRequest(
        request_id=request_data["request_id"],
        case_id=case_id,
        patient_id=relationship_data["patient_id"],
        request_source=RequestSource(request_data["request_source"]),
        care_category=CareCategory(request_data["care_category"]),
        service=request_data["service"],
        canonical_pid=date.fromisoformat(request_data["patient_indicated_date"]),
        facility_id=request_data.get("facility_id"),
        clinic_id=request_data.get("clinic_id"),
        patient_classification=PatientClinicClassification.UNKNOWN,
        appointment_intent=(
            AppointmentIntent(appointment_intent)
            if appointment_intent is not None
            else None
        ),
        consult_id=(consult_data or {}).get("consult_id"),
        stop_code=request_data.get("stop_code"),
        stop_code_group=request_data.get("stop_code_group"),
        required_duration_minutes=request_data.get("required_duration_minutes"),
        required_resource_types=tuple(
            ResourceType(value)
            for value in request_data.get("required_resource_types", [])
        ),
        required_template_types=tuple(
            SlotTemplateType(value)
            for value in request_data.get("required_template_types", [])
        ),
        required_modality=request_data.get("required_modality"),
        preferred_days_of_week=tuple(request_data.get("preferred_days_of_week", [])),
        preferred_time_of_day=tuple(request_data.get("preferred_time_of_day", [])),
        synthetic=bool(request_data.get("synthetic", True)),
    )

    relationship = PatientClinicRelationship(
        patient_id=relationship_data["patient_id"],
        facility_id=relationship_data["facility_id"],
        stop_code=relationship_data.get("stop_code"),
        stop_code_group=relationship_data.get("stop_code_group"),
        last_completed_visit=(
            datetime.fromisoformat(relationship_data["last_completed_visit"])
            if relationship_data.get("last_completed_visit")
            else None
        ),
        as_of=datetime.fromisoformat(relationship_data["as_of"]),
        synthetic=bool(relationship_data.get("synthetic", True)),
    )
    return request, relationship
