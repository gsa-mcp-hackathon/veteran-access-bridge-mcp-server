"""Normalized live interaction events for the MSA workspace.

Issue #70.

These events are projections for real-time UI/runtime consumption. They do not
advance CaseLifecycleState and do not replace CaseEvent/CaseEventStore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class InteractionEventType(StrEnum):
    """Canonical live events consumed by the MSA workspace."""

    INTERACTION_RECEIVED = "interaction_received"
    VETERAN_UTTERANCE = "veteran_utterance"
    AGENT_ANSWERED = "agent_answered"
    MCP_TOOL_CALLED = "mcp_tool_called"
    MCP_TOOL_RESULT = "mcp_tool_result"

    INTENT_CAPTURED = "intent_captured"
    PREFERENCE_CAPTURED = "preference_captured"
    PREFERRED_DATE_CAPTURED = "preferred_date_captured"
    PROVIDER_REQUESTED_DATE_LOADED = "provider_requested_date_loaded"
    SCHEDULING_WINDOW_ESTABLISHED = "scheduling_window_established"

    ENCOUNTER_LOADED = "encounter_loaded"
    ELIGIBILITY_UPDATED = "eligibility_updated"
    ACCESS_ASSESSED = "access_assessed"
    OPTIONS_PRESENTED = "options_presented"

    VETERAN_SELECTED = "veteran_selected"
    HUMAN_ATTENTION_RECOMMENDED = "human_attention_recommended"
    TRANSFER_REQUESTED = "transfer_requested"
    MSA_JOINED = "msa_joined"
    VETERAN_CONFIRMED = "veteran_confirmed"
    VOICE_IDENTITY_VERIFIED = "voice_identity_verified"
    SLOT_VERIFIED = "slot_verified"
    MSA_APPROVED = "msa_approved"
    SIMULATED_BOOKING_RECORDED = "simulated_booking_recorded"

    CONTACT_ATTEMPT_RECORDED = "contact_attempt_recorded"
    INTERACTION_ENDED = "interaction_ended"


class InteractionEventSource(StrEnum):
    """System/component that produced an MSA live event."""

    CONVERSATION = "conversation"
    WATSONX_ORCHESTRATE = "watsonx_orchestrate"
    DETERMINISTIC_SERVICE = "deterministic_service"
    SCHEDULING_ADAPTER = "scheduling_adapter"
    MSA = "msa"
    APPLICATION = "application"


# Events whose payload may contain conversational extraction results.
CONVERSATION_EVENT_TYPES = frozenset(
    {
        InteractionEventType.VETERAN_UTTERANCE,
        InteractionEventType.INTENT_CAPTURED,
        InteractionEventType.PREFERENCE_CAPTURED,
        InteractionEventType.PREFERRED_DATE_CAPTURED,
    }
)

# Governed/deterministic scheduling evidence must never be emitted as if it
# were inferred from the conversation.
DETERMINISTIC_EVENT_TYPES = frozenset(
    {
        InteractionEventType.ELIGIBILITY_UPDATED,
        InteractionEventType.ACCESS_ASSESSED,
    }
)

GOVERNED_EVENT_TYPES = frozenset(
    {
        InteractionEventType.PROVIDER_REQUESTED_DATE_LOADED,
        InteractionEventType.ENCOUNTER_LOADED,
        InteractionEventType.SLOT_VERIFIED,
    }
)


@dataclass(frozen=True)
class InteractionEvent:
    """One normalized live-event envelope for the MSA workspace.

    The envelope correlates interaction/runtime data to the governed scheduling
    encounter but does not mutate scheduling state.
    """

    event_id: str
    event_type: InteractionEventType
    interaction_id: str
    case_id: str
    scheduling_encounter_id: str
    correlation_id: str
    source: InteractionEventSource
    occurred_at: datetime
    synthetic: bool = True
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in (
            "event_id",
            "interaction_id",
            "case_id",
            "scheduling_encounter_id",
            "correlation_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} is required.")

        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware.")

        if not self.synthetic:
            raise ValueError("MSA live-event MVP values must be synthetic.")

        if self.source is InteractionEventSource.CONVERSATION:
            if self.event_type in DETERMINISTIC_EVENT_TYPES:
                raise ValueError(
                    f"{self.event_type.value} cannot be sourced from conversation."
                )
            if self.event_type in GOVERNED_EVENT_TYPES:
                raise ValueError(
                    f"{self.event_type.value} requires governed/system evidence "
                    "and cannot be sourced from conversation."
                )

        if self.event_type is InteractionEventType.MSA_APPROVED:
            if self.source is not InteractionEventSource.MSA:
                raise ValueError("msa_approved must be emitted by the MSA source.")

        if self.event_type is InteractionEventType.VETERAN_CONFIRMED:
            if self.source not in {
                InteractionEventSource.CONVERSATION,
                InteractionEventSource.APPLICATION,
            }:
                raise ValueError(
                    "veteran_confirmed must originate from the Veteran interaction "
                    "or application projection."
                )

        if self.event_type is InteractionEventType.SIMULATED_BOOKING_RECORDED:
            if self.source is not InteractionEventSource.APPLICATION:
                raise ValueError(
                    "simulated_booking_recorded must be emitted by the application."
                )


def event_to_dict(event: InteractionEvent) -> dict[str, Any]:
    """Serialize a normalized event for API/SSE projection."""

    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "interaction_id": event.interaction_id,
        "case_id": event.case_id,
        "scheduling_encounter_id": event.scheduling_encounter_id,
        "correlation_id": event.correlation_id,
        "source": event.source.value,
        "occurred_at": event.occurred_at.isoformat(),
        "synthetic": event.synthetic,
        "payload": dict(event.payload),
    }
