"""Governed calendar projection for the MSA Primary Care workspace.

Issue #72.

The browser consumes this projection and must not derive slot eligibility,
verification, or booking state from raw availability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class CalendarSlotState(StrEnum):
    RAW_ONLY = "RAW_ONLY"
    ELIGIBLE = "ELIGIBLE"
    EXCLUDED = "EXCLUDED"
    SELECTED = "SELECTED"
    VERIFIED = "VERIFIED"
    SIMULATED_BOOKED = "SIMULATED_BOOKED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class CalendarSlotProjection:
    slot_id: str
    option_id: str | None
    source_system: str
    facility_name: str
    resource_name: str | None
    slot_start: str
    slot_end: str
    modality: str | None
    state: CalendarSlotState
    eligibility_reasons: tuple[str, ...]
    preference_rank: int | None
    is_access_comparator: bool
    synthetic: bool = True


def project_calendar_slots(
    encounter: Mapping[str, Any],
) -> tuple[CalendarSlotProjection, ...]:
    """Build browser-ready slot states from a governed encounter payload."""

    eligibility_by_slot = {
        str(item["slot_id"]): item for item in encounter.get("slot_eligibility", ())
    }
    options_by_slot = {
        str(item["source_record_id"]): item
        for item in encounter.get("eligible_options", ())
    }

    ranks: dict[str, int] = {}
    for index, ranked in enumerate(encounter.get("ranked_options", ()), start=1):
        option = ranked.get("option", {})
        option_id = option.get("option_id")
        if option_id:
            ranks[str(option_id)] = index

    assessment = encounter.get("access_standard") or {}
    comparator_option_id = assessment.get("earliest_eligible_va_option_id")

    decision = encounter.get("decision") or {}
    selected_option_id = decision.get("selected_option_id")
    verification_outcome = decision.get("verification_outcome")
    booking_id = decision.get("booking_id")

    encounter_state = str(encounter.get("encounter_state", ""))

    projections: list[CalendarSlotProjection] = []
    for slot in encounter.get("slots", ()):
        slot_id = str(slot["slot_id"])
        eligibility = eligibility_by_slot.get(slot_id)
        option = options_by_slot.get(slot_id)
        option_id = str(option["option_id"]) if option else None

        if eligibility is None:
            state = CalendarSlotState.RAW_ONLY
            reasons: tuple[str, ...] = ()
        elif not bool(eligibility.get("eligible")):
            state = CalendarSlotState.EXCLUDED
            reasons = tuple(str(reason) for reason in eligibility.get("reasons", ()))
        else:
            state = CalendarSlotState.ELIGIBLE
            reasons = tuple(str(reason) for reason in eligibility.get("reasons", ()))

        if option_id and option_id == selected_option_id:
            state = CalendarSlotState.SELECTED
            if verification_outcome == "VERIFIED":
                state = CalendarSlotState.VERIFIED
            if booking_id:
                state = CalendarSlotState.SIMULATED_BOOKED
        elif state is CalendarSlotState.ELIGIBLE and encounter_state in {
            "AWAITING_SCHEDULER_REVIEW",
            "BLOCKED",
        }:
            state = CalendarSlotState.REVIEW_REQUIRED

        projections.append(
            CalendarSlotProjection(
                slot_id=slot_id,
                option_id=option_id,
                source_system=str(slot["source_system"]),
                facility_name=str(slot["facility_name"]),
                resource_name=(
                    str(slot["resource_name"])
                    if slot.get("resource_name") is not None
                    else None
                ),
                slot_start=str(slot["slot_start"]),
                slot_end=str(slot["slot_end"]),
                modality=(
                    str(slot["modality"]) if slot.get("modality") is not None else None
                ),
                state=state,
                eligibility_reasons=reasons,
                preference_rank=(ranks.get(option_id) if option_id else None),
                is_access_comparator=(
                    option_id is not None and option_id == comparator_option_id
                ),
            )
        )

    return tuple(projections)
