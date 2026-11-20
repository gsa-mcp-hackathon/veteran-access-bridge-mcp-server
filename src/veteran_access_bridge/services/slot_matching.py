"""Deterministic SchedulingRequest-to-SchedulingSlot matching for M6.2c."""

from __future__ import annotations

from veteran_access_bridge.domain.models import (
    PatientClinicClassification,
    SchedulingRequest,
    SchedulingSlot,
    SlotAvailability,
    SlotEligibilityReason,
    SlotEligibilityResult,
)


def _same_text(left: str | None, right: str | None) -> bool:
    """Case-insensitive comparison for normalized scheduling text."""
    if left is None or right is None:
        return left is right
    return left.strip().casefold() == right.strip().casefold()


def evaluate_slot_eligibility(
    request: SchedulingRequest,
    slot: SchedulingSlot,
) -> SlotEligibilityResult:
    """Evaluate one slot against one scheduling request.

    This function is read-only and deterministic. It does not rank preferences,
    reserve capacity, invoke EPS, infer Community Care authorization, or write
    lifecycle state.
    """
    reasons: list[SlotEligibilityReason] = []

    if slot.availability is SlotAvailability.STALE:
        reasons.append(SlotEligibilityReason.STALE)
    elif slot.availability is SlotAvailability.UNAVAILABLE:
        reasons.append(SlotEligibilityReason.UNAVAILABLE)

    if slot.slot_start.date() < request.canonical_pid:
        reasons.append(SlotEligibilityReason.BEFORE_PID)

    if not _same_text(slot.service, request.service):
        reasons.append(SlotEligibilityReason.SERVICE_MISMATCH)

    # FACILITY_MISMATCH is the M6.2 contract's umbrella reason for explicit
    # facility/clinic/stop-code context constraints.
    location_mismatch = False
    if request.facility_id is not None and not _same_text(
        slot.facility_id, request.facility_id
    ):
        location_mismatch = True
    if request.clinic_id is not None and not _same_text(slot.clinic_id, request.clinic_id):
        location_mismatch = True
    if request.stop_code is not None and not _same_text(slot.stop_code, request.stop_code):
        location_mismatch = True
    if request.stop_code_group is not None and not _same_text(
        slot.stop_code_group, request.stop_code_group
    ):
        location_mismatch = True
    if location_mismatch:
        reasons.append(SlotEligibilityReason.FACILITY_MISMATCH)

    if request.patient_classification is PatientClinicClassification.UNKNOWN:
        reasons.append(SlotEligibilityReason.PATIENT_CLASSIFICATION_UNKNOWN)
    elif (
        not slot.eligible_patient_classifications
        or request.patient_classification not in slot.eligible_patient_classifications
    ):
        reasons.append(SlotEligibilityReason.PATIENT_CLASSIFICATION_MISMATCH)

    if (
        request.appointment_intent is not None
        and slot.eligible_appointment_intents
        and request.appointment_intent not in slot.eligible_appointment_intents
    ):
        reasons.append(SlotEligibilityReason.APPOINTMENT_INTENT_MISMATCH)

    if (
        request.required_template_types
        and slot.template_type not in request.required_template_types
    ):
        reasons.append(SlotEligibilityReason.TEMPLATE_MISMATCH)

    if (
        request.required_resource_types
        and slot.resource_type not in request.required_resource_types
    ):
        reasons.append(SlotEligibilityReason.RESOURCE_MISMATCH)

    if (
        request.required_duration_minutes is not None
        and slot.duration_minutes < request.required_duration_minutes
    ):
        reasons.append(SlotEligibilityReason.DURATION_INSUFFICIENT)

    if request.required_modality is not None and not _same_text(
        slot.modality, request.required_modality
    ):
        reasons.append(SlotEligibilityReason.MODALITY_MISMATCH)

    if reasons:
        return SlotEligibilityResult(
            request_id=request.request_id,
            slot_id=slot.slot_id,
            eligible=False,
            reasons=tuple(reasons),
        )

    return SlotEligibilityResult(
        request_id=request.request_id,
        slot_id=slot.slot_id,
        eligible=True,
        reasons=(SlotEligibilityReason.ELIGIBLE,),
    )


def match_scheduling_slots(
    request: SchedulingRequest,
    slots: tuple[SchedulingSlot, ...],
) -> tuple[SlotEligibilityResult, ...]:
    """Evaluate slots in input order and return structured evidence for each."""
    return tuple(evaluate_slot_eligibility(request, slot) for slot in slots)
