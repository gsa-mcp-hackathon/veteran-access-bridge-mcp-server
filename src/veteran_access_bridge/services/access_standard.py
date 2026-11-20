"""Deterministic VA access-standard assessment for M6.1.

This service is read-only. It evaluates internal VA capacity against a configured
wait-time standard measured from the canonical Patient Indicated Date (PID).

An exceeded standard produces only a Community Care eligibility-review signal.
It never grants authorization, calls EPS, or writes lifecycle/booking state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from veteran_access_bridge.adapters.federal_ehr import FederalEHRAdapter
from veteran_access_bridge.adapters.vista import VistAAdapter
from veteran_access_bridge.domain.models import (
    AccessOption,
    ClinicalConsult,
    OptionReadiness,
    PatientContext,
    SourceSearchStatus,
    WorkflowState,
)
from veteran_access_bridge.domain.workflow import determine_workflow_state

_ACCESS_STANDARD_DAYS = {
    "PRIMARY": 20,
    "PRIMARY_CARE": 20,
    "MENTAL_HEALTH": 20,
    "SPECIALTY": 28,
    "SPECIALTY_CARE": 28,
}

_ELIGIBLE_INTERNAL_READINESS = {
    OptionReadiness.AVAILABLE,
    OptionReadiness.VERIFIED_BOOKABLE,
}


@dataclass(frozen=True)
class AccessStandardAssessment:
    case_id: str
    patient_id: str
    consult_id: str
    care_category: str
    patient_indicated_date: date
    standard_days: int
    earliest_eligible_va_option_id: Optional[str]
    earliest_eligible_va_date: Optional[datetime]
    earliest_eligible_va_wait_days: Optional[int]
    wait_standard_exceeded: bool
    community_care_review_recommended: bool
    community_care_authorization_status: str
    comparator_source_system: Optional[str]
    comparator_source_record_id: Optional[str]
    comparator_retrieved_at: Optional[datetime]
    comparator_freshness: Optional[str]
    synthetic: bool = True


def _normalize_care_category(care_category: str) -> tuple[str, int]:
    normalized = care_category.strip().upper().replace(" ", "_")
    try:
        standard_days = _ACCESS_STANDARD_DAYS[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(_ACCESS_STANDARD_DAYS))
        raise ValueError(
            f"Unsupported care_category {care_category!r}. Supported values: {supported}."
        ) from exc

    canonical = {
        "PRIMARY_CARE": "PRIMARY",
        "SPECIALTY_CARE": "SPECIALTY",
    }.get(normalized, normalized)
    return canonical, standard_days


def evaluate_access_standard(
    *,
    case_id: str,
    patient_id: str,
    consult_id: str,
    care_category: str,
    patient_indicated_date: date,
    options: tuple[AccessOption, ...],
) -> AccessStandardAssessment:
    """Evaluate already-normalized internal VA options against the wait standard."""

    canonical_category, standard_days = _normalize_care_category(care_category)

    eligible = tuple(
        option
        for option in options
        if option.source_system in {"VISTA_ISS", "FEDERAL_EHR_FHIR"}
        and option.readiness in _ELIGIBLE_INTERNAL_READINESS
        and option.slot_start.date() >= patient_indicated_date
    )

    if not eligible:
        return AccessStandardAssessment(
            case_id=case_id,
            patient_id=patient_id,
            consult_id=consult_id,
            care_category=canonical_category,
            patient_indicated_date=patient_indicated_date,
            standard_days=standard_days,
            earliest_eligible_va_option_id=None,
            earliest_eligible_va_date=None,
            earliest_eligible_va_wait_days=None,
            wait_standard_exceeded=True,
            community_care_review_recommended=True,
            community_care_authorization_status="NOT_EVALUATED",
            comparator_source_system=None,
            comparator_source_record_id=None,
            comparator_retrieved_at=None,
            comparator_freshness=None,
        )

    earliest = min(eligible, key=lambda option: option.slot_start)
    wait_days = (earliest.slot_start.date() - patient_indicated_date).days
    exceeded = wait_days > standard_days

    return AccessStandardAssessment(
        case_id=case_id,
        patient_id=patient_id,
        consult_id=consult_id,
        care_category=canonical_category,
        patient_indicated_date=patient_indicated_date,
        standard_days=standard_days,
        earliest_eligible_va_option_id=earliest.option_id,
        earliest_eligible_va_date=earliest.slot_start,
        earliest_eligible_va_wait_days=wait_days,
        wait_standard_exceeded=exceeded,
        community_care_review_recommended=exceeded,
        community_care_authorization_status="NOT_EVALUATED",
        comparator_source_system=earliest.source_system,
        comparator_source_record_id=earliest.source_record_id,
        comparator_retrieved_at=earliest.provenance.retrieved_at,
        comparator_freshness=earliest.provenance.freshness,
    )


def assess_access_standard(
    *,
    case_id: str,
    patient: PatientContext,
    consult: ClinicalConsult | None,
    care_category: str,
    patient_indicated_date: date,
    as_of: datetime,
    _vista: Optional[VistAAdapter] = None,
    _federal_ehr: Optional[FederalEHRAdapter] = None,
) -> AccessStandardAssessment:
    """Search internal VA sources only and evaluate the applicable wait standard."""

    if determine_workflow_state(patient, consult) != WorkflowState.READY_TO_SEARCH:
        raise ValueError("assess_access_standard requires READY_TO_SEARCH.")

    if consult is None:  # guarded by determine_workflow_state; keeps typing explicit
        raise ValueError("A valid consult is required.")

    vista = _vista or VistAAdapter(as_of=as_of)
    federal_ehr = _federal_ehr or FederalEHRAdapter(as_of=as_of)

    source_results = (
        vista.search(patient.patient_id, consult.specialty, as_of=as_of),
        federal_ehr.search(patient.patient_id, consult.specialty, as_of=as_of),
    )

    usable_statuses = {SourceSearchStatus.SUCCESS, SourceSearchStatus.PARTIAL}
    options = tuple(
        option
        for result in source_results
        if result.status in usable_statuses
        for option in result.options
    )

    return evaluate_access_standard(
        case_id=case_id,
        patient_id=patient.patient_id,
        consult_id=consult.consult_id,
        care_category=care_category,
        patient_indicated_date=patient_indicated_date,
        options=options,
    )
