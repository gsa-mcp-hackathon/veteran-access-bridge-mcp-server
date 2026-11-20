"""Internal VA/Federal M6.2 slot bridge.

Runs VistA and Federal EHR synthetic capacity through SchedulingSlot matching,
then returns both the full deterministic eligibility evidence and the
corresponding existing AccessOption objects unchanged.

Community Care/EPS is intentionally out of scope for this bridge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from veteran_access_bridge.adapters.federal_ehr import FederalEHRAdapter
from veteran_access_bridge.adapters.vista import VistAAdapter
from veteran_access_bridge.domain.models import (
    AccessOption,
    SchedulingRequest,
    SchedulingSlot,
    SlotEligibilityResult,
    SourceSearchResult,
    SourceSearchStatus,
)
from veteran_access_bridge.services.slot_matching import match_scheduling_slots

_USE_WALL_CLOCK = object()


@dataclass(frozen=True)
class InternalSlotSearchEvidence:
    """Read-only M6.2 evidence for one internal scheduling request."""

    slots: tuple[SchedulingSlot, ...]
    eligibility: tuple[SlotEligibilityResult, ...]
    eligible_options: tuple[AccessOption, ...]
    source_results: tuple[SourceSearchResult, ...]


def evaluate_internal_scheduling_request(
    request: SchedulingRequest,
    *,
    _vista: Optional[VistAAdapter] = None,
    _federal_ehr: Optional[FederalEHRAdapter] = None,
    _as_of: object = _USE_WALL_CLOCK,
) -> InternalSlotSearchEvidence:
    """Evaluate internal VA/Federal capacity and preserve all slot evidence.

    This function is read-only. It does not call Community Care/EPS, rank
    Veteran preferences, reserve capacity, infer authorization, or write
    lifecycle state.
    """
    if _as_of is _USE_WALL_CLOCK:
        as_of: Optional[datetime] = None
    else:
        if not isinstance(_as_of, datetime):
            raise ValueError("_as_of must be a timezone-aware datetime.")
        if _as_of.tzinfo is None or _as_of.utcoffset() is None:
            raise ValueError("_as_of must be timezone-aware.")
        as_of = _as_of.astimezone(timezone.utc)

    vista = _vista or VistAAdapter(as_of=as_of)
    federal_ehr = _federal_ehr or FederalEHRAdapter(as_of=as_of)

    all_slots: list[SchedulingSlot] = []
    all_eligibility: list[SlotEligibilityResult] = []
    eligible_options: list[AccessOption] = []
    source_results: list[SourceSearchResult] = []

    for adapter in (vista, federal_ehr):
        slots = adapter.search_scheduling_slots(
            request.patient_id,
            request.service,
            as_of=as_of,
        )
        eligibility = match_scheduling_slots(request, slots)
        eligible_slot_ids = {
            result.slot_id for result in eligibility if result.eligible
        }

        all_slots.extend(slots)
        all_eligibility.extend(eligibility)

        source_result = adapter.search(
            request.patient_id,
            request.service,
            as_of=as_of,
        )
        source_results.append(source_result)

        if source_result.status not in {
            SourceSearchStatus.SUCCESS,
            SourceSearchStatus.PARTIAL,
        }:
            continue

        eligible_options.extend(
            option
            for option in source_result.options
            if option.source_record_id in eligible_slot_ids
        )

    return InternalSlotSearchEvidence(
        slots=tuple(all_slots),
        eligibility=tuple(all_eligibility),
        eligible_options=tuple(eligible_options),
        source_results=tuple(source_results),
    )


def search_internal_eligible_options(
    request: SchedulingRequest,
    *,
    _vista: Optional[VistAAdapter] = None,
    _federal_ehr: Optional[FederalEHRAdapter] = None,
    _as_of: object = _USE_WALL_CLOCK,
) -> tuple[AccessOption, ...]:
    """Return existing AccessOption objects whose internal slots are M6.2-eligible.

    Kept as the backward-compatible M6.2d helper. The implementation delegates
    to evaluate_internal_scheduling_request() so M6.3 can consume the same
    eligibility result without reimplementing matching.
    """
    return evaluate_internal_scheduling_request(
        request,
        _vista=_vista,
        _federal_ehr=_federal_ehr,
        _as_of=_as_of,
    ).eligible_options
