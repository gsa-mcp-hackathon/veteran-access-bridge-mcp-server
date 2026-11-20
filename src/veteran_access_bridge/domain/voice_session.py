"""Transport-neutral call and voice-session contracts.

These models intentionally do not depend on IBM Phone, SIP, Deepgram, or any
other transport provider. External adapters map provider events into these
canonical contracts so Veteran Access Bridge remains the source of truth for
correlation, human-control state, and scheduling context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class VoiceSessionState(StrEnum):
    CREATED = "CREATED"
    RINGING = "RINGING"
    CONNECTED = "CONNECTED"
    AVERY_ACTIVE = "AVERY_ACTIVE"
    ATTENTION_RECOMMENDED = "ATTENTION_RECOMMENDED"
    HANDOFF_REQUESTED = "HANDOFF_REQUESTED"
    MSA_JOINING = "MSA_JOINING"
    MSA_ACTIVE = "MSA_ACTIVE"
    ENDED = "ENDED"
    FAILED = "FAILED"


class VoiceParticipantRole(StrEnum):
    VETERAN = "VETERAN"
    AVERY = "AVERY"
    MSA = "MSA"
    RN = "RN"
    SPECIALTY_SCHEDULER = "SPECIALTY_SCHEDULER"
    COMMUNITY_CARE = "COMMUNITY_CARE"
    OTHER_HUMAN = "OTHER_HUMAN"


class VoiceParticipantState(StrEnum):
    INVITED = "INVITED"
    CONNECTED = "CONNECTED"
    MUTED = "MUTED"
    ON_HOLD = "ON_HOLD"
    DISCONNECTED = "DISCONNECTED"


class HandoffPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class VoiceEventType(StrEnum):
    SESSION_CREATED = "SESSION_CREATED"
    RINGING = "RINGING"
    CONNECTED = "CONNECTED"
    PARTICIPANT_JOINED = "PARTICIPANT_JOINED"
    PARTICIPANT_LEFT = "PARTICIPANT_LEFT"
    AVERY_ACTIVE = "AVERY_ACTIVE"
    HUMAN_ATTENTION_RECOMMENDED = "HUMAN_ATTENTION_RECOMMENDED"
    HANDOFF_REQUESTED = "HANDOFF_REQUESTED"
    HANDOFF_ACCEPTED = "HANDOFF_ACCEPTED"
    HANDOFF_COMPLETED = "HANDOFF_COMPLETED"
    HOLD_STARTED = "HOLD_STARTED"
    HOLD_ENDED = "HOLD_ENDED"
    SESSION_ENDED = "SESSION_ENDED"
    SESSION_FAILED = "SESSION_FAILED"


class VoiceParticipant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    participant_id: str
    role: VoiceParticipantRole
    state: VoiceParticipantState = VoiceParticipantState.CONNECTED
    display_name: str | None = None


class VoiceHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: bool = False
    priority: HandoffPriority | None = None
    reason_code: str | None = None
    destination: str | None = None
    scheduling_paused: bool = False
    context_preserved: bool = True


class VoiceSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_session_id: str = Field(default_factory=lambda: f"vs-{uuid4()}")
    interaction_id: str
    correlation_id: str
    case_id: str
    scheduling_encounter_id: str
    state: VoiceSessionState = VoiceSessionState.CREATED
    transport: str = "PENDING"
    provider_session_id: str | None = None
    provider_call_id: str | None = None
    participants: list[VoiceParticipant] = Field(default_factory=list)
    handoff: VoiceHandoff = Field(default_factory=VoiceHandoff)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    synthetic: bool = True


class VoiceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"ve-{uuid4()}")
    voice_session_id: str
    event_type: VoiceEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider_event_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    synthetic: bool = True


class CreateVoiceSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str
    correlation_id: str
    case_id: str
    scheduling_encounter_id: str
    transport: str = "PENDING"


class ApplyVoiceEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: VoiceEventType
    provider_event_id: str | None = None
    provider_session_id: str | None = None
    provider_call_id: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
