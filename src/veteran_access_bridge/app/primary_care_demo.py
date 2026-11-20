"""Primary Care Demo A lifecycle coordinator.

Issue #73.

This application service advances the synthetic direct Primary Care demo
without coercing the request into the legacy specialty-consult lifecycle.
All option eligibility remains upstream in the governed Scheduling Encounter.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import uuid4

from veteran_access_bridge.domain import (
    InteractionEvent,
    InteractionEventSource,
    InteractionEventType,
)
from veteran_access_bridge.services.interaction_events import InteractionEventStore


class PrimaryCareDemoState(StrEnum):
    OPTIONS_READY = "OPTIONS_READY"
    SLOT_SELECTED = "SLOT_SELECTED"
    SLOT_VERIFIED = "SLOT_VERIFIED"
    VETERAN_CONFIRMED = "VETERAN_CONFIRMED"
    MSA_APPROVAL_PENDING = "MSA_APPROVAL_PENDING"
    MSA_APPROVED = "MSA_APPROVED"
    SIMULATED_BOOKED = "SIMULATED_BOOKED"


@dataclass(frozen=True)
class PrimaryCareDemoRecord:
    case_id: str
    scheduling_encounter_id: str
    state: PrimaryCareDemoState = PrimaryCareDemoState.OPTIONS_READY
    selected_option_id: str | None = None
    verified_option_id: str | None = None
    veteran_confirmed: bool = False
    msa_approved: bool = False
    booking_id: str | None = None
    synthetic: bool = True


class PrimaryCareDemoLifecycle:
    def __init__(self) -> None:
        self._records: dict[str, PrimaryCareDemoRecord] = {}

    def get(self, case_id: str, scheduling_encounter_id: str) -> PrimaryCareDemoRecord:
        record = self._records.get(case_id)
        if record is None:
            record = PrimaryCareDemoRecord(
                case_id=case_id,
                scheduling_encounter_id=scheduling_encounter_id,
            )
            self._records[case_id] = record
        return record

    def reset(
        self,
        case_id: str,
        scheduling_encounter_id: str,
    ) -> PrimaryCareDemoRecord:
        """Start a fresh single-active synthetic demo for this case."""

        record = PrimaryCareDemoRecord(
            case_id=case_id,
            scheduling_encounter_id=scheduling_encounter_id,
        )
        self._records[case_id] = record
        return record

    def select(
        self,
        *,
        case_id: str,
        scheduling_encounter_id: str,
        option_id: str,
        eligible_option_ids: set[str],
        event_store: InteractionEventStore,
        interaction_id: str,
        correlation_id: str,
    ) -> PrimaryCareDemoRecord:
        record = self.get(case_id, scheduling_encounter_id)
        if option_id not in eligible_option_ids:
            raise ValueError("Only a governed eligible option may be selected.")
        if record.state not in {
            PrimaryCareDemoState.OPTIONS_READY,
            PrimaryCareDemoState.SLOT_SELECTED,
        }:
            raise ValueError(f"Selection is not permitted from {record.state.value}.")

        updated = replace(
            record,
            state=PrimaryCareDemoState.SLOT_SELECTED,
            selected_option_id=option_id,
            verified_option_id=None,
            veteran_confirmed=False,
            msa_approved=False,
            booking_id=None,
        )
        self._records[case_id] = updated
        self._emit(
            event_store,
            event_type=InteractionEventType.VETERAN_SELECTED,
            source=InteractionEventSource.APPLICATION,
            interaction_id=interaction_id,
            case_id=case_id,
            scheduling_encounter_id=scheduling_encounter_id,
            correlation_id=correlation_id,
            payload={"option_id": option_id},
        )
        return updated

    def verify(
        self,
        *,
        case_id: str,
        scheduling_encounter_id: str,
        option_id: str,
        event_store: InteractionEventStore,
        interaction_id: str,
        correlation_id: str,
    ) -> PrimaryCareDemoRecord:
        record = self.get(case_id, scheduling_encounter_id)
        if record.state is not PrimaryCareDemoState.SLOT_SELECTED:
            raise ValueError("A governed option must be selected before verification.")
        if record.selected_option_id != option_id:
            raise ValueError("Verification must target the selected option.")

        updated = replace(
            record,
            state=PrimaryCareDemoState.SLOT_VERIFIED,
            verified_option_id=option_id,
        )
        self._records[case_id] = updated
        self._emit(
            event_store,
            event_type=InteractionEventType.SLOT_VERIFIED,
            source=InteractionEventSource.DETERMINISTIC_SERVICE,
            interaction_id=interaction_id,
            case_id=case_id,
            scheduling_encounter_id=scheduling_encounter_id,
            correlation_id=correlation_id,
            payload={"option_id": option_id, "verification": "VERIFIED"},
        )
        return updated

    def confirm(
        self,
        *,
        case_id: str,
        scheduling_encounter_id: str,
        event_store: InteractionEventStore,
        interaction_id: str,
        correlation_id: str,
    ) -> PrimaryCareDemoRecord:
        record = self.get(case_id, scheduling_encounter_id)
        if record.state is not PrimaryCareDemoState.SLOT_VERIFIED:
            raise ValueError("Veteran confirmation requires a verified slot.")

        updated = replace(
            record,
            state=PrimaryCareDemoState.MSA_APPROVAL_PENDING,
            veteran_confirmed=True,
        )
        self._records[case_id] = updated
        self._emit(
            event_store,
            event_type=InteractionEventType.VETERAN_CONFIRMED,
            source=InteractionEventSource.APPLICATION,
            interaction_id=interaction_id,
            case_id=case_id,
            scheduling_encounter_id=scheduling_encounter_id,
            correlation_id=correlation_id,
            payload={"option_id": record.selected_option_id},
        )
        return updated

    def approve(
        self,
        *,
        case_id: str,
        scheduling_encounter_id: str,
        event_store: InteractionEventStore,
        interaction_id: str,
        correlation_id: str,
    ) -> PrimaryCareDemoRecord:
        record = self.get(case_id, scheduling_encounter_id)
        if record.state is not PrimaryCareDemoState.MSA_APPROVAL_PENDING:
            raise ValueError("MSA approval requires explicit Veteran confirmation.")

        updated = replace(
            record,
            state=PrimaryCareDemoState.MSA_APPROVED,
            msa_approved=True,
        )
        self._records[case_id] = updated
        self._emit(
            event_store,
            event_type=InteractionEventType.MSA_APPROVED,
            source=InteractionEventSource.MSA,
            interaction_id=interaction_id,
            case_id=case_id,
            scheduling_encounter_id=scheduling_encounter_id,
            correlation_id=correlation_id,
            payload={"option_id": record.selected_option_id},
        )
        return updated

    def book(
        self,
        *,
        case_id: str,
        scheduling_encounter_id: str,
        event_store: InteractionEventStore,
        interaction_id: str,
        correlation_id: str,
    ) -> PrimaryCareDemoRecord:
        record = self.get(case_id, scheduling_encounter_id)
        if record.state is not PrimaryCareDemoState.MSA_APPROVED:
            raise ValueError("Simulated booking requires explicit MSA approval.")

        booking_id = record.booking_id or f"sim-book-{uuid4().hex[:12]}"
        updated = replace(
            record,
            state=PrimaryCareDemoState.SIMULATED_BOOKED,
            booking_id=booking_id,
        )
        self._records[case_id] = updated
        self._emit(
            event_store,
            event_type=InteractionEventType.SIMULATED_BOOKING_RECORDED,
            source=InteractionEventSource.APPLICATION,
            interaction_id=interaction_id,
            case_id=case_id,
            scheduling_encounter_id=scheduling_encounter_id,
            correlation_id=correlation_id,
            payload={
                "option_id": record.selected_option_id,
                "booking_id": booking_id,
                "synthetic": True,
                "production_write": False,
            },
        )
        return updated

    @staticmethod
    def _emit(
        event_store: InteractionEventStore,
        *,
        event_type: InteractionEventType,
        source: InteractionEventSource,
        interaction_id: str,
        case_id: str,
        scheduling_encounter_id: str,
        correlation_id: str,
        payload: dict,
    ) -> None:
        from datetime import datetime, timezone

        event_store.append(
            InteractionEvent(
                event_id=f"evt-{uuid4().hex[:16]}",
                event_type=event_type,
                interaction_id=interaction_id,
                case_id=case_id,
                scheduling_encounter_id=scheduling_encounter_id,
                correlation_id=correlation_id,
                source=source,
                occurred_at=datetime.now(timezone.utc),
                payload=payload,
            )
        )


def to_dict(record: PrimaryCareDemoRecord) -> dict[str, object]:
    return {
        "case_id": record.case_id,
        "scheduling_encounter_id": record.scheduling_encounter_id,
        "state": record.state.value,
        "selected_option_id": record.selected_option_id,
        "verified_option_id": record.verified_option_id,
        "veteran_confirmed": record.veteran_confirmed,
        "msa_approved": record.msa_approved,
        "booking_id": record.booking_id,
        "synthetic": record.synthetic,
    }


def apply_calendar_overlay(
    calendar: list[dict],
    record: PrimaryCareDemoRecord,
) -> list[dict]:
    projected: list[dict] = []
    for item in calendar:
        copy = dict(item)
        option_id = copy.get("option_id")
        if option_id and option_id == record.selected_option_id:
            if record.state is PrimaryCareDemoState.SLOT_SELECTED:
                copy["state"] = "SELECTED"
            elif record.state in {
                PrimaryCareDemoState.SLOT_VERIFIED,
                PrimaryCareDemoState.VETERAN_CONFIRMED,
                PrimaryCareDemoState.MSA_APPROVAL_PENDING,
                PrimaryCareDemoState.MSA_APPROVED,
            }:
                copy["state"] = "VERIFIED"
            elif record.state is PrimaryCareDemoState.SIMULATED_BOOKED:
                copy["state"] = "SIMULATED_BOOKED"
        projected.append(copy)
    return projected


def next_permitted_action(record: PrimaryCareDemoRecord) -> str:
    return {
        PrimaryCareDemoState.OPTIONS_READY: "SELECT_ELIGIBLE_OPTION",
        PrimaryCareDemoState.SLOT_SELECTED: "VERIFY_SELECTED_SLOT",
        PrimaryCareDemoState.SLOT_VERIFIED: "VETERAN_CONFIRMATION",
        PrimaryCareDemoState.VETERAN_CONFIRMED: "MSA_APPROVAL",
        PrimaryCareDemoState.MSA_APPROVAL_PENDING: "MSA_APPROVAL",
        PrimaryCareDemoState.MSA_APPROVED: "COMMIT_SIMULATED_BOOKING",
        PrimaryCareDemoState.SIMULATED_BOOKED: "NO_FURTHER_BOOKING_ACTION",
    }[record.state]
