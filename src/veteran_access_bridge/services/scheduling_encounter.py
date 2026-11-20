"""Governed real-time Scheduling Encounter assembler.

The encounter composes existing deterministic scheduling services and projects
the already-persisted lifecycle into one shared read-only snapshot.

M6.3c does not create handoffs, selections, verifications, confirmations,
approvals, reservations, or bookings. Those actions remain exclusively in the
existing governed services.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from veteran_access_bridge.adapters.federal_ehr import FederalEHRAdapter
from veteran_access_bridge.adapters.vista import VistAAdapter
from veteran_access_bridge.domain.models import (
    AccessOption,
    CareCategory,
    CaseLifecycleState,
    ClinicalConsult,
    PatientClinicClassification,
    PatientClinicRelationship,
    PatientContext,
    SchedulingRequest,
    SchedulingSlot,
    SlotEligibilityResult,
    SourceSearchResult,
    WorkflowState,
)
from veteran_access_bridge.domain.workflow import determine_workflow_state
from veteran_access_bridge.services.access_standard import (
    AccessStandardAssessment,
    evaluate_access_standard,
)
from veteran_access_bridge.services.booking import BookingStore
from veteran_access_bridge.services.clinic_classification import (
    classify_patient_clinic_relationship,
)
from veteran_access_bridge.services.confirmation import ConfirmationStore
from veteran_access_bridge.services.encounter_lifecycle import (
    SchedulingDecisionSnapshot,
    project_scheduling_decision,
)
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.handoff import HandoffStore
from veteran_access_bridge.services.internal_slot_bridge import (
    evaluate_internal_scheduling_request,
)
from veteran_access_bridge.services.preference_ranking import (
    RankedAccessOption,
    rank_eligible_options,
)
from veteran_access_bridge.services.selection import SelectionStore
from veteran_access_bridge.services.verification import VerificationStore


class SchedulingEncounterState(StrEnum):
    """Shared encounter states for Veteran and Scheduler experiences."""

    REQUEST_ASSEMBLED = "REQUEST_ASSEMBLED"
    CLASSIFIED = "CLASSIFIED"
    READY_TO_SEARCH = "READY_TO_SEARCH"
    OPTIONS_ASSEMBLED = "OPTIONS_ASSEMBLED"
    AWAITING_VETERAN_SELECTION = "AWAITING_VETERAN_SELECTION"
    AWAITING_SCHEDULER_REVIEW = "AWAITING_SCHEDULER_REVIEW"
    AWAITING_VERIFICATION = "AWAITING_VERIFICATION"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    SIMULATED_BOOKED = "SIMULATED_BOOKED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    RESCHEDULED = "RESCHEDULED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


_LIFECYCLE_TO_ENCOUNTER_STATE: dict[
    CaseLifecycleState, SchedulingEncounterState
] = {
    CaseLifecycleState.REQUEST_RECEIVED: SchedulingEncounterState.REQUEST_ASSEMBLED,
    CaseLifecycleState.CLINICAL_REVIEW_REQUIRED: SchedulingEncounterState.BLOCKED,
    CaseLifecycleState.CONSULT_PENDING: SchedulingEncounterState.BLOCKED,
    CaseLifecycleState.READY_TO_SEARCH: SchedulingEncounterState.READY_TO_SEARCH,
    CaseLifecycleState.VA_OPTIONS_AVAILABLE: SchedulingEncounterState.OPTIONS_ASSEMBLED,
    CaseLifecycleState.COMMUNITY_CARE_REVIEW_REQUIRED: (
        SchedulingEncounterState.AWAITING_SCHEDULER_REVIEW
    ),
    CaseLifecycleState.COMMUNITY_OPTIONS_AVAILABLE: (
        SchedulingEncounterState.OPTIONS_ASSEMBLED
    ),
    CaseLifecycleState.READY_FOR_HANDOFF: SchedulingEncounterState.OPTIONS_ASSEMBLED,
    CaseLifecycleState.HUMAN_REVIEW: SchedulingEncounterState.AWAITING_SCHEDULER_REVIEW,
    CaseLifecycleState.OPTION_SELECTED: SchedulingEncounterState.AWAITING_VERIFICATION,
    CaseLifecycleState.READY_TO_VERIFY: SchedulingEncounterState.AWAITING_VERIFICATION,
    CaseLifecycleState.AUTH_REQUIRED: SchedulingEncounterState.BLOCKED,
    CaseLifecycleState.VERIFIED_BOOKABLE: (
        SchedulingEncounterState.AWAITING_VETERAN_SELECTION
    ),
    CaseLifecycleState.PENDING_VETERAN_CONFIRMATION: (
        SchedulingEncounterState.AWAITING_VETERAN_SELECTION
    ),
    CaseLifecycleState.PENDING_SCHEDULER_APPROVAL: (
        SchedulingEncounterState.READY_FOR_APPROVAL
    ),
    CaseLifecycleState.BOOKED_SIMULATED: SchedulingEncounterState.SIMULATED_BOOKED,
    CaseLifecycleState.COMPLETED: SchedulingEncounterState.COMPLETED,
    CaseLifecycleState.NO_SHOW: SchedulingEncounterState.NO_SHOW,
    CaseLifecycleState.CANCELLED: SchedulingEncounterState.CANCELLED,
    CaseLifecycleState.RESCHEDULED: SchedulingEncounterState.RESCHEDULED,
    CaseLifecycleState.SOURCE_UNAVAILABLE: SchedulingEncounterState.BLOCKED,
}

_LIFECYCLE_BLOCKING_STATES = frozenset({
    CaseLifecycleState.CLINICAL_REVIEW_REQUIRED,
    CaseLifecycleState.CONSULT_PENDING,
    CaseLifecycleState.AUTH_REQUIRED,
    CaseLifecycleState.SOURCE_UNAVAILABLE,
})


@dataclass(frozen=True)
class SchedulingEncounter:
    """Canonical read-only snapshot for one real-time scheduling encounter."""

    encounter_id: str
    assembled_at: datetime
    request: SchedulingRequest
    workflow_state: WorkflowState
    encounter_state: SchedulingEncounterState
    patient_classification: PatientClinicClassification
    slots: tuple[SchedulingSlot, ...]
    slot_eligibility: tuple[SlotEligibilityResult, ...]
    eligible_options: tuple[AccessOption, ...]
    ranked_options: tuple[RankedAccessOption, ...]
    source_results: tuple[SourceSearchResult, ...]
    access_standard: AccessStandardAssessment | None
    decision: SchedulingDecisionSnapshot | None = None
    blockers: tuple[str, ...] = ()
    preferences_applied: bool = False
    synthetic: bool = True

    def __post_init__(self) -> None:
        if not self.encounter_id.strip():
            raise ValueError("encounter_id is required.")
        if self.assembled_at.tzinfo is None or self.assembled_at.utcoffset() is None:
            raise ValueError("assembled_at must be timezone-aware.")
        if not self.synthetic or not self.request.synthetic:
            raise ValueError("SchedulingEncounter must remain synthetic.")
        if self.encounter_state is SchedulingEncounterState.BLOCKED and not self.blockers:
            raise ValueError("BLOCKED encounters require at least one blocker.")
        if self.encounter_state is not SchedulingEncounterState.BLOCKED and self.blockers:
            raise ValueError("Non-blocked encounters must not carry blockers.")
        if self.preferences_applied and len(self.ranked_options) != len(self.eligible_options):
            raise ValueError(
                "Preference ranking must preserve the eligible option count."
            )
        if not self.preferences_applied and self.ranked_options:
            raise ValueError(
                "ranked_options must be empty when preferences_applied is false."
            )


def _request_workflow_state(
    *,
    request: SchedulingRequest,
    patient: PatientContext,
    consult: ClinicalConsult | None,
) -> WorkflowState:
    """Resolve readiness without weakening the existing specialty gate."""
    if request.patient_id != patient.patient_id:
        return WorkflowState.CLINICAL_REVIEW_REQUIRED

    if any(not item.synthetic for item in patient.provenance):
        return WorkflowState.CLINICAL_REVIEW_REQUIRED

    if request.care_category is CareCategory.SPECIALTY:
        return determine_workflow_state(patient, consult)

    if request.care_category in {
        CareCategory.PRIMARY_CARE,
        CareCategory.MENTAL_HEALTH,
    }:
        return WorkflowState.READY_TO_SEARCH

    return WorkflowState.AUTH_REQUIRED


def _effective_request(
    request: SchedulingRequest,
    relationship: PatientClinicRelationship,
) -> SchedulingRequest:
    """Apply source-backed clinic classification to the immutable request."""
    if relationship.patient_id != request.patient_id:
        raise ValueError("Clinic relationship patient_id must match the request.")
    if request.facility_id and relationship.facility_id != request.facility_id:
        raise ValueError("Clinic relationship facility_id must match the request.")

    classification = classify_patient_clinic_relationship(relationship)
    return replace(
        request,
        patient_classification=classification,
        classification_as_of=relationship.as_of,
        last_completed_visit=relationship.last_completed_visit,
    )


def _project_state(
    case_id: str,
    event_store: CaseEventStore | None,
    *,
    handoff_store: HandoffStore | None,
    selection_store: SelectionStore | None,
    verification_store: VerificationStore | None,
    confirmation_store: ConfirmationStore | None,
    booking_store: BookingStore | None,
) -> tuple[SchedulingEncounterState, SchedulingDecisionSnapshot | None, tuple[str, ...]]:
    if event_store is None:
        return SchedulingEncounterState.OPTIONS_ASSEMBLED, None, ()

    decision = project_scheduling_decision(
        case_id,
        event_store,
        handoff_store=handoff_store,
        selection_store=selection_store,
        verification_store=verification_store,
        confirmation_store=confirmation_store,
        booking_store=booking_store,
    )
    if decision.lifecycle_state is None:
        return SchedulingEncounterState.OPTIONS_ASSEMBLED, decision, ()

    state = _LIFECYCLE_TO_ENCOUNTER_STATE[decision.lifecycle_state]
    blockers = (
        (f"LIFECYCLE_BLOCKED:{decision.lifecycle_state.value}",)
        if decision.lifecycle_state in _LIFECYCLE_BLOCKING_STATES
        else ()
    )
    return state, decision, blockers


def assemble_scheduling_encounter(
    *,
    request: SchedulingRequest,
    patient: PatientContext,
    relationship: PatientClinicRelationship,
    as_of: datetime,
    consult: ClinicalConsult | None = None,
    event_store: CaseEventStore | None = None,
    handoff_store: HandoffStore | None = None,
    selection_store: SelectionStore | None = None,
    verification_store: VerificationStore | None = None,
    confirmation_store: ConfirmationStore | None = None,
    booking_store: BookingStore | None = None,
    _vista: Optional[VistAAdapter] = None,
    _federal_ehr: Optional[FederalEHRAdapter] = None,
) -> SchedulingEncounter:
    """Assemble one deterministic, side-effect-free SchedulingEncounter.

    When lifecycle stores are supplied, the encounter projects their persisted
    state. It never invokes the corresponding mutation services.
    """
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware.")
    as_of = as_of.astimezone(timezone.utc)

    effective_request = _effective_request(request, relationship)
    workflow_state = _request_workflow_state(
        request=effective_request,
        patient=patient,
        consult=consult,
    )

    blockers: list[str] = []
    if workflow_state is not WorkflowState.READY_TO_SEARCH:
        blockers.append(f"WORKFLOW_NOT_READY:{workflow_state.value}")
    if (
        effective_request.patient_classification
        is PatientClinicClassification.UNKNOWN
    ):
        blockers.append("PATIENT_CLINIC_CLASSIFICATION_UNKNOWN")

    encounter_id = f"SE-{effective_request.case_id}-{effective_request.request_id}"

    if blockers:
        return SchedulingEncounter(
            encounter_id=encounter_id,
            assembled_at=as_of,
            request=effective_request,
            workflow_state=workflow_state,
            encounter_state=SchedulingEncounterState.BLOCKED,
            patient_classification=effective_request.patient_classification,
            slots=(),
            slot_eligibility=(),
            eligible_options=(),
            ranked_options=(),
            source_results=(),
            access_standard=None,
            decision=None,
            blockers=tuple(blockers),
            preferences_applied=False,
        )

    internal = evaluate_internal_scheduling_request(
        effective_request,
        _vista=_vista,
        _federal_ehr=_federal_ehr,
        _as_of=as_of,
    )

    access_standard = evaluate_access_standard(
        case_id=effective_request.case_id,
        patient_id=effective_request.patient_id,
        consult_id=effective_request.consult_id or "NOT_APPLICABLE",
        care_category=effective_request.care_category.value,
        patient_indicated_date=effective_request.canonical_pid,
        options=internal.eligible_options,
    )

    ranked_options = rank_eligible_options(
        effective_request,
        internal.slots,
        internal.eligible_options,
    )

    encounter_state, decision, lifecycle_blockers = _project_state(
        effective_request.case_id,
        event_store,
        handoff_store=handoff_store,
        selection_store=selection_store,
        verification_store=verification_store,
        confirmation_store=confirmation_store,
        booking_store=booking_store,
    )

    return SchedulingEncounter(
        encounter_id=encounter_id,
        assembled_at=as_of,
        request=effective_request,
        workflow_state=workflow_state,
        encounter_state=encounter_state,
        patient_classification=effective_request.patient_classification,
        slots=internal.slots,
        slot_eligibility=internal.eligibility,
        eligible_options=internal.eligible_options,
        ranked_options=ranked_options,
        source_results=internal.source_results,
        access_standard=access_standard,
        decision=decision,
        blockers=lifecycle_blockers,
        preferences_applied=True,
    )
