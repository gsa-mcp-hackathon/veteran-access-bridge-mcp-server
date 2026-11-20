"""Application services for the Veteran Access Bridge."""

from .clinic_classification import classify_patient_clinic_relationship
from .slot_matching import evaluate_slot_eligibility, match_scheduling_slots
from .internal_slot_bridge import (
    InternalSlotSearchEvidence,
    evaluate_internal_scheduling_request,
    search_internal_eligible_options,
)
from .preference_ranking import RankedAccessOption, rank_eligible_options
from .encounter_lifecycle import (
    SchedulingDecisionSnapshot,
    project_scheduling_decision,
)
from .scheduling_encounter import (
    SchedulingEncounter,
    SchedulingEncounterState,
    assemble_scheduling_encounter,
)
from .booking import (
    BookingStore,
    SlotReservationStore,
    simulated_commit,
    validate_booking_preconditions,
)
from .outcomes import record_lifecycle_event
from .confirmation import (
    ConfirmationStore,
    prepare_veteran_confirmation_request,
    record_veteran_confirmation,
)
from .orchestrate_runtime import (
    FakeOrchestrateRuntime,
    HttpOrchestrateRuntime,
    OrchestrateAuthenticationError,
    OrchestrateConfig,
    OrchestrateProtocolError,
    OrchestrateRuntime,
    OrchestrateRuntimeError,
    OrchestrateTimeoutError,
    OrchestrateUnavailableError,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeInteraction,
)
from .interaction_events import (
    InteractionEventConflictError,
    InteractionEventStore,
    project_case_event,
)
from .events import (
    CaseEventStore,
    IdempotencyConflictError,
    InvalidTransitionError,
    TerminalStateError,
)
from .handoff import HandoffStore, prepare_scheduling_handoff
from .selection import (
    SelectionStore,
    record_option_selection,
    validate_option_selection,
)
from .verification import (
    VerificationStore,
    record_verification_result,
    route_from_option_selected,
)

__all__ = [
    "classify_patient_clinic_relationship",
    "evaluate_slot_eligibility",
    "match_scheduling_slots",
    "InternalSlotSearchEvidence",
    "evaluate_internal_scheduling_request",
    "search_internal_eligible_options",
    "RankedAccessOption",
    "rank_eligible_options",
    "SchedulingDecisionSnapshot",
    "project_scheduling_decision",
    "SchedulingEncounter",
    "SchedulingEncounterState",
    "assemble_scheduling_encounter",
    "CaseEventStore",
    "IdempotencyConflictError",
    "InvalidTransitionError",
    "TerminalStateError",
    "HandoffStore",
    "prepare_scheduling_handoff",
    "SelectionStore",
    "record_option_selection",
    "validate_option_selection",
    "VerificationStore",
    "record_verification_result",
    "route_from_option_selected",
    "ConfirmationStore",
    "prepare_veteran_confirmation_request",
    "record_veteran_confirmation",
    "BookingStore",
    "SlotReservationStore",
    "simulated_commit",
    "validate_booking_preconditions",
    "record_lifecycle_event",
    "InteractionEventConflictError",
    "InteractionEventStore",
    "project_case_event",
    "FakeOrchestrateRuntime",
    "HttpOrchestrateRuntime",
    "OrchestrateAuthenticationError",
    "OrchestrateConfig",
    "OrchestrateProtocolError",
    "OrchestrateRuntime",
    "OrchestrateRuntimeError",
    "OrchestrateTimeoutError",
    "OrchestrateUnavailableError",
    "RuntimeEvent",
    "RuntimeEventType",
    "RuntimeInteraction",
]
