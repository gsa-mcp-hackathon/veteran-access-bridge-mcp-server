"""Select the canonical Veteran caller without binding Avery to an observer.

The helper deliberately has no optional LiveKit dependency so that its
participant-order and room-scoping behavior can be regression-tested in the
base CI environment. LiveKit provides the room and participant event objects.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VabVoiceContext:
    voice_session_id: str
    interaction_id: str
    case_id: str
    scheduling_encounter_id: str

    @classmethod
    def from_participant_metadata(cls, raw: str | None) -> "VabVoiceContext":
        try:
            payload = json.loads(raw or "{}")
        except (TypeError, ValueError) as exc:
            raise ValueError("LiveKit participant metadata is not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise ValueError("LiveKit participant metadata must be an object.")

        required = (
            "voice_session_id",
            "interaction_id",
            "case_id",
            "scheduling_encounter_id",
        )
        missing = [
            key
            for key in required
            if not isinstance(payload.get(key), str) or not payload[key].strip()
        ]
        if missing:
            raise ValueError(
                "LiveKit participant metadata is missing: " + ", ".join(missing)
            )

        return cls(
            voice_session_id=payload["voice_session_id"],
            interaction_id=payload["interaction_id"],
            case_id=payload["case_id"],
            scheduling_encounter_id=payload["scheduling_encounter_id"],
        )


def verified_veteran_context(
    participant: Any, room_name: str
) -> VabVoiceContext | None:
    """Accept only the server-issued caller role/identity for this voice room.

    Observers can join before the Veteran; their partial metadata must never
    raise a worker-startup error or be interpreted as the Veteran's identity.
    """
    identity = getattr(participant, "identity", None)
    metadata = getattr(participant, "metadata", None)
    if (
        not isinstance(identity, str)
        or not identity.startswith("veteran-")
        or not isinstance(metadata, str)
    ):
        return None

    try:
        payload = json.loads(metadata)
        if not isinstance(payload, dict) or payload.get("vab_role") != "veteran_caller":
            return None
        context = VabVoiceContext.from_participant_metadata(metadata)
    except (TypeError, ValueError):
        return None

    if room_name != f"vab-{context.voice_session_id}":
        return None
    return context


async def wait_for_veteran_participant(room: Any) -> tuple[Any, VabVoiceContext]:
    """Wait for a verified Veteran regardless of observer arrival order.

    Register listeners *before* inspecting existing participants so that
    a joining Veteran cannot be missed between snapshot and subscription.
    Listener cleanup is guaranteed on success, failure, and cancellation.
    """
    loop = asyncio.get_running_loop()
    matched: asyncio.Future[tuple[Any, VabVoiceContext]] = loop.create_future()

    def consider(participant: Any) -> None:
        if matched.done():
            return
        context = verified_veteran_context(participant, room.name)
        if context is not None:
            matched.set_result((participant, context))

    room.on("participant_connected", consider)
    room.on("participant_active", consider)
    try:
        for participant in tuple(room.remote_participants.values()):
            consider(participant)
        return await matched
    finally:
        room.off("participant_connected", consider)
        room.off("participant_active", consider)
