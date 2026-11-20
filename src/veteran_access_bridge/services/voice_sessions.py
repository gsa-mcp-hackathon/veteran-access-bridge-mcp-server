"""In-memory canonical voice-session registry for the synthetic prototype."""

from __future__ import annotations

from datetime import datetime, timezone

from veteran_access_bridge.domain.voice_session import (
    ApplyVoiceEventRequest,
    CreateVoiceSessionRequest,
    HandoffPriority,
    VoiceEvent,
    VoiceEventType,
    VoiceHandoff,
    VoiceParticipant,
    VoiceParticipantRole,
    VoiceParticipantState,
    VoiceSession,
    VoiceSessionState,
)


class VoiceSessionRegistry:
    """Own canonical call state independently of the external voice provider."""

    def __init__(self) -> None:
        self._sessions: dict[str, VoiceSession] = {}
        self._events: dict[str, list[VoiceEvent]] = {}
        self._provider_event_ids: dict[str, set[str]] = {}

    def create(self, request: CreateVoiceSessionRequest) -> VoiceSession:
        session = VoiceSession(**request.model_dump())
        session.participants = [
            VoiceParticipant(
                participant_id=f"{session.voice_session_id}:veteran",
                role=VoiceParticipantRole.VETERAN,
            ),
            VoiceParticipant(
                participant_id=f"{session.voice_session_id}:avery",
                role=VoiceParticipantRole.AVERY,
            ),
        ]
        self._sessions[session.voice_session_id] = session
        self._events[session.voice_session_id] = [
            VoiceEvent(
                voice_session_id=session.voice_session_id,
                event_type=VoiceEventType.SESSION_CREATED,
            )
        ]
        self._provider_event_ids[session.voice_session_id] = set()
        return session.model_copy(deep=True)

    def get(self, voice_session_id: str) -> VoiceSession:
        try:
            return self._sessions[voice_session_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"Unknown voice session {voice_session_id!r}.") from exc

    def events(self, voice_session_id: str) -> list[VoiceEvent]:
        if voice_session_id not in self._sessions:
            raise KeyError(f"Unknown voice session {voice_session_id!r}.")
        return [event.model_copy(deep=True) for event in self._events[voice_session_id]]

    def find_by_provider_call_id(self, provider_call_id: str) -> VoiceSession | None:
        for session in self._sessions.values():
            if session.provider_call_id == provider_call_id:
                return session.model_copy(deep=True)
        return None

    def find_by_provider_session_id(
        self,
        provider_session_id: str,
    ) -> VoiceSession | None:
        for session in self._sessions.values():
            if session.provider_session_id == provider_session_id:
                return session.model_copy(deep=True)
        return None

    def apply_event(
        self,
        voice_session_id: str,
        request: ApplyVoiceEventRequest,
    ) -> tuple[VoiceSession, VoiceEvent]:
        if voice_session_id not in self._sessions:
            raise KeyError(f"Unknown voice session {voice_session_id!r}.")

        current = self._sessions[voice_session_id]

        if (
            request.provider_event_id is not None
            and request.provider_event_id in self._provider_event_ids[voice_session_id]
        ):
            existing = next(
                event
                for event in self._events[voice_session_id]
                if event.provider_event_id == request.provider_event_id
            )
            return current.model_copy(deep=True), existing.model_copy(deep=True)

        if current.state in {VoiceSessionState.ENDED, VoiceSessionState.FAILED}:
            raise ValueError(
                f"Voice session {voice_session_id!r} is terminal ({current.state.value})."
            )

        event = VoiceEvent(
            voice_session_id=voice_session_id,
            event_type=request.event_type,
            provider_event_id=request.provider_event_id,
            payload=request.payload,
        )

        if request.provider_session_id is not None:
            current.provider_session_id = request.provider_session_id
        if request.provider_call_id is not None:
            current.provider_call_id = request.provider_call_id

        event_type = request.event_type
        if event_type == VoiceEventType.RINGING:
            current.state = VoiceSessionState.RINGING
        elif event_type == VoiceEventType.CONNECTED:
            current.state = VoiceSessionState.CONNECTED
        elif event_type == VoiceEventType.AVERY_ACTIVE:
            current.state = VoiceSessionState.AVERY_ACTIVE
        elif event_type == VoiceEventType.HUMAN_ATTENTION_RECOMMENDED:
            current.state = VoiceSessionState.ATTENTION_RECOMMENDED
            current.handoff = self._handoff_from_payload(request.payload, required=False)
        elif event_type == VoiceEventType.HANDOFF_REQUESTED:
            current.state = VoiceSessionState.HANDOFF_REQUESTED
            current.handoff = self._handoff_from_payload(request.payload, required=True)
        elif event_type == VoiceEventType.HANDOFF_ACCEPTED:
            current.state = VoiceSessionState.MSA_JOINING
        elif event_type == VoiceEventType.HANDOFF_COMPLETED:
            current.state = VoiceSessionState.MSA_ACTIVE
        elif event_type == VoiceEventType.SESSION_ENDED:
            current.state = VoiceSessionState.ENDED
            current.ended_at = datetime.now(timezone.utc)
        elif event_type == VoiceEventType.SESSION_FAILED:
            current.state = VoiceSessionState.FAILED
            current.ended_at = datetime.now(timezone.utc)

        if event_type in {
            VoiceEventType.PARTICIPANT_JOINED,
            VoiceEventType.PARTICIPANT_LEFT,
        }:
            self._apply_participant_event(current, request)

        current.updated_at = datetime.now(timezone.utc)
        self._events[voice_session_id].append(event)
        if request.provider_event_id is not None:
            self._provider_event_ids[voice_session_id].add(request.provider_event_id)
        return current.model_copy(deep=True), event.model_copy(deep=True)

    @staticmethod
    def _handoff_from_payload(
        payload: dict[str, object],
        *,
        required: bool,
    ) -> VoiceHandoff:
        priority_raw = payload.get("priority")
        priority = HandoffPriority(str(priority_raw)) if priority_raw else None
        return VoiceHandoff(
            required=required,
            priority=priority,
            reason_code=(
                str(payload["reason_code"]) if payload.get("reason_code") else None
            ),
            destination=(
                str(payload["destination"]) if payload.get("destination") else None
            ),
            scheduling_paused=bool(payload.get("scheduling_paused", required)),
            context_preserved=bool(payload.get("context_preserved", True)),
        )

    @staticmethod
    def _apply_participant_event(
        session: VoiceSession,
        request: ApplyVoiceEventRequest,
    ) -> None:
        participant_id = str(request.payload.get("participant_id", "")).strip()
        role_raw = request.payload.get("role")
        if not participant_id or role_raw is None:
            raise ValueError(
                "Participant events require payload.participant_id and payload.role."
            )
        role = VoiceParticipantRole(str(role_raw))
        target_state = (
            VoiceParticipantState.CONNECTED
            if request.event_type == VoiceEventType.PARTICIPANT_JOINED
            else VoiceParticipantState.DISCONNECTED
        )
        for participant in session.participants:
            if participant.participant_id == participant_id:
                participant.state = target_state
                participant.role = role
                return
        session.participants.append(
            VoiceParticipant(
                participant_id=participant_id,
                role=role,
                state=target_state,
                display_name=(
                    str(request.payload["display_name"])
                    if request.payload.get("display_name")
                    else None
                ),
            )
        )
