"""Warm handoff projection for the MSA workspace.

Issue #71. This is a read-only application projection assembled from the
governed Scheduling Encounter and calendar evidence.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def build_handoff_projection(
    encounter: Mapping[str, Any],
    calendar: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    request = encounter.get("request") or {}
    decision = encounter.get("decision") or {}
    assessment = encounter.get("access_standard") or {}

    eligible = [
        item
        for item in calendar
        if item.get("state")
        in {
            "ELIGIBLE",
            "SELECTED",
            "VERIFIED",
            "SIMULATED_BOOKED",
            "REVIEW_REQUIRED",
        }
    ]
    excluded = [
        {
            "slot_id": item.get("slot_id"),
            "state": item.get("state"),
            "reasons": list(item.get("eligibility_reasons") or ()),
        }
        for item in calendar
        if item.get("state") == "EXCLUDED"
    ]

    actions: list[str] = []
    if decision.get("selected_option_id"):
        actions.append("OPTION_SELECTED")
    if decision.get("verification_outcome"):
        actions.append("SLOT_VERIFICATION_RECORDED")
    if decision.get("veteran_response"):
        actions.append("VETERAN_RESPONSE_RECORDED")
    if decision.get("booking_id"):
        actions.append("SIMULATED_BOOKING_RECORDED")

    next_action = "PRESENT_GOVERNED_OPTIONS"
    state = encounter.get("encounter_state")
    if state == "AWAITING_VERIFICATION":
        next_action = "VERIFY_SELECTED_SLOT"
    elif state == "AWAITING_VETERAN_SELECTION":
        next_action = "REQUEST_OR_RECORD_VETERAN_CONFIRMATION"
    elif state == "READY_FOR_APPROVAL":
        next_action = "MSA_APPROVAL"
    elif state == "SIMULATED_BOOKED":
        next_action = "NO_FURTHER_BOOKING_ACTION"
    elif state in {"BLOCKED", "AWAITING_SCHEDULER_REVIEW"}:
        next_action = "MSA_REVIEW"

    return {
        "request_intent": request.get("appointment_intent"),
        "care_category": request.get("care_category"),
        "veteran_preferences": {
            "days_of_week": list(request.get("preferred_days_of_week") or ()),
            "time_of_day": list(request.get("preferred_time_of_day") or ()),
            "modality": list(request.get("preferred_modality") or ()),
            "facility_ids": list(request.get("preferred_facility_ids") or ()),
        },
        "scheduling_encounter_state": state,
        "eligible_options": eligible,
        "excluded_options": excluded,
        "access_evidence": {
            "standard_days": assessment.get("standard_days"),
            "eligible_comparator_wait_days": assessment.get(
                "earliest_eligible_va_wait_days"
            ),
            "wait_standard_exceeded": assessment.get("wait_standard_exceeded"),
            "comparator_option_id": assessment.get("earliest_eligible_va_option_id"),
        },
        "actions_completed": actions,
        "transfer_reason": None,
        "next_permitted_action": next_action,
        "apparent_conflict": build_apparent_conflict(calendar),
        "synthetic": True,
    }


def build_apparent_conflict(
    calendar: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Explain when the earliest raw slot is not the earliest eligible slot."""

    if not calendar:
        return None

    ordered = sorted(calendar, key=lambda item: str(item.get("slot_start") or ""))
    earliest_raw = ordered[0]
    eligible_states = {
        "ELIGIBLE",
        "SELECTED",
        "VERIFIED",
        "SIMULATED_BOOKED",
        "REVIEW_REQUIRED",
    }
    eligible = [item for item in ordered if item.get("state") in eligible_states]
    if not eligible:
        return None

    earliest_eligible = eligible[0]
    if earliest_raw.get("slot_id") == earliest_eligible.get("slot_id"):
        return None
    if earliest_raw.get("state") != "EXCLUDED":
        return None

    reasons = list(earliest_raw.get("eligibility_reasons") or ())
    readable = [str(reason).replace("_", " ").lower() for reason in reasons]
    reason_text = ", ".join(readable) if readable else "governed eligibility rules"

    explanation = (
        "An earlier slot is visible in raw availability, but it is not an "
        "eligible option for this scheduling encounter because of "
        f"{reason_text}. The later slot is the earliest governed eligible "
        "option and is the one used for the access comparison."
    )

    return {
        "earliest_raw_slot_id": earliest_raw.get("slot_id"),
        "earliest_raw_start": earliest_raw.get("slot_start"),
        "earliest_raw_state": earliest_raw.get("state"),
        "exclusion_reasons": reasons,
        "earliest_eligible_slot_id": earliest_eligible.get("slot_id"),
        "earliest_eligible_option_id": earliest_eligible.get("option_id"),
        "earliest_eligible_start": earliest_eligible.get("slot_start"),
        "explanation": explanation,
        "synthetic": True,
    }
