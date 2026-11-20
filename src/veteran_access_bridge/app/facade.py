"""Role-neutral application facade that reuses the M2 service layer.

M3/M4 intentionally do not duplicate business rules in the HTTP layer. The
facade composes the existing lifecycle, selection, verification, confirmation,
booking, and outcome services while the API enforces who may invoke each action.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any

from veteran_access_bridge.adapters.eps import SyntheticEPSAdapter
from veteran_access_bridge.adapters.hsrm import SyntheticHSRMAdapter
from veteran_access_bridge.domain.models import (
    ActorRole,
    AppointmentIntent,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    VerificationOutcome,
    VeteranResponse,
)
from veteran_access_bridge.mcp.cases import demo_as_of, load_demo_case
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.services.booking import (
    BookingStore,
    SlotReservationStore,
    simulated_commit,
    validate_booking_preconditions,
)
from veteran_access_bridge.services.confirmation import (
    ConfirmationStore,
    prepare_veteran_confirmation_request,
    record_veteran_confirmation,
)
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.handoff import (
    HandoffStore,
    prepare_scheduling_handoff,
)
from veteran_access_bridge.services.outcomes import record_lifecycle_event
from veteran_access_bridge.services.search import search_availability
from veteran_access_bridge.services.selection import (
    SelectionStore,
    record_option_selection,
)
from veteran_access_bridge.services.verification import (
    VerificationStore,
    record_verification_result,
    route_from_option_selected,
)

DEMO_CASE_ID = "DEMO-CARD-5000335-001"


@dataclass
class ApplicationStores:
    event_store: CaseEventStore
    handoff_store: HandoffStore
    selection_store: SelectionStore
    verification_store: VerificationStore
    confirmation_store: ConfirmationStore
    booking_store: BookingStore
    reservation_store: SlotReservationStore

    @classmethod
    def fresh(cls) -> "ApplicationStores":
        return cls(
            event_store=CaseEventStore(),
            handoff_store=HandoffStore(),
            selection_store=SelectionStore(),
            verification_store=VerificationStore(),
            confirmation_store=ConfirmationStore(),
            booking_store=BookingStore(),
            reservation_store=SlotReservationStore(),
        )


def shared_stores() -> ApplicationStores:
    # Import the module, not copied singleton names, so this facade always sees
    # the canonical process-level state objects.
    from veteran_access_bridge.mcp import state

    return ApplicationStores(
        event_store=state.event_store,
        handoff_store=state.handoff_store,
        selection_store=state.selection_store,
        verification_store=state.verification_store,
        confirmation_store=state.confirmation_store,
        booking_store=state.booking_store,
        reservation_store=state.reservation_store,
    )


class DemoApplication:
    """Thread-serialized application facade for the synthetic demo."""

    def __init__(
        self,
        stores: ApplicationStores | None = None,
        *,
        hsrm_adapter: SyntheticHSRMAdapter | None = None,
        eps_adapter: SyntheticEPSAdapter | None = None,
    ) -> None:
        self.stores = stores if stores is not None else shared_stores()
        self.hsrm = hsrm_adapter or SyntheticHSRMAdapter()
        self.eps = eps_adapter or SyntheticEPSAdapter()
        self._lock = RLock()

    def ensure_demo_ready(self, case_id: str = DEMO_CASE_ID) -> None:
        """Seed the canonical synthetic case through HUMAN_REVIEW once."""
        with self._lock:
            current = self.stores.event_store.get_lifecycle_record(case_id)
            if current is not None:
                return

            at = demo_as_of()
            self.stores.event_store.append(
                CaseEvent(
                    event_id=f"{case_id}:DEMO_GATE",
                    case_id=case_id,
                    event_type=CaseEventType.WORKFLOW_GATE_EVALUATED,
                    from_state=CaseLifecycleState.REQUEST_RECEIVED,
                    to_state=CaseLifecycleState.READY_TO_SEARCH,
                    actor_role=ActorRole.SYSTEM,
                    actor_id="demo-bootstrap",
                    occurred_at=at,
                    idempotency_key=f"{case_id}:DEMO_GATE",
                    payload={"synthetic_bootstrap": True},
                )
            )
            patient, consult = load_demo_case(case_id)
            result = search_availability(patient, consult, _as_of=at)
            self.stores.event_store.append(
                CaseEvent(
                    event_id=f"{case_id}:DEMO_SEARCH",
                    case_id=case_id,
                    event_type=CaseEventType.SEARCH_EXECUTED,
                    from_state=CaseLifecycleState.READY_TO_SEARCH,
                    to_state=CaseLifecycleState.COMMUNITY_OPTIONS_AVAILABLE,
                    actor_role=ActorRole.SYSTEM,
                    actor_id="demo-bootstrap",
                    occurred_at=at,
                    idempotency_key=f"{case_id}:DEMO_SEARCH",
                    payload={
                        "source_count": len(result.source_results),
                        "option_count": len(result.options),
                    },
                )
            )
            self.stores.event_store.append(
                CaseEvent(
                    event_id=f"{case_id}:DEMO_OPTIONS_ASSESSED",
                    case_id=case_id,
                    event_type=CaseEventType.OPTIONS_ASSESSED,
                    from_state=CaseLifecycleState.COMMUNITY_OPTIONS_AVAILABLE,
                    to_state=CaseLifecycleState.READY_FOR_HANDOFF,
                    actor_role=ActorRole.SYSTEM,
                    actor_id="demo-bootstrap",
                    occurred_at=at,
                    idempotency_key=f"{case_id}:DEMO_OPTIONS_ASSESSED",
                    payload={"viable_option_count": len(result.options)},
                )
            )
            prepare_scheduling_handoff(
                case_id=case_id,
                search_result=result,
                event_store=self.stores.event_store,
                handoff_store=self.stores.handoff_store,
                actor_id="demo-bootstrap",
                _as_of=at,
            )

    def _handoff_for_case(self, case_id: str):
        selection = self.stores.selection_store.get_for_case(case_id)
        if selection is not None:
            handoff = self.stores.handoff_store.get(selection.handoff_id)
            if handoff is not None:
                return handoff
        for event in reversed(self.stores.event_store.get_events(case_id)):
            if event.payload and event.payload.get("handoff_id"):
                handoff = self.stores.handoff_store.get(event.payload["handoff_id"])
                if handoff is not None:
                    return handoff
        return None

    def _selected_option(self, case_id: str):
        selection = self.stores.selection_store.get_for_case(case_id)
        if selection is None:
            return None, None
        handoff = self.stores.handoff_store.get(selection.handoff_id)
        if handoff is None:
            return selection, None
        option = next(
            (item for item in handoff.options if item.option_id == selection.option_id),
            None,
        )
        return selection, option

    def _booking_for_case(self, case_id: str):
        for event in reversed(self.stores.event_store.get_events(case_id)):
            if event.event_type == CaseEventType.BOOKED_SIMULATED and event.payload:
                booking_id = event.payload.get("booking_id")
                if booking_id:
                    return self.stores.booking_store.get(booking_id)
        return None

    def snapshot(
        self,
        case_id: str = DEMO_CASE_ID,
        *,
        include_audit: bool = False,
    ) -> dict[str, Any]:
        self.ensure_demo_ready(case_id)
        patient, consult = load_demo_case(case_id)
        lifecycle = self.stores.event_store.get_lifecycle_record(case_id)
        handoff = self._handoff_for_case(case_id)
        selection, selected_option = self._selected_option(case_id)
        verification = self.stores.verification_store.get_for_case(case_id)
        request = self.stores.confirmation_store.get_request_for_case(case_id)
        confirmation = self.stores.confirmation_store.get_confirmation_for_case(case_id)
        booking = self._booking_for_case(case_id)

        payload: dict[str, Any] = {
            "synthetic": True,
            "case_id": case_id,
            "patient": {
                "patient_id": patient.patient_id,
                "display_name": patient.display_name,
                "city": patient.city,
                "state": patient.state,
            },
            "consult": {
                "consult_id": consult.consult_id,
                "specialty": consult.specialty,
                "status": consult.status,
                "valid": consult.valid,
            },
            "lifecycle": to_jsonable(lifecycle) if lifecycle else None,
            "handoff": to_jsonable(handoff) if handoff else None,
            "selection": to_jsonable(selection) if selection else None,
            "selected_option": (
                to_jsonable(selected_option) if selected_option else None
            ),
            "verification": to_jsonable(verification) if verification else None,
            "confirmation_request": to_jsonable(request) if request else None,
            "veteran_confirmation": to_jsonable(confirmation) if confirmation else None,
            "booking": to_jsonable(booking) if booking else None,
        }
        if include_audit:
            payload["audit"] = [
                to_jsonable(event)
                for event in self.stores.event_store.get_events(case_id)
            ]
        return payload

    def select_option(
        self,
        *,
        case_id: str,
        option_id: str,
        actor_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        with self._lock:
            self.ensure_demo_ready(case_id)
            handoff = self._handoff_for_case(case_id)
            if handoff is None:
                raise ValueError(f"No SchedulingHandoff found for case {case_id!r}.")
            record = record_option_selection(
                case_id=case_id,
                handoff_id=handoff.handoff_id,
                option_id=option_id,
                actor_role=ActorRole.SCHEDULER,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                event_store=self.stores.event_store,
                handoff_store=self.stores.handoff_store,
                selection_store=self.stores.selection_store,
            )
            routed = route_from_option_selected(
                case_id=case_id,
                selection_id=record.selection_id,
                idempotency_key=f"{idempotency_key}:route",
                event_store=self.stores.event_store,
                selection_store=self.stores.selection_store,
                verification_store=self.stores.verification_store,
            )
            return {
                "selection": to_jsonable(record),
                "routing_verification": to_jsonable(routed) if routed else None,
                "lifecycle": to_jsonable(
                    self.stores.event_store.get_lifecycle_record(case_id)
                ),
            }

    def verify_selected_option(
        self,
        *,
        case_id: str,
        actor_id: str,
        evidence_ref: str,
        outcome: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        with self._lock:
            selection, option = self._selected_option(case_id)
            if selection is None or option is None:
                raise ValueError("No selected option is available for verification.")
            try:
                verification_outcome = VerificationOutcome(outcome)
            except ValueError as exc:
                raise ValueError(f"Invalid verification outcome {outcome!r}.") from exc
            result = record_verification_result(
                case_id=case_id,
                option_id=option.option_id,
                source_system=option.source_system,
                evidence_ref=evidence_ref,
                outcome=verification_outcome,
                actor_role=ActorRole.SCHEDULER,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                event_store=self.stores.event_store,
                verification_store=self.stores.verification_store,
            )
            return to_jsonable(result)

    def request_veteran_confirmation(
        self,
        *,
        case_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            selection, option = self._selected_option(case_id)
            if selection is None or option is None:
                raise ValueError("No selected option is available for confirmation.")
            request = prepare_veteran_confirmation_request(
                case_id=case_id,
                option_id=option.option_id,
                selection_id=selection.selection_id,
                event_store=self.stores.event_store,
                selection_store=self.stores.selection_store,
                confirmation_store=self.stores.confirmation_store,
            )
            return to_jsonable(request)

    def record_veteran_response(
        self,
        *,
        case_id: str,
        actor_id: str,
        response: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        with self._lock:
            request = self.stores.confirmation_store.get_request_for_case(case_id)
            selection, option = self._selected_option(case_id)
            if request is None or selection is None or option is None:
                raise ValueError("No pending confirmation request is available.")
            try:
                veteran_response = VeteranResponse(response)
            except ValueError as exc:
                raise ValueError(f"Invalid Veteran response {response!r}.") from exc
            record = record_veteran_confirmation(
                case_id=case_id,
                confirmation_request_id=request.confirmation_request_id,
                option_id=option.option_id,
                response=veteran_response,
                actor_role=ActorRole.VETERAN,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                event_store=self.stores.event_store,
                confirmation_store=self.stores.confirmation_store,
            )
            return to_jsonable(record)

    def commit_selected_booking(
        self,
        *,
        case_id: str,
        actor_id: str,
        idempotency_key: str,
        appointment_intent: str = "INITIAL_CONSULT",
    ) -> dict[str, Any]:
        with self._lock:
            selection, option = self._selected_option(case_id)
            if selection is None or option is None:
                raise ValueError("No selected option is available for booking.")
            patient, consult = load_demo_case(case_id)
            try:
                intent = AppointmentIntent(appointment_intent)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid appointment_intent {appointment_intent!r}."
                ) from exc

            slot_id = option.source_record_id
            is_cc = option.source_system.upper() == "COMMUNITY_CARE_EPS"
            hsrm_record = (
                self.hsrm.get_authorization_for_option(option.option_id)
                if is_cc
                else None
            )
            eps_slot = self.eps.get_slot(slot_id) if is_cc else None

            gate = validate_booking_preconditions(
                case_id=case_id,
                option_id=option.option_id,
                slot_id=slot_id,
                source_system=option.source_system,
                intended_service=consult.specialty,
                appointment_intent=intent,
                actor_role=ActorRole.SCHEDULER,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                event_store=self.stores.event_store,
                confirmation_store=self.stores.confirmation_store,
                selection_store=self.stores.selection_store,
                booking_store=self.stores.booking_store,
                hsrm_record=hsrm_record,
                eps_slot=eps_slot,
            )
            if not gate.passed:
                raise ValueError(
                    "Booking preconditions failed: " + " | ".join(gate.failures)
                )

            booking = simulated_commit(
                case_id=case_id,
                option_id=option.option_id,
                slot_id=slot_id,
                source_system=option.source_system,
                intended_service=consult.specialty,
                appointment_intent=intent,
                patient_id=patient.patient_id,
                consult_id=consult.consult_id,
                handoff_id=selection.handoff_id,
                facility_name=option.facility_name,
                actor_role=ActorRole.SCHEDULER,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                event_store=self.stores.event_store,
                confirmation_store=self.stores.confirmation_store,
                selection_store=self.stores.selection_store,
                booking_store=self.stores.booking_store,
                reservation_store=self.stores.reservation_store,
                hsrm_record=hsrm_record,
                eps_slot=eps_slot,
            )
            return {
                "preconditions": to_jsonable(gate),
                "booking": to_jsonable(booking),
            }

    def record_outcome(
        self,
        *,
        case_id: str,
        actor_id: str,
        event_type: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        with self._lock:
            try:
                outcome_event = CaseEventType(event_type)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid lifecycle event type {event_type!r}."
                ) from exc
            event = record_lifecycle_event(
                case_id=case_id,
                event_type=outcome_event,
                actor_role=ActorRole.SCHEDULER,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                event_store=self.stores.event_store,
            )
            return to_jsonable(event)
