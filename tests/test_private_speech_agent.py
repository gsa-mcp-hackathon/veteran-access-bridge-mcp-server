import asyncio

import pytest

pytest.importorskip("livekit.agents")
from livekit.agents import Agent, stt

from veteran_access_bridge.voice.private_speech_agent import PrivateSpeechAgent


def test_raw_final_goes_to_host_but_not_sdk_captions(monkeypatch):
    events = [
        stt.SpeechEvent(
            type=kind,
            alternatives=[stt.SpeechData(language="en", text=text)],
        )
        for kind, text in [
            (stt.SpeechEventType.INTERIM_TRANSCRIPT, "zero zero"),
            (stt.SpeechEventType.FINAL_TRANSCRIPT, "zero zero six seven"),
        ]
    ]

    async def source(*args):
        for event in events:
            yield event

    monkeypatch.setattr(Agent.default, "stt_node", source)
    dispatched = []
    agent = PrivateSpeechAgent(
        instructions="test",
        dispatch=lambda text, source: dispatched.append((text, source)),
        identity_pending=lambda: True,
    )

    async def run():
        return [e async for e in agent.stt_node(None, None)]

    safe = asyncio.run(run())
    assert dispatched == [("zero zero six seven", "speech")]
    assert len(safe) == 2
    assert all(
        e.alternatives[0].text == "[Verification details withheld]" for e in safe
    )
    assert events[1].alternatives[0].text == "zero zero six seven"
