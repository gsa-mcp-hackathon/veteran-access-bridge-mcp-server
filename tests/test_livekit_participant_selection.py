"""Observer-arrival and restart regression tests for Avery caller selection.

These use a small room event fake so no LiveKit network, optional voice SDK,
Deepgram subscription, or production credentials are necessary in base CI.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from veteran_access_bridge.voice.participant_selection import (
    VabVoiceContext,
    verified_veteran_context,
    wait_for_veteran_participant,
)


@dataclass(frozen=True)
class Participant:
    identity: str
    metadata: str


def veteran(
    identity: str = "veteran-trusted-id",
    *,
    voice_session_id: str = "voice-123",
    role: str = "veteran_caller",
) -> Participant:
    return Participant(
        identity=identity,
        metadata=json.dumps(
            {
                "vab_role": role,
                "voice_session_id": voice_session_id,
                "interaction_id": "interaction-123",
                "case_id": "DEMO-PC-001",
                "scheduling_encounter_id": "SE-PC-001",
            }
        ),
    )


def observer(identity: str = "msa-observer-1") -> Participant:
    return Participant(
        identity=identity,
        metadata=json.dumps(
            {
                "role": "msa_observer",
                "voice_session_id": "voice-123",
                "interaction_id": "interaction-123",
                "case_id": "DEMO-PC-001",
            }
        ),
    )


class Room:
    def __init__(self, *participants: Participant, name: str = "vab-voice-123") -> None:
        self.name = name
        self.remote_participants = {p.identity: p for p in participants}
        self.listeners: dict[str, list] = {}

    def on(self, event: str, handler) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def off(self, event: str, handler) -> None:
        self.listeners[event].remove(handler)

    def add(self, participant: Participant, event: str = "participant_connected") -> None:
        self.remote_participants[participant.identity] = participant
        for callback in tuple(self.listeners.get(event, ())):
            callback(participant)

    def listeners_cleared(self) -> bool:
        return all(not callbacks for callbacks in self.listeners.values())


def test_observer_metadata_is_not_veteran_context() -> None:
    assert verified_veteran_context(observer(), "vab-voice-123") is None
    assert verified_veteran_context(
        veteran(identity="msa-observer-forged-role"), "vab-voice-123"
    ) is None
    assert verified_veteran_context(
        veteran(role="msa_observer"), "vab-voice-123"
    ) is None
    assert verified_veteran_context(
        veteran(voice_session_id="voice-other"), "vab-voice-123"
    ) is None
    assert verified_veteran_context(
        Participant("veteran-malformed", "{bad json"), "vab-voice-123"
    ) is None
    assert verified_veteran_context(
        Participant("veteran-missing", '{"vab_role":"veteran_caller"}'),
        "vab-voice-123",
    ) is None


def test_context_rejects_non_object_and_non_string_identifiers() -> None:
    with pytest.raises(ValueError, match="must be an object"):
        VabVoiceContext.from_participant_metadata("[]")
    with pytest.raises(ValueError, match="is missing"):
        VabVoiceContext.from_participant_metadata(
            '{"voice_session_id":123,"interaction_id":"i",'
            '"case_id":"c","scheduling_encounter_id":"e"}'
        )


@pytest.mark.asyncio
async def test_observer_first_then_veteran_joins() -> None:
    room = Room(observer())
    pending = asyncio.create_task(wait_for_veteran_participant(room))
    await asyncio.sleep(0)
    assert not pending.done()
    room.add(veteran(), event="participant_active")
    participant, context = await asyncio.wait_for(pending, timeout=1)
    assert participant.identity == "veteran-trusted-id"
    assert context.voice_session_id == "voice-123"
    assert room.listeners_cleared()


@pytest.mark.asyncio
async def test_veteran_first_is_selected_not_later_observer() -> None:
    room = Room(veteran())
    participant, context = await asyncio.wait_for(wait_for_veteran_participant(room), 1)
    room.add(observer())
    assert participant.identity == "veteran-trusted-id"
    assert context.scheduling_encounter_id == "SE-PC-001"
    assert room.listeners_cleared()


@pytest.mark.asyncio
async def test_worker_restart_with_observer_and_veteran_already_present() -> None:
    room = Room(observer(), veteran(), observer("msa-observer-2"))
    for _ in range(2):
        participant, context = await asyncio.wait_for(wait_for_veteran_participant(room), 1)
        assert participant.identity == "veteran-trusted-id"
        assert context.interaction_id == "interaction-123"
        assert room.listeners_cleared()


@pytest.mark.asyncio
async def test_malformed_or_cross_room_veteran_cannot_be_bound() -> None:
    room = Room(
        observer(),
        veteran(identity="veteran-cross-room", voice_session_id="voice-other"),
        Participant("veteran-malformed", '{"vab_role":"veteran_caller"}'),
    )
    task = asyncio.create_task(wait_for_veteran_participant(room))
    await asyncio.sleep(0)
    assert not task.done()
    room.add(veteran(identity="veteran-good"), event="participant_connected")
    participant, _ = await asyncio.wait_for(task, 1)
    assert participant.identity == "veteran-good"
    assert room.listeners_cleared()


@pytest.mark.asyncio
async def test_cancelled_wait_removes_listeners() -> None:
    room = Room(observer())
    task = asyncio.create_task(wait_for_veteran_participant(room))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert room.listeners_cleared()


def test_agent_session_explicitly_binds_to_validated_veteran_identity() -> None:
    """Guard against reintroducing the worker's default first-participant binding."""
    root = Path(__file__).resolve().parents[1]
    worker = (
        root / "src" / "veteran_access_bridge" / "voice" / "livekit_worker.py"
    ).read_text(encoding="utf-8")
    assert "participant, context = await wait_for_veteran_participant(ctx.room)" in worker
    assert "room_io.RoomOptions(participant_identity=participant.identity)" in worker
    assert "ctx.wait_for_participant()" not in worker
