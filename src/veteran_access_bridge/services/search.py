"""search_availability — M1 availability search service.

Calls all three synthetic source adapters for a READY_TO_SEARCH case and
returns a SearchAvailabilityResult with:

- options: flat aggregated AccessOption list from successful adapters
- source_results: per-source SourceSearchResult including failures

A failed adapter is never silently dropped. Every SourceSearchResult is
present in source_results regardless of its status. Each adapter call has
its own exception boundary; an unexpected exception from one adapter becomes
a SourceSearchResult with SOURCE_UNAVAILABLE and a safe error message — the
remaining adapters still run. search_availability() does not construct a
SchedulingHandoff.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from veteran_access_bridge.adapters.community import CommunityAdapter
from veteran_access_bridge.adapters.federal_ehr import FederalEHRAdapter
from veteran_access_bridge.adapters.vista import VistAAdapter
from veteran_access_bridge.domain.models import (
    ClinicalConsult,
    PatientContext,
    SearchAvailabilityResult,
    SourceSearchResult,
    SourceSearchStatus,
    WorkflowState,
)
from veteran_access_bridge.domain.workflow import determine_workflow_state

# Sentinel for "use datetime.now()" — allows None to be a valid as_of value
# without ambiguity. Tests always supply an explicit as_of.
_USE_WALL_CLOCK = object()


def _call_adapter(
    adapter: VistAAdapter | FederalEHRAdapter | CommunityAdapter,
    source_system: str,
    patient_id: str,
    specialty: str,
    as_of: Optional[datetime],
) -> SourceSearchResult:
    """Call a single adapter with its own exception boundary.

    Any unexpected exception raised by the adapter is caught and converted to a
    SourceSearchResult with SOURCE_UNAVAILABLE. The error_message contains only
    the exception type name — no stack trace, local path, or sensitive detail.
    """
    try:
        if isinstance(adapter, (VistAAdapter, FederalEHRAdapter, CommunityAdapter)):
            return adapter.search(patient_id, specialty, as_of=as_of)
        return adapter.search(patient_id, specialty)
    except Exception as exc:  # noqa: BLE001
        return SourceSearchResult(
            source_system=source_system,
            status=SourceSearchStatus.SOURCE_UNAVAILABLE,
            retrieved_at=as_of if as_of is not None else datetime.now(timezone.utc),
            error_message=(
                f"Adapter raised an unexpected exception: {type(exc).__name__}"
            ),
        )


def search_availability(
    patient: PatientContext,
    consult: ClinicalConsult | None,
    *,
    _vista: Optional[VistAAdapter] = None,
    _federal_ehr: Optional[FederalEHRAdapter] = None,
    _community: Optional[CommunityAdapter] = None,
    _as_of: object = _USE_WALL_CLOCK,
) -> SearchAvailabilityResult:
    """Search all three synthetic source adapters for scheduling availability.

    Parameters
    ----------
    patient:
        The PatientContext for the case.
    consult:
        The ClinicalConsult for the case. Must be valid and READY_TO_SEARCH.
    _vista, _federal_ehr, _community:
        Optional adapter overrides. Pass adapter instances constructed with
        ``simulate_unavailable=True`` to test partial-source failure paths
        without touching fixture files. May also be any object with a
        compatible ``search(patient_id, specialty)`` method.
    _as_of:
        Reference datetime for slot expiry evaluation. When not supplied,
        each adapter uses datetime.now(timezone.utc). Always supply an
        explicit datetime in tests to keep results deterministic.

    Returns
    -------
    SearchAvailabilityResult
        Contains the aggregated AccessOption list from successful adapters
        and a per-source SourceSearchResult for every adapter called,
        including failures.

    Raises
    ------
    ValueError
        If the case is not in READY_TO_SEARCH state. The workflow gate is
        deterministic and must pass before any adapter is called.
    """
    state = determine_workflow_state(patient, consult)
    if state != WorkflowState.READY_TO_SEARCH:
        raise ValueError(
            f"search_availability requires READY_TO_SEARCH; "
            f"got {state!r} for patient {patient.patient_id!r}."
        )

    specialty = consult.specialty  # type: ignore[union-attr]  # guarded above

    # Resolve the clock once. When _as_of is the sentinel, each adapter
    # falls back to its own datetime.now() call. When an explicit datetime
    # is supplied, all three adapters share the same reference point.
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
    community = _community or CommunityAdapter(as_of=as_of)

    # Each adapter call has its own exception boundary; a failure in one
    # adapter does not prevent the others from running.
    vista_result = _call_adapter(
        vista, "VISTA_ISS", patient.patient_id, specialty, as_of
    )
    federal_ehr_result = _call_adapter(
        federal_ehr, "FEDERAL_EHR_FHIR", patient.patient_id, specialty, as_of
    )
    community_result = _call_adapter(
        community, "COMMUNITY_CARE_EPS", patient.patient_id, specialty, as_of
    )

    source_results = (vista_result, federal_ehr_result, community_result)

    # Aggregate options only from adapters that returned SUCCESS or PARTIAL.
    successful_statuses = {SourceSearchStatus.SUCCESS, SourceSearchStatus.PARTIAL}
    aggregated_options = tuple(
        option
        for result in source_results
        if result.status in successful_statuses
        for option in result.options
    )

    return SearchAvailabilityResult(
        patient_id=patient.patient_id,
        consult_id=consult.consult_id,  # type: ignore[union-attr]
        searched_at=as_of if as_of is not None else datetime.now(timezone.utc),
        options=aggregated_options,
        source_results=source_results,
    )
