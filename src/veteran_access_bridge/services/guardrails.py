"""Application projection helpers for workflow control assessments.

Issue #76 integration with Issue #70 live events.
"""

from __future__ import annotations

from datetime import datetime

from veteran_access_bridge.domain.guardrails import (
    GuardrailAssessment,
    HandoffRequirement,
)
from veteran_access_bridge.domain.interaction_events import (
    InteractionEvent,
    InteractionEventSource,
    InteractionEventType,
)


def build_guardrail_event(
    assessment: GuardrailAssessment,
    *,
    event_id: str,
    interaction_id: str,
    case_id: str,
    scheduling_encounter_id: str,
    correlation_id: str,
    occurred_at: datetime,
) -> InteractionEvent | None:
    """Project a control assessment into the live MSA event stream."""

    if assessment.handoff is HandoffRequirement.NONE:
        return None

    if assessment.handoff is HandoffRequirement.ADVISORY:
        event_type = InteractionEventType.HUMAN_ATTENTION_RECOMMENDED
    else:
        event_type = InteractionEventType.TRANSFER_REQUESTED

    return InteractionEvent(
        event_id=event_id,
        event_type=event_type,
        interaction_id=interaction_id,
        case_id=case_id,
        scheduling_encounter_id=scheduling_encounter_id,
        correlation_id=correlation_id,
        source=InteractionEventSource.APPLICATION,
        occurred_at=occurred_at,
        synthetic=True,
        payload=dict(assessment.handoff_payload),
    )
