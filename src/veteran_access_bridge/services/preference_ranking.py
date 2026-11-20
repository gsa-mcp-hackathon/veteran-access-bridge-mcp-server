"""M6.3b deterministic Veteran preference ranking.

Ranking is applied only after M6.2 deterministic slot eligibility. Preferences
can reorder eligible options but can never create eligibility, authorize care,
reserve capacity, or change the M6.1 access-standard comparator.
"""

from __future__ import annotations

from dataclasses import dataclass

from veteran_access_bridge.domain.models import (
    AccessOption,
    SchedulingRequest,
    SchedulingSlot,
)


@dataclass(frozen=True)
class RankedAccessOption:
    """One already-eligible option with transparent preference evidence."""

    rank: int
    option: AccessOption
    matched_dimensions: tuple[str, ...]
    unmatched_dimensions: tuple[str, ...]
    preference_match_count: int
    explicit_preference_count: int

    @property
    def fully_matches_preferences(self) -> bool:
        return (
            self.explicit_preference_count > 0
            and self.preference_match_count == self.explicit_preference_count
        )


def _normalized(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(value.strip().casefold() for value in values if value.strip())


def _time_of_day(hour: int) -> str:
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    return "evening"


def _preference_evidence(
    *,
    request: SchedulingRequest,
    option: AccessOption,
    slot: SchedulingSlot | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    matched: list[str] = []
    unmatched: list[str] = []

    facilities = _normalized(request.preferred_facility_ids)
    if facilities:
        target = option.facility_id.strip().casefold()
        (matched if target in facilities else unmatched).append("FACILITY")

    modalities = _normalized(request.preferred_modality)
    if modalities:
        target = slot.modality.strip().casefold() if slot and slot.modality else ""
        (matched if target in modalities else unmatched).append("MODALITY")

    days = _normalized(request.preferred_days_of_week)
    if days:
        target = option.slot_start.strftime("%A").casefold()
        (matched if target in days else unmatched).append("DAY_OF_WEEK")

    times = _normalized(request.preferred_time_of_day)
    if times:
        target = _time_of_day(option.slot_start.hour)
        (matched if target in times else unmatched).append("TIME_OF_DAY")

    return tuple(matched), tuple(unmatched)


def rank_eligible_options(
    request: SchedulingRequest,
    slots: tuple[SchedulingSlot, ...],
    eligible_options: tuple[AccessOption, ...],
) -> tuple[RankedAccessOption, ...]:
    """Rank only M6.2-eligible options using explicit Veteran preferences.

    Each explicitly supplied preference dimension contributes at most one
    transparent match. Options are sorted by:
    1. greater number of matched dimensions,
    2. earlier slot start,
    3. original eligible-option order for deterministic final tie breaking.

    No option is added or removed by this function.
    """
    slot_by_record = {slot.source_record_id: slot for slot in slots}

    evidence: list[
        tuple[int, AccessOption, tuple[str, ...], tuple[str, ...]]
    ] = []
    for index, option in enumerate(eligible_options):
        matched, unmatched = _preference_evidence(
            request=request,
            option=option,
            slot=slot_by_record.get(option.source_record_id),
        )
        evidence.append((index, option, matched, unmatched))

    ordered = sorted(
        evidence,
        key=lambda item: (
            -len(item[2]),
            item[1].slot_start,
            item[0],
        ),
    )

    return tuple(
        RankedAccessOption(
            rank=rank,
            option=option,
            matched_dimensions=matched,
            unmatched_dimensions=unmatched,
            preference_match_count=len(matched),
            explicit_preference_count=len(matched) + len(unmatched),
        )
        for rank, (_, option, matched, unmatched) in enumerate(ordered, start=1)
    )
