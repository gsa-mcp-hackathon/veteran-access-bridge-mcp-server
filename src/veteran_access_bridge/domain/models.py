"""Canonical domain models for the Veteran Access Bridge MVP.

These models intentionally separate source-derived patient context from
synthetic operational workflow records. They contain no booking behavior.

## State concept distinction (M2)

WorkflowState — computed readiness gate (stateless)
    A deterministic function of PatientContext and ClinicalConsult inputs,
    computed fresh on each call to determine_workflow_state(). It has no
    persistence and no memory of prior events. It answers: "Is this case
    eligible to proceed right now?"

CaseLifecycleState — persisted lifecycle position
    A persisted record tracking where a synthetic scheduling case is in its
    end-to-end lifecycle. Updated only by appending a CaseEvent to the
    CaseEventStore. It answers: "What has happened to this case, and where
    is it in the scheduling workflow?"

The two concepts intentionally use separate enums and must never be conflated.
WorkflowState values appear on ClinicalConsult/PatientContext inputs; lifecycle
values appear on CaseLifecycleState records and CaseEvent transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Optional


class WorkflowState(StrEnum):
    """Computed readiness gate — stateless, derived fresh on each call.

    M1 states (actively used in determine_workflow_state):
        REQUEST_RECEIVED, CLINICAL_REVIEW_REQUIRED, CONSULT_PENDING,
        READY_TO_SEARCH

    M1 states (defined; used as post-search lifecycle values in M2):
        VA_OPTIONS_AVAILABLE, COMMUNITY_CARE_REVIEW_REQUIRED,
        COMMUNITY_OPTIONS_AVAILABLE, READY_FOR_HANDOFF, HUMAN_REVIEW,
        READY_TO_VERIFY, VERIFIED_BOOKABLE, BOOKED_SIMULATED,
        SOURCE_UNAVAILABLE, AUTH_REQUIRED

    Do NOT persist WorkflowState as a lifecycle position. Use
    CaseLifecycleState for persisted case position.
    """

    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    CLINICAL_REVIEW_REQUIRED = "CLINICAL_REVIEW_REQUIRED"
    CONSULT_PENDING = "CONSULT_PENDING"
    READY_TO_SEARCH = "READY_TO_SEARCH"
    VA_OPTIONS_AVAILABLE = "VA_OPTIONS_AVAILABLE"
    COMMUNITY_CARE_REVIEW_REQUIRED = "COMMUNITY_CARE_REVIEW_REQUIRED"
    COMMUNITY_OPTIONS_AVAILABLE = "COMMUNITY_OPTIONS_AVAILABLE"
    READY_FOR_HANDOFF = "READY_FOR_HANDOFF"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    READY_TO_VERIFY = "READY_TO_VERIFY"
    VERIFIED_BOOKABLE = "VERIFIED_BOOKABLE"
    BOOKED_SIMULATED = "BOOKED_SIMULATED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    # M2 new lifecycle states (persisted; not used by determine_workflow_state)
    OPTION_SELECTED = "OPTION_SELECTED"
    PENDING_VETERAN_CONFIRMATION = "PENDING_VETERAN_CONFIRMATION"
    PENDING_SCHEDULER_APPROVAL = "PENDING_SCHEDULER_APPROVAL"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"


@dataclass(frozen=True)
class SourceProvenance:
    source_system: str
    source_record_id: str
    retrieved_at: datetime
    synthetic: bool
    environment: str
    freshness: str | None = None


@dataclass(frozen=True)
class PatientContext:
    patient_id: str
    display_name: str
    birth_date: str
    gender: str
    city: str
    state: str
    postal_code: str
    active_conditions: tuple[str, ...] = ()
    provenance: tuple[SourceProvenance, ...] = ()

    @property
    def has_cardiology_context(self) -> bool:
        cardiology_terms = ("atrial fibrillation", "afib", "cardiac", "cardiology")
        values = (condition.lower() for condition in self.active_conditions)
        return any(any(term in value for term in cardiology_terms) for value in values)


@dataclass(frozen=True)
class ClinicalConsult:
    consult_id: str
    patient_id: str
    specialty: str
    status: str
    requested_at: datetime
    valid: bool
    source: str = "SYNTHETIC_DEMO_FIXTURE"
    reason: str | None = None
    blockers: tuple[str, ...] = field(default_factory=tuple)
    provenance: tuple[SourceProvenance, ...] = ()

    @property
    def ready_for_search(self) -> bool:
        return (
            self.valid
            and self.specialty.strip().lower() == "cardiology"
            and self.status.strip().upper() in {"ACTIVE", "READY", "APPROVED"}
            and not self.blockers
        )


# ---------------------------------------------------------------------------
# M6.2 scheduling request / slot contracts
# ---------------------------------------------------------------------------


class CareCategory(StrEnum):
    """High-level scheduling care category."""

    PRIMARY_CARE = "PRIMARY_CARE"
    MENTAL_HEALTH = "MENTAL_HEALTH"
    SPECIALTY = "SPECIALTY"
    COMMUNITY_CARE = "COMMUNITY_CARE"


class PatientClinicClassification(StrEnum):
    """Clinic-contextual New/Established classification."""

    NEW = "NEW"
    ESTABLISHED = "ESTABLISHED"
    UNKNOWN = "UNKNOWN"


class RequestSource(StrEnum):
    """Origin of the scheduling request."""

    VETERAN_REQUEST = "VETERAN_REQUEST"
    PROVIDER_REQUEST = "PROVIDER_REQUEST"
    CONSULT = "CONSULT"
    RETURN_TO_CLINIC = "RETURN_TO_CLINIC"
    WALK_IN = "WALK_IN"
    RESCHEDULE = "RESCHEDULE"


class ResourceType(StrEnum):
    """Normalized resource type used by scheduling capacity."""

    PHYSICIAN = "PHYSICIAN"
    NP = "NP"
    PA = "PA"
    RN = "RN"
    TEAM = "TEAM"
    COMMUNITY_PROVIDER = "COMMUNITY_PROVIDER"


class SlotTemplateType(StrEnum):
    """Normalized scheduling template/block type."""

    NEW_PATIENT = "NEW_PATIENT"
    ESTABLISHED = "ESTABLISHED"
    CONSULT = "CONSULT"
    FOLLOW_UP = "FOLLOW_UP"
    SAME_DAY = "SAME_DAY"
    WALK_IN = "WALK_IN"
    PROCEDURE = "PROCEDURE"


class SlotAvailability(StrEnum):
    """Domain-level normalized slot availability."""

    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class SlotEligibilityReason(StrEnum):
    """Deterministic reason explaining request/slot eligibility."""

    ELIGIBLE = "ELIGIBLE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    SERVICE_MISMATCH = "SERVICE_MISMATCH"
    FACILITY_MISMATCH = "FACILITY_MISMATCH"
    PATIENT_CLASSIFICATION_UNKNOWN = "PATIENT_CLASSIFICATION_UNKNOWN"
    PATIENT_CLASSIFICATION_MISMATCH = "PATIENT_CLASSIFICATION_MISMATCH"
    APPOINTMENT_INTENT_MISMATCH = "APPOINTMENT_INTENT_MISMATCH"
    TEMPLATE_MISMATCH = "TEMPLATE_MISMATCH"
    RESOURCE_MISMATCH = "RESOURCE_MISMATCH"
    DURATION_INSUFFICIENT = "DURATION_INSUFFICIENT"
    MODALITY_MISMATCH = "MODALITY_MISMATCH"
    BEFORE_PID = "BEFORE_PID"


@dataclass(frozen=True)
class PatientClinicRelationship:
    """Source-backed clinic relationship used for New/Established classification."""

    patient_id: str
    facility_id: str
    stop_code: str | None
    stop_code_group: str | None
    last_completed_visit: datetime | None
    as_of: datetime
    provenance: tuple[SourceProvenance, ...] = ()
    synthetic: bool = True

    def __post_init__(self) -> None:
        if not self.patient_id.strip():
            raise ValueError("patient_id is required.")
        if not self.facility_id.strip():
            raise ValueError("facility_id is required.")
        if not self.synthetic:
            raise ValueError("M6.2 demo relationship records must be synthetic.")


@dataclass(frozen=True)
class SchedulingRequest:
    """Canonical synthetic scheduling request used for deterministic slot matching."""

    request_id: str
    case_id: str
    patient_id: str
    request_source: RequestSource
    care_category: CareCategory
    service: str
    canonical_pid: date

    facility_id: str | None = None
    clinic_id: str | None = None
    stop_code: str | None = None
    stop_code_group: str | None = None

    patient_classification: PatientClinicClassification = (
        PatientClinicClassification.UNKNOWN
    )
    classification_as_of: datetime | None = None
    last_completed_visit: datetime | None = None

    appointment_intent: AppointmentIntent | None = None
    consult_id: str | None = None

    required_duration_minutes: int | None = None
    required_resource_types: tuple[ResourceType, ...] = ()
    required_template_types: tuple[SlotTemplateType, ...] = ()
    required_modality: str | None = None

    preferred_days_of_week: tuple[str, ...] = ()
    preferred_time_of_day: tuple[str, ...] = ()
    preferred_modality: tuple[str, ...] = ()
    preferred_facility_ids: tuple[str, ...] = ()

    provenance: tuple[SourceProvenance, ...] = ()
    synthetic: bool = True

    def __post_init__(self) -> None:
        for field_name in ("request_id", "case_id", "patient_id", "service"):
            value = getattr(self, field_name)
            if not value.strip():
                raise ValueError(f"{field_name} is required.")
        if self.required_duration_minutes is not None and self.required_duration_minutes <= 0:
            raise ValueError("required_duration_minutes must be greater than zero.")
        if self.request_source is RequestSource.CONSULT and not self.consult_id:
            raise ValueError("CONSULT requests require consult_id.")
        if not self.synthetic:
            raise ValueError("M6.2 demo scheduling requests must be synthetic.")


@dataclass(frozen=True)
class SchedulingSlot:
    """Normalized synthetic provider/resource capacity block."""

    slot_id: str
    source_system: str
    source_record_id: str

    facility_id: str
    facility_name: str
    clinic_id: str | None
    stop_code: str | None
    stop_code_group: str | None

    service: str
    resource_id: str | None
    resource_name: str | None
    resource_type: ResourceType

    template_type: SlotTemplateType
    modality: str | None

    slot_start: datetime
    slot_end: datetime
    duration_minutes: int

    availability: SlotAvailability

    eligible_patient_classifications: tuple[PatientClinicClassification, ...]
    eligible_appointment_intents: tuple[AppointmentIntent, ...] = ()

    provenance: SourceProvenance | None = None
    synthetic: bool = True

    def __post_init__(self) -> None:
        for field_name in (
            "slot_id",
            "source_system",
            "source_record_id",
            "facility_id",
            "facility_name",
            "service",
        ):
            value = getattr(self, field_name)
            if not value.strip():
                raise ValueError(f"{field_name} is required.")
        if self.slot_end <= self.slot_start:
            raise ValueError("slot_end must be after slot_start.")
        interval_minutes = int(
            (self.slot_end - self.slot_start).total_seconds() // 60
        )
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be greater than zero.")
        if self.duration_minutes != interval_minutes:
            raise ValueError(
                "duration_minutes must equal the normalized slot interval."
            )
        if not self.synthetic:
            raise ValueError("M6.2 demo scheduling slots must be synthetic.")


@dataclass(frozen=True)
class SlotEligibilityResult:
    """Deterministic request/slot eligibility evidence."""

    request_id: str
    slot_id: str
    eligible: bool
    reasons: tuple[SlotEligibilityReason, ...]

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required.")
        if not self.slot_id.strip():
            raise ValueError("slot_id is required.")
        if self.eligible and self.reasons != (SlotEligibilityReason.ELIGIBLE,):
            raise ValueError(
                "Eligible results must contain only SlotEligibilityReason.ELIGIBLE."
            )
        if not self.eligible and SlotEligibilityReason.ELIGIBLE in self.reasons:
            raise ValueError(
                "Ineligible results must not contain SlotEligibilityReason.ELIGIBLE."
            )
        if not self.reasons:
            raise ValueError("At least one eligibility reason is required.")


# ---------------------------------------------------------------------------
# Availability search models
# ---------------------------------------------------------------------------


class OptionReadiness(StrEnum):
    """Deterministic readiness classification for a scheduling option.

    The readiness value is set by the adapter and must never be inferred by
    downstream services. Community Care slots without authorization must use
    AVAILABLE_NOT_AUTHORIZED, never VERIFIED_BOOKABLE.
    """

    AVAILABLE = "AVAILABLE"
    AVAILABLE_NOT_AUTHORIZED = "AVAILABLE_NOT_AUTHORIZED"
    AUTHORIZED_NOT_VERIFIED = "AUTHORIZED_NOT_VERIFIED"
    VERIFIED_BOOKABLE = "VERIFIED_BOOKABLE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class SourceSearchStatus(StrEnum):
    """Per-source outcome of a single adapter search call."""

    SUCCESS = "SUCCESS"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    NO_SLOTS = "NO_SLOTS"
    PARTIAL = "PARTIAL"


@dataclass(frozen=True)
class AccessOption:
    """Normalized cross-source scheduling option.

    Source-specific fields are resolved inside each adapter before producing
    this value. MCP consumers and the UI never see raw source schemas.
    """

    option_id: str
    source_system: str
    source_record_id: str
    specialty: str
    facility_name: str
    facility_id: str
    slot_start: datetime
    slot_end: datetime
    availability_status: str
    readiness: OptionReadiness
    provenance: SourceProvenance
    provider: Optional[str] = None
    duration_minutes: Optional[int] = None
    wait_days: Optional[int] = None
    drive_minutes: Optional[int] = None
    blockers: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceSearchResult:
    """Result from a single synthetic source adapter.

    A failed source is represented here with status != SUCCESS and an
    error_message. It is never silently dropped from SearchAvailabilityResult.
    """

    source_system: str
    status: SourceSearchStatus
    retrieved_at: datetime
    options: tuple[AccessOption, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    error_message: Optional[str] = None


@dataclass(frozen=True)
class SearchAvailabilityResult:
    """Aggregated result from search_availability().

    options is the flat list of AccessOptions from all successful adapters.
    source_results preserves per-source health including failures.
    search_availability() does not construct SchedulingHandoff.
    """

    patient_id: str
    consult_id: str
    searched_at: datetime
    options: tuple[AccessOption, ...] = field(default_factory=tuple)
    source_results: tuple[SourceSearchResult, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SchedulingHandoff:
    """Prepared artifact from prepare_scheduling_handoff().

    Not constructed by search_availability(). Contains only options that
    have passed the viability filter (not STALE, not UNAVAILABLE, not
    AVAILABLE_NOT_AUTHORIZED without an authorization reference).
    Community Care options that require verification are flagged via
    requires_verification=True.

    handoff_id is deterministic: hash of case_id + sorted option_ids so
    the same search result always produces the same handoff_id.
    """

    handoff_id: str
    patient_id: str
    consult_id: str
    prepared_at: datetime
    options: tuple[AccessOption, ...] = field(default_factory=tuple)
    viable_option_count: int = 0
    source_summary: str = ""
    requires_verification: bool = False
    synthetic: bool = True


# ---------------------------------------------------------------------------
# M2 lifecycle models
# ---------------------------------------------------------------------------


class CaseLifecycleState(StrEnum):
    """Persisted lifecycle position for a synthetic scheduling case.

    This is a distinct concept from WorkflowState (computed readiness gate).
    CaseLifecycleState is updated only by appending a CaseEvent to the
    CaseEventStore. It records where the case actually is in the end-to-end
    scheduling workflow.

    Terminal states: COMPLETED, CANCELLED.
    """

    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    CLINICAL_REVIEW_REQUIRED = "CLINICAL_REVIEW_REQUIRED"
    CONSULT_PENDING = "CONSULT_PENDING"
    READY_TO_SEARCH = "READY_TO_SEARCH"
    VA_OPTIONS_AVAILABLE = "VA_OPTIONS_AVAILABLE"
    COMMUNITY_CARE_REVIEW_REQUIRED = "COMMUNITY_CARE_REVIEW_REQUIRED"
    COMMUNITY_OPTIONS_AVAILABLE = "COMMUNITY_OPTIONS_AVAILABLE"
    READY_FOR_HANDOFF = "READY_FOR_HANDOFF"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    OPTION_SELECTED = "OPTION_SELECTED"
    READY_TO_VERIFY = "READY_TO_VERIFY"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    VERIFIED_BOOKABLE = "VERIFIED_BOOKABLE"
    PENDING_VETERAN_CONFIRMATION = "PENDING_VETERAN_CONFIRMATION"
    PENDING_SCHEDULER_APPROVAL = "PENDING_SCHEDULER_APPROVAL"
    BOOKED_SIMULATED = "BOOKED_SIMULATED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


# Allowed transitions: maps each CaseLifecycleState to the set of states it
# may transition to. Enforced by CaseEventStore; not by this module.
ALLOWED_LIFECYCLE_TRANSITIONS: dict[CaseLifecycleState, frozenset[CaseLifecycleState]] = {
    CaseLifecycleState.REQUEST_RECEIVED: frozenset({
        CaseLifecycleState.CLINICAL_REVIEW_REQUIRED,
        CaseLifecycleState.CONSULT_PENDING,
        CaseLifecycleState.READY_TO_SEARCH,
    }),
    CaseLifecycleState.CLINICAL_REVIEW_REQUIRED: frozenset({
        CaseLifecycleState.CONSULT_PENDING,
        CaseLifecycleState.READY_TO_SEARCH,
    }),
    CaseLifecycleState.CONSULT_PENDING: frozenset({
        CaseLifecycleState.READY_TO_SEARCH,
    }),
    CaseLifecycleState.READY_TO_SEARCH: frozenset({
        CaseLifecycleState.VA_OPTIONS_AVAILABLE,
        CaseLifecycleState.COMMUNITY_OPTIONS_AVAILABLE,
        CaseLifecycleState.COMMUNITY_CARE_REVIEW_REQUIRED,
        CaseLifecycleState.SOURCE_UNAVAILABLE,
    }),
    CaseLifecycleState.SOURCE_UNAVAILABLE: frozenset({
        CaseLifecycleState.READY_TO_SEARCH,
    }),
    CaseLifecycleState.VA_OPTIONS_AVAILABLE: frozenset({
        CaseLifecycleState.READY_FOR_HANDOFF,
    }),
    CaseLifecycleState.COMMUNITY_CARE_REVIEW_REQUIRED: frozenset({
        CaseLifecycleState.READY_FOR_HANDOFF,
        CaseLifecycleState.CANCELLED,
    }),
    CaseLifecycleState.COMMUNITY_OPTIONS_AVAILABLE: frozenset({
        CaseLifecycleState.COMMUNITY_CARE_REVIEW_REQUIRED,
        CaseLifecycleState.READY_FOR_HANDOFF,
    }),
    CaseLifecycleState.READY_FOR_HANDOFF: frozenset({
        CaseLifecycleState.HUMAN_REVIEW,
    }),
    CaseLifecycleState.HUMAN_REVIEW: frozenset({
        CaseLifecycleState.OPTION_SELECTED,
        CaseLifecycleState.READY_TO_SEARCH,
        CaseLifecycleState.CANCELLED,
    }),
    CaseLifecycleState.OPTION_SELECTED: frozenset({
        CaseLifecycleState.READY_TO_VERIFY,
        CaseLifecycleState.VERIFIED_BOOKABLE,
    }),
    CaseLifecycleState.READY_TO_VERIFY: frozenset({
        CaseLifecycleState.VERIFIED_BOOKABLE,
        CaseLifecycleState.AUTH_REQUIRED,
        CaseLifecycleState.HUMAN_REVIEW,
    }),
    CaseLifecycleState.AUTH_REQUIRED: frozenset({
        CaseLifecycleState.READY_TO_SEARCH,
        CaseLifecycleState.CANCELLED,
    }),
    CaseLifecycleState.VERIFIED_BOOKABLE: frozenset({
        CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
    }),
    CaseLifecycleState.PENDING_VETERAN_CONFIRMATION: frozenset({
        CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
        CaseLifecycleState.HUMAN_REVIEW,
        CaseLifecycleState.CANCELLED,
    }),
    CaseLifecycleState.PENDING_SCHEDULER_APPROVAL: frozenset({
        CaseLifecycleState.BOOKED_SIMULATED,
        CaseLifecycleState.HUMAN_REVIEW,
    }),
    CaseLifecycleState.BOOKED_SIMULATED: frozenset({
        CaseLifecycleState.COMPLETED,
        CaseLifecycleState.NO_SHOW,
        CaseLifecycleState.CANCELLED,
        CaseLifecycleState.RESCHEDULED,
    }),
    CaseLifecycleState.NO_SHOW: frozenset({
        CaseLifecycleState.HUMAN_REVIEW,
    }),
    CaseLifecycleState.RESCHEDULED: frozenset({
        CaseLifecycleState.READY_TO_SEARCH,
    }),
    # Terminal states — no outbound transitions
    CaseLifecycleState.COMPLETED: frozenset(),
    CaseLifecycleState.CANCELLED: frozenset(),
}


class CaseEventType(StrEnum):
    """Append-only lifecycle event types.

    Each event type corresponds to a single transition in the
    ALLOWED_LIFECYCLE_TRANSITIONS map. The event store uses these to drive
    state changes and to validate transition legality.
    """

    # Pre-search gate events (driven by determine_workflow_state results)
    WORKFLOW_GATE_EVALUATED = "WORKFLOW_GATE_EVALUATED"
    BLOCKER_CLEARED = "BLOCKER_CLEARED"

    # Search events
    SEARCH_EXECUTED = "SEARCH_EXECUTED"
    SEARCH_RETRY_REQUESTED = "SEARCH_RETRY_REQUESTED"

    # Post-search routing
    OPTIONS_ASSESSED = "OPTIONS_ASSESSED"
    AUTHORIZATION_RECORDED = "AUTHORIZATION_RECORDED"

    # Handoff and selection
    HANDOFF_PREPARED = "HANDOFF_PREPARED"
    OPTION_SELECTED = "OPTION_SELECTED"

    # Verification path
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"      # CC routing: OPTION_SELECTED → READY_TO_VERIFY
    VERIFICATION_PASSED = "VERIFICATION_PASSED"          # resolved: VERIFIED_BOOKABLE
    VERIFICATION_FAILED = "VERIFICATION_FAILED"          # resolved: AUTH_REQUIRED
    VERIFICATION_INCONCLUSIVE = "VERIFICATION_INCONCLUSIVE"  # resolved: HUMAN_REVIEW

    # Confirmation and approval
    VETERAN_CONFIRMATION_REQUESTED = "VETERAN_CONFIRMATION_REQUESTED"
    VETERAN_CONFIRMED = "VETERAN_CONFIRMED"
    VETERAN_DECLINED = "VETERAN_DECLINED"
    VETERAN_REQUESTED_CHANGE = "VETERAN_REQUESTED_CHANGE"
    SCHEDULER_APPROVED = "SCHEDULER_APPROVED"
    SCHEDULER_REQUESTED_REVISION = "SCHEDULER_REQUESTED_REVISION"

    # Booking (T26 — set atomically by service layer only)
    BOOKED_SIMULATED = "BOOKED_SIMULATED"

    # Post-booking outcomes
    APPOINTMENT_COMPLETED = "APPOINTMENT_COMPLETED"
    VETERAN_NO_SHOW = "VETERAN_NO_SHOW"
    APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"
    RESCHEDULE_REQUESTED = "RESCHEDULE_REQUESTED"
    NEW_SEARCH_INITIATED = "NEW_SEARCH_INITIATED"

    # Staff follow-up
    FOLLOW_UP_INITIATED = "FOLLOW_UP_INITIATED"


class ActorRole(StrEnum):
    """Validated role for audit events.

    For the M2 synthetic demo, role is supplied as a parameter and written
    into the audit event. This is NOT production-grade authentication.
    The upgrade path to session-backed identity is deferred to M3/M4.
    """

    SCHEDULER = "SCHEDULER"
    VETERAN = "VETERAN"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class CaseEvent:
    """Append-only lifecycle event record.

    Each CaseEvent represents a single state transition in the scheduling
    lifecycle. Events are never modified after creation. The idempotency_key
    field allows callers to detect duplicate submissions: the event store
    must reject a second append with the same idempotency_key and instead
    return the existing event.

    Fields:
        event_id:        Unique identifier for this event (UUID or deterministic hash).
        case_id:         The synthetic scheduling case this event belongs to.
        event_type:      What happened (from CaseEventType).
        from_state:      The lifecycle state before this event.
        to_state:        The lifecycle state after this event.
        actor_role:      Role of the human or system that caused this event.
        actor_id:        Opaque identifier for the actor (synthetic/demo only).
        occurred_at:     When the event occurred (timezone-aware UTC).
        idempotency_key: Caller-supplied deduplication key. The event store
                         must treat a second append with the same key as a
                         no-op and return the first event.
        synthetic:       Always True for M2 synthetic demo.
        payload:         Optional structured data specific to this event type
                         (e.g., option_id for OPTION_SELECTED, booking_id for
                         BOOKED_SIMULATED). Must not contain PHI.
    """

    event_id: str
    case_id: str
    event_type: CaseEventType
    from_state: CaseLifecycleState
    to_state: CaseLifecycleState
    actor_role: ActorRole
    actor_id: str
    occurred_at: datetime
    idempotency_key: str
    synthetic: bool = True
    payload: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class CaseLifecycleRecord:
    """Persisted current lifecycle position of a synthetic scheduling case.

    Maintained by the CaseEventStore. The current_state is the to_state of
    the most recently appended CaseEvent. event_count is the total number of
    events in the case history.

    This is not a WorkflowState. It records the persisted scheduling workflow
    position, not the computed readiness gate.
    """

    case_id: str
    current_state: CaseLifecycleState
    last_event_type: CaseEventType
    last_event_at: datetime
    event_count: int
    synthetic: bool = True


@dataclass(frozen=True)
class BookingRecord:
    """Immutable record of a simulated booking commit (T26).

    Created atomically by the service layer when PENDING_SCHEDULER_APPROVAL
    transitions to BOOKED_SIMULATED. The MCP never creates this directly.

    Carries full Community Care EPS/HSRM provenance for the demo. VA/Federal
    bookings set authorization and EPS fields to None.

    booking_id is derived deterministically:
        SHA-256(idempotency_key)[:16] prefixed with "bk-"

    Fields:
        booking_id:           Deterministic ID from idempotency_key.
        case_id:              Synthetic scheduling case.
        option_id:            The AccessOption that was booked.
        slot_id:              The specific slot identifier.
        patient_id:           Synthetic patient identifier.
        consult_id:           Synthetic consult identifier.
        handoff_id:           The handoff the selection came from.
        facility_name:        Human-readable facility name.
        appointment_intent:   AppointmentIntent (INITIAL_CONSULT or FOLLOW_UP).
        appointment_start:    Scheduled appointment start time.
        appointment_end:      Scheduled appointment end time.
        source_system:        Source system (VISTA_ISS, FEDERAL_EHR, EPS, etc.).
        provider_id:          Provider identifier (Community Care / EPS).
        provider_name:        Provider display name (if available).
        referral_id:          HSRM referral identifier (Community Care only).
        authorization_id:     HSRM authorization identifier (Community Care only).
        hsrm_provenance_ref:  Reference to HSRM authorization evidence.
        eps_provenance_ref:   Reference to EPS slot evidence.
        booked_at:            Timezone-aware UTC booking timestamp.
        booked_by_role:       Must be ActorRole.SCHEDULER.
        booked_by_id:         Opaque Scheduler identifier.
        idempotency_key:      Caller-supplied deduplication key.
        synthetic:            Always True for M2 synthetic demo.
        notes:                Optional freetext notes.
    """

    booking_id: str
    case_id: str
    option_id: str
    slot_id: str
    patient_id: str
    consult_id: str
    handoff_id: str
    facility_name: str
    appointment_intent: "AppointmentIntent"
    appointment_start: datetime
    appointment_end: datetime
    source_system: str
    booked_at: datetime
    booked_by_role: "ActorRole"
    booked_by_id: str
    idempotency_key: str
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    referral_id: Optional[str] = None
    authorization_id: Optional[str] = None
    hsrm_provenance_ref: Optional[str] = None
    eps_provenance_ref: Optional[str] = None
    synthetic: bool = True
    notes: Optional[str] = None


@dataclass(frozen=True)
class SlotReservationEntry:
    """In-memory slot reservation record for double-booking protection.

    Held in SlotReservationTable (M2-2). A slot_id may appear at most once
    in the table. An attempt to reserve an already-reserved slot from a
    different case_id must return a conflict error. An attempt from the same
    case_id with the same idempotency_key is treated as a no-op and returns
    the existing entry.

    released is set to True when the case is CANCELLED or RESCHEDULED; the
    slot becomes available again to other cases.
    """

    slot_id: str
    case_id: str
    option_id: str
    reserved_at: datetime
    idempotency_key: str
    released: bool = False
    synthetic: bool = True


# ---------------------------------------------------------------------------
# M2-4 option-selection models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OptionSelectionValidation:
    """Result of validate_option_selection().

    Returned by the validation service and the MCP tool before any state is
    written. A failed validation carries valid=False and a human-readable
    reason; no option is attached. A passing validation carries valid=True,
    the selected AccessOption, and a requires_verification flag that reflects
    whether the option's current readiness requires the verification step.

    This type is purely informational. It does not advance lifecycle state.

    Fields:
        valid:                  True iff the option may be selected.
        option:                 The AccessOption if valid=True, else None.
        requires_verification:  True iff option.readiness == AUTHORIZED_NOT_VERIFIED.
        reason:                 Human-readable explanation (always set on failure;
                                may be set on success for informational notes).
        synthetic:              Always True for M2 synthetic demo.
    """

    valid: bool
    option: Optional["AccessOption"] = None
    requires_verification: bool = False
    reason: str = ""
    synthetic: bool = True


@dataclass(frozen=True)
class OptionSelectionRecord:
    """Immutable record of a Scheduler's option selection.

    Created by record_option_selection() and persisted in SelectionStore.
    The OPTION_SELECTED lifecycle event carries selection_id in its payload.

    selection_id is derived deterministically from the caller-supplied
    idempotency_key via SHA-256 so that the same key always produces the
    same selection_id.

    Idempotency contract:
        same idempotency_key + identical material fields → return existing record
        same idempotency_key + different case/handoff/option/actor  → IdempotencyConflictError

    Fields:
        selection_id:           Deterministic ID derived from idempotency_key.
        case_id:                The synthetic scheduling case.
        handoff_id:             The handoff the option was selected from.
        option_id:              The selected AccessOption.option_id.
        readiness_at_selection: The option's OptionReadiness at the time of
                                selection. Preserved exactly — never upgraded.
        requires_verification:  True iff readiness_at_selection is
                                AUTHORIZED_NOT_VERIFIED.
        selected_at:            Timezone-aware UTC timestamp.
        selected_by_role:       Must be ActorRole.SCHEDULER.
        selected_by_id:         Opaque actor identifier (synthetic/demo only).
        idempotency_key:        Caller-supplied deduplication key.
        synthetic:              Always True for M2 synthetic demo.
    """

    selection_id: str
    case_id: str
    handoff_id: str
    option_id: str
    readiness_at_selection: "OptionReadiness"
    requires_verification: bool
    selected_at: datetime
    selected_by_role: "ActorRole"
    selected_by_id: str
    idempotency_key: str
    synthetic: bool = True


class VerificationOutcome(StrEnum):
    """Outcome of a Community Care authorization verification.

    Supplied explicitly by the authorized Scheduler actor when resolving
    READY_TO_VERIFY. The service applies the outcome; it does not derive it.

    VERIFIED       → lifecycle target VERIFIED_BOOKABLE
    AUTH_REQUIRED  → lifecycle target AUTH_REQUIRED
    INCONCLUSIVE   → lifecycle target HUMAN_REVIEW
    """

    VERIFIED = "VERIFIED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class VerificationResult:
    """Immutable record of an actual verification resolution.

    Created by record_verification_result() for READY_TO_VERIFY resolutions,
    and by route_from_option_selected() for the VA/Federal fast path
    (OPTION_SELECTED → VERIFIED_BOOKABLE).

    NOT created for the Community Care routing-only step
    (OPTION_SELECTED → READY_TO_VERIFY). That step uses VERIFICATION_REQUIRED
    and produces no VerificationResult — explicit evidence must follow.

    verification_id is derived deterministically:
        SHA-256(idempotency_key)[:16] prefixed with "ver-"

    Fields:
        verification_id:        Deterministic ID derived from idempotency_key.
        case_id:                Synthetic scheduling case ID.
        option_id:              The AccessOption that was verified.
        source_system:          Source system of the option (e.g. VISTA_ISS).
        outcome:                VerificationOutcome — VERIFIED / AUTH_REQUIRED / INCONCLUSIVE.
        evidence_ref:           Reference to authorization evidence supplied by actor.
                                None for VA/Federal direct-booking path; non-empty
                                string required for Community Care verification.
        verified_at:            Timezone-aware UTC timestamp.
        requires_authorization: True iff outcome is AUTH_REQUIRED.
        requires_human_review:  True iff outcome is INCONCLUSIVE.
        idempotency_key:        Caller-supplied deduplication key.
        synthetic:              Always True for M2 synthetic demo.
    """

    verification_id: str
    case_id: str
    option_id: str
    source_system: str
    outcome: VerificationOutcome
    evidence_ref: Optional[str]
    verified_at: datetime
    requires_authorization: bool
    requires_human_review: bool
    idempotency_key: str
    synthetic: bool = True


# ---------------------------------------------------------------------------
# M2-6 veteran confirmation models
# ---------------------------------------------------------------------------


class VeteranResponse(StrEnum):
    """Explicit Veteran response to a confirmation request.

    Supplied by the Veteran actor when calling record_veteran_confirmation().
    The service applies the response; it does not infer it from silence or
    prior preferences.

    CONFIRMED        → lifecycle target PENDING_SCHEDULER_APPROVAL
    DECLINED         → lifecycle target CANCELLED
    REQUESTED_CHANGE → lifecycle target HUMAN_REVIEW
    """

    CONFIRMED = "CONFIRMED"
    DECLINED = "DECLINED"
    REQUESTED_CHANGE = "REQUESTED_CHANGE"


@dataclass(frozen=True)
class ConfirmationRequest:
    """Immutable confirmation request prepared for a Veteran to review.

    Created by prepare_veteran_confirmation_request() and persisted in
    ConfirmationStore. Advances lifecycle to PENDING_VETERAN_CONFIRMATION.

    confirmation_request_id is derived deterministically:
        SHA-256("confirmation:" + case_id + ":" + selection_id + ":" + option_id)[:16]
        prefixed with "cr-"

    Including selection_id prevents an old request from being reused if the
    same option is re-selected in a later lifecycle path.

    Fields:
        confirmation_request_id: Deterministic ID from case + selection + option.
        case_id:                 Synthetic scheduling case ID.
        option_id:               The AccessOption being confirmed.
        selection_id:            The OptionSelectionRecord that produced this option.
        requested_at:            Timezone-aware UTC timestamp.
        requested_by_role:       Always ActorRole.SYSTEM.
        synthetic:               Always True for M2 synthetic demo.
    """

    confirmation_request_id: str
    case_id: str
    option_id: str
    selection_id: str
    requested_at: datetime
    requested_by_role: "ActorRole"
    synthetic: bool = True


@dataclass(frozen=True)
class VeteranConfirmationRecord:
    """Immutable record of a Veteran's explicit confirmation response.

    Created by record_veteran_confirmation() and persisted in ConfirmationStore.
    The Veteran's response determines the lifecycle transition.

    confirmation_id is derived deterministically:
        SHA-256(idempotency_key)[:16] prefixed with "conf-"

    Fields:
        confirmation_id:         Deterministic ID from idempotency_key.
        confirmation_request_id: The request this record responds to.
        case_id:                 Synthetic scheduling case ID.
        option_id:               The AccessOption being confirmed.
        response:                VeteranResponse — explicit Veteran decision.
        responded_at:            Timezone-aware UTC timestamp.
        actor_role:              Always ActorRole.VETERAN.
        actor_id:                Opaque actor identifier (synthetic/demo only).
        idempotency_key:         Caller-supplied deduplication key.
        synthetic:               Always True for M2 synthetic demo.
    """

    confirmation_id: str
    confirmation_request_id: str
    case_id: str
    option_id: str
    response: VeteranResponse
    responded_at: datetime
    actor_role: "ActorRole"
    actor_id: str
    idempotency_key: str
    synthetic: bool = True


# ---------------------------------------------------------------------------
# M2-7 booking gate models
# ---------------------------------------------------------------------------


class AppointmentIntent(StrEnum):
    """Explicit intent for a scheduled appointment.

    INITIAL_CONSULT — first/new referral; may proceed via EPS when all checks pass.
    FOLLOW_UP       — subsequent visit; must NOT proceed via EPS initial-consult path.
                      FOLLOW_UP must fail closed or route to HUMAN_REVIEW.
    """

    INITIAL_CONSULT = "INITIAL_CONSULT"
    FOLLOW_UP = "FOLLOW_UP"


class HSRMAuthorizationStatus(StrEnum):
    """Status of a Community Care authorization/referral from the HSRM domain.

    Only ACTIVE authorizations may proceed to the booking gate.
    """

    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"
    DENIED = "DENIED"


@dataclass(frozen=True)
class HSRMAuthorizationRecord:
    """Synthetic HSRM authorization/referral evidence.

    Provided by SyntheticHSRMAdapter. Represents what the authorization domain
    has on record for a Community Care referral. It does not grant authorization
    — it records what has already been authorized by the appropriate party.

    Fields:
        authorization_id:       Unique HSRM authorization identifier.
        referral_id:            HSRM referral identifier.
        case_id:                Synthetic scheduling case.
        option_id:              The option this authorization covers.
        authorized_service:     Specialty/service covered (e.g. "CARDIOLOGY").
        authorized_provider_id: If provider-specific, the authorized provider.
                                None if provider-agnostic.
        status:                 HSRMAuthorizationStatus.
        effective_date:         Authorization effective date.
        expiration_date:        Authorization expiration date.
        retrieved_at:           When this record was retrieved from the adapter.
        provenance_ref:         Opaque reference string for audit/traceability.
        synthetic:              Always True for M2 synthetic demo.
    """

    authorization_id: str
    referral_id: str
    case_id: str
    option_id: str
    authorized_service: str
    status: HSRMAuthorizationStatus
    effective_date: datetime
    expiration_date: datetime
    retrieved_at: datetime
    provenance_ref: str
    authorized_provider_id: Optional[str] = None
    synthetic: bool = True


@dataclass(frozen=True)
class EPSSlotRecord:
    """Synthetic EPS provider slot state.

    Provided by SyntheticEPSAdapter. Represents what EPS has on record for a
    community provider slot. EPS never creates or infers authorization — that
    responsibility belongs to the HSRM domain.

    Fields:
        slot_id:                    Unique EPS slot identifier.
        option_id:                  The AccessOption this slot belongs to.
        provider_id:                EPS participating provider identifier.
        provider_name:              Provider display name (if available).
        appointment_start:          Scheduled slot start time.
        appointment_end:            Scheduled slot end time.
        available:                  True iff the slot is currently bookable.
        initial_consult_eligible:   True iff EPS accepts INITIAL_CONSULT for this slot.
        retrieved_at:               When this record was retrieved from the adapter.
        provenance_ref:             Opaque reference string for audit/traceability.
        synthetic:                  Always True for M2 synthetic demo.
    """

    slot_id: str
    option_id: str
    provider_id: str
    provider_name: Optional[str]
    appointment_start: datetime
    appointment_end: datetime
    available: bool
    initial_consult_eligible: bool
    retrieved_at: datetime
    provenance_ref: str
    synthetic: bool = True


@dataclass(frozen=True)
class BookingPreconditionResult:
    """Read-only result of validate_booking_preconditions().

    Never persisted. Returned by the MCP validation tool and the service
    function. A passed result does not commit any state.

    Fields:
        passed:         True iff all preconditions were satisfied.
        case_id:        The case that was checked.
        option_id:      The option that was checked.
        hsrm_checked:   True iff HSRM authorization checks ran (Community Care).
        eps_checked:    True iff EPS slot checks ran (Community Care).
        failures:       Human-readable failure reasons (empty if passed).
        synthetic:      Always True for M2 synthetic demo.
    """

    passed: bool
    case_id: str
    option_id: str
    hsrm_checked: bool
    eps_checked: bool
    failures: tuple[str, ...]
    synthetic: bool = True


@dataclass(frozen=True)
class SlotReservation:
    """In-memory slot reservation created atomically by simulated_commit().

    One per slot_id. First reservation wins. Used for double-booking protection.

    Fields:
        reservation_id: Deterministic ID from slot_id + case_id.
        slot_id:        The slot being held.
        case_id:        The case holding the reservation.
        option_id:      The option containing the slot.
        booking_id:     The BookingRecord this reservation belongs to.
        reserved_at:    Timezone-aware UTC timestamp.
        synthetic:      Always True for M2 synthetic demo.
    """

    reservation_id: str
    slot_id: str
    case_id: str
    option_id: str
    booking_id: str
    reserved_at: datetime
    synthetic: bool = True
