"""Live interaction event services for the MSA workspace.

The InteractionEventStore is an append-only projection store. It is not a
scheduling state machine. The existing CaseEventStore remains authoritative for
persisted scheduling lifecycle transitions.
"""

from __future__ import annotations

from typing import Optional

from veteran_access_bridge.domain.interaction_events import (
    InteractionEvent,
    InteractionEventSource,
    InteractionEventType,
)
from veteran_access_bridge.domain.models import CaseEvent, CaseEventType


class InteractionEventConflictError(ValueError):
    """Raised when an event_id is reused with different content."""


class InteractionEventStore:
    """Append-only in-memory stream used by the synthetic live MSA experience."""

    def __init__(self) -> None:
        self._history: dict[str, list[InteractionEvent]] = {}
        self._event_index: dict[str, InteractionEvent] = {}

    def append(self, event: InteractionEvent) -> InteractionEvent:
        existing = self._event_index.get(event.event_id)
        if existing is not None:
            if existing == event:
                return existing
            raise InteractionEventConflictError(
                f"event_id {event.event_id!r} already exists with different content."
            )

        self._history.setdefault(event.interaction_id, []).append(event)
        self._event_index[event.event_id] = event
        return event

    def get_events(self, interaction_id: str) -> tuple[InteractionEvent, ...]:
        return tuple(self._history.get(interaction_id, ()))

    def get_event(self, event_id: str) -> Optional[InteractionEvent]:
        return self._event_index.get(event_id)

    def get_events_after(
        self,
        interaction_id: str,
        event_id: str | None,
    ) -> tuple[InteractionEvent, ...]:
        """Return events after a cursor for SSE reconnect/replay."""

        events = self.get_events(interaction_id)
        if event_id is None:
            return events

        for index, event in enumerate(events):
            if event.event_id == event_id:
                return events[index + 1 :]
        return events

    def interaction_ids(self) -> frozenset[str]:
        return frozenset(self._history)


_LIFECYCLE_TO_LIVE_EVENT: dict[
    CaseEventType, tuple[InteractionEventType, InteractionEventSource]
] = {
    CaseEventType.VERIFICATION_PASSED: (
        InteractionEventType.SLOT_VERIFIED,
        InteractionEventSource.DETERMINISTIC_SERVICE,
    ),
    CaseEventType.VETERAN_CONFIRMED: (
        InteractionEventType.VETERAN_CONFIRMED,
        InteractionEventSource.APPLICATION,
    ),
    CaseEventType.SCHEDULER_APPROVED: (
        InteractionEventType.MSA_APPROVED,
        InteractionEventSource.MSA,
    ),
    CaseEventType.BOOKED_SIMULATED: (
        InteractionEventType.SIMULATED_BOOKING_RECORDED,
        InteractionEventSource.APPLICATION,
    ),
}


def project_case_event(
    event: CaseEvent,
    *,
    interaction_id: str,
    scheduling_encounter_id: str,
    correlation_id: str,
) -> InteractionEvent | None:
    """Project an exact-semantic lifecycle event into the live event stream.

    Returns None when there is no exact mapping. This is intentional: live
    events such as intent_captured, eligibility_updated, or options_presented
    must be emitted by the component that actually performed that work rather
    than inferred from a loosely related lifecycle transition.
    """

    mapping = _LIFECYCLE_TO_LIVE_EVENT.get(event.event_type)
    if mapping is None:
        return None

    event_type, source = mapping
    return InteractionEvent(
        event_id=f"live-{event.event_id}",
        event_type=event_type,
        interaction_id=interaction_id,
        case_id=event.case_id,
        scheduling_encounter_id=scheduling_encounter_id,
        correlation_id=correlation_id,
        source=source,
        occurred_at=event.occurred_at,
        synthetic=event.synthetic,
        payload={
            "case_event_id": event.event_id,
            **dict(event.payload),
        },
    )
