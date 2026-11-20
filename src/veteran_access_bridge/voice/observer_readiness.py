"""Read-only LiveKit preflight for a scoped synthetic observer.

An observer must never be the first participant to create a room: token-based
Avery dispatch runs only on room creation by the Veteran. This module checks
the authoritative LiveKit room and existing dispatch *without* creating either.
The caller/session identity validation reuses Avery's own participant selector.
"""

from __future__ import annotations

from typing import Any

from veteran_access_bridge.voice.dispatch_name import voice_agent_name
from veteran_access_bridge.voice.participant_selection import (
    verified_veteran_context,
)


class ObserverRoomNotReady(Exception):
    """No observer token can be issued for this room yet."""


async def require_observer_room_ready(
    *,
    api: Any,
    room_name: str,
    voice_session_id: str,
    interaction_id: str,
    case_id: str,
    scheduling_encounter_id: str,
) -> None:
    """Fail closed unless Veteran is connected and Avery is already dispatched.

    This is a read-only point-in-time check, not a room reservation. A later
    LiveKit join/reconnect still needs session-scoped access controls.
    """
    from livekit import api as livekit_api

    rooms = await api.room.list_rooms(
        livekit_api.ListRoomsRequest(names=[room_name])
    )
    if not any(room.name == room_name for room in rooms.rooms):
        raise ObserverRoomNotReady("Observer requires an existing voice room.")

    participants = await api.room.list_participants(
        livekit_api.ListParticipantsRequest(room=room_name)
    )
    matched = False
    for participant in participants.participants:
        context = verified_veteran_context(participant, room_name)
        if context is None:
            continue
        if (
            context.voice_session_id == voice_session_id
            and context.interaction_id == interaction_id
            and context.case_id == case_id
            and context.scheduling_encounter_id == scheduling_encounter_id
        ):
            matched = True
            break

    if not matched:
        raise ObserverRoomNotReady(
            "Observer requires a connected, session-matched Veteran caller."
        )

    dispatches = await api.agent_dispatch.list_dispatch(room_name)
    if not any(d.agent_name == voice_agent_name() for d in dispatches):
        raise ObserverRoomNotReady("Observer requires existing Avery dispatch.")
