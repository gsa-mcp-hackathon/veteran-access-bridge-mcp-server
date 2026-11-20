import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("livekit.agents")
from veteran_access_bridge.voice import livekit_worker as worker
from veteran_access_bridge.voice.participant_selection import VabVoiceContext
from veteran_access_bridge.voice.worker_assertion import verify_turn


@pytest.mark.parametrize(
    "sender,sid,text,accepted",
    [
        ("caller", "PA-current", "Central time", True),
        ("observer", "PA-current", "yes", False),
        ("caller", "PA-replaced", "yes", False),
        ("caller", "PA-current", "x" * 513, False),
        ("caller", "PA-current", " ", False),
    ],
)
def test_typed_accessibility_reply_is_bounded_and_participant_bound(
    sender, sid, text, accepted
):
    class Reader:
        closed = False

        async def chunks(self):
            yield text

        def __aiter__(self):
            return self.chunks()

        def close(self):
            self.closed = True

    reader = Reader()
    participant = SimpleNamespace(identity="caller", sid="PA-current")
    result = asyncio.run(
        worker.read_caller_reply(reader, sender, participant, SimpleNamespace(sid=sid))
    )
    assert (result is not None) is accepted
    assert reader.closed


@pytest.mark.parametrize("delivery", [True, False])
@pytest.mark.parametrize("trace", ["a" * 32, "invalid-patient-text", None])
def test_worker_sends_authenticated_final_turn_without_demo_authority(
    monkeypatch, delivery, trace
):
    secret = "test-worker-secret-" + "w" * 40
    monkeypatch.setenv("VAB_ENABLE_TRUSTED_VOICE_BOOKING", "true")
    monkeypatch.setenv("VAB_VOICE_WORKER_SECRET", secret)
    sent = []
    clients = []

    class Client:
        def __init__(self, **kwargs):
            clients.append(self)
            self.closed = False

        async def aclose(self):
            self.closed = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, headers, json):
            verify_turn(headers["Authorization"].removeprefix("Bearer "), json, secret)
            assert not any(k.startswith("X-Demo") for k in headers)
            assert url.endswith("/internal/synthetic-primary-care/voice-turn")
            sent.append(json)
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "synthetic": True,
                    "voice_session_id": "vs-test",
                    "text": "verified reply",
                    "allow_interruptions": delivery,
                    "timing_trace_id": trace,
                },
            )

    monkeypatch.setattr(worker.httpx, "AsyncClient", Client)
    bridge = worker.VabConversationBridge(
        VabVoiceContext("vs-test", "interaction", "case", "encounter"),
        participant_identity="veteran-test",
        participant_sid="PA-test",
    )
    asyncio.run(bridge.latest_agent_opening())
    asyncio.run(bridge.send_utterance("Yes, book that appointment."))
    assert bridge.allow_interruptions is delivery
    assert bridge.timing_trace_id == (trace if trace == "a" * 32 else "unscoped")
    assert [b["sequence"] for b in sent] == [0, 1]
    assert [b["action"] for b in sent] == ["opening", "turn"]
    assert all(b["participant_sid"] == "PA-test" for b in sent)
    assert len(clients) == 1
    asyncio.run(bridge.aclose())
    assert clients[0].closed


@pytest.mark.parametrize(
    "sender,sid,accepted",
    [
        ("caller", "PA-current", True),
        ("observer", "PA-current", False),
        ("caller", "PA-old", False),
    ],
)
def test_private_rpc_is_addressed_and_never_returns_digits(sender, sid, accepted):
    class Bridge:
        trusted = True
        requires_last_four = True

        async def _trusted_turn(self, action, text):
            assert action == "last_four" and text == "0067"
            self.requires_last_four = False
            return "Your identity is verified."

    spoken = []

    async def say(text):
        spoken.append(text)

    async def run():
        return await worker.private_identity_rpc(
            SimpleNamespace(
                caller_identity=sender, payload='{"action":"submit","digits":"0067"}'
            ),
            SimpleNamespace(identity="caller", sid="PA-current"),
            SimpleNamespace(sid=sid),
            Bridge(),
            asyncio.Lock(),
            say,
        )

    if not accepted:
        with pytest.raises(PermissionError):
            asyncio.run(run())
        assert not spoken
    else:
        result = asyncio.run(run())
        assert "0067" not in result + str(spoken)
        assert result == '{"required": false}'
