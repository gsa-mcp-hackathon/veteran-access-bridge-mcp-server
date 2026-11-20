"""LiveKit worker that bridges Veteran speech to the existing Avery runtime.

The worker owns realtime media only:
LiveKit audio -> Deepgram Flux STT -> VAB interaction endpoint -> Orchestrate
text -> Deepgram Flux Alexis TTS -> LiveKit audio.

Scheduling state, MCP tools, handoff rules, and canonical VoiceSession state stay
inside Veteran Access Bridge.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

import httpx
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, room_io
from livekit.plugins import deepgram

from veteran_access_bridge.domain.avery_script import AVERY_OPENING_GREETING
from veteran_access_bridge.voice.dispatch_name import voice_agent_name
from veteran_access_bridge.voice.participant_selection import (
    VabVoiceContext,
    wait_for_veteran_participant,
)

LOGGER = logging.getLogger("veteran_access_bridge.voice.livekit_worker")
# Scheduling vocabulary only: never prime identity recognition with expected answers.
SCHEDULING_KEYTERMS = ["primary care", "Veterans Affairs", "VA Video Connect", "PACT"]


async def read_caller_reply(reader, sender_identity, participant, current):
    """Bounded accessibility text from the original caller, never an observer."""
    try:
        if (
            sender_identity != participant.identity
            or current is None
            or current.sid != participant.sid
        ):
            return None
        text = ""
        async with asyncio.timeout(5):
            async for chunk in reader:
                text += chunk
                if len(text) > 512:
                    return None
        return text.strip() or None
    except Exception:
        return None
    finally:
        reader.close()


async def private_identity_rpc(data, participant, current, bridge, lock, say):
    """Addressed RPC only. Never use caption streams or model messages."""
    if (
        data.caller_identity != participant.identity
        or current is None
        or current.sid != participant.sid
        or not bridge.trusted
        or not isinstance(data.payload, str)
        or len(data.payload) > 96
    ):
        raise PermissionError("Private identity request unavailable")
    try:
        payload = json.loads(data.payload)
    except (ValueError, TypeError):
        raise PermissionError("Invalid private identity request") from None
    if payload == {"action": "status"}:
        return json.dumps({"required": bridge.requires_last_four})
    if (
        not isinstance(payload, dict)
        or set(payload) != {"action", "digits"}
        or payload.get("action") != "submit"
        or not isinstance(payload.get("digits"), str)
        or not re.fullmatch(r"[0-9]{4}", payload["digits"])
    ):
        raise PermissionError("Invalid private identity request")
    async with lock:
        if not bridge.requires_last_four:
            raise PermissionError("Private identity input is not expected")
        digits = payload.pop("digits")
        try:
            reply = await bridge._trusted_turn("last_four", digits)
        finally:
            digits = ""
        await say(reply)
        return json.dumps({"required": bridge.requires_last_four})


class VabConversationBridge:
    def __init__(
        self,
        context: VabVoiceContext,
        *,
        participant_identity: str = "",
        participant_sid: str = "",
    ) -> None:
        self.context = context
        self.participant_identity = participant_identity
        self.participant_sid = participant_sid
        self.sequence = 0
        self.timing_trace_id = "unscoped"
        self.allow_interruptions = True
        self.requires_last_four = False
        self.identity_pending = True
        self.silence_prompt = None
        self.trusted = os.getenv("VAB_ENABLE_TRUSTED_VOICE_BOOKING") == "true"
        if self.trusted and (
            not participant_identity
            or not participant_sid
            or len(os.getenv("VAB_VOICE_WORKER_SECRET", "").encode()) < 32
        ):
            raise PermissionError(
                "Trusted worker configuration and participant required"
            )
        self.base_url = os.getenv(
            "VAB_VOICE_BACKEND_URL", "http://127.0.0.1:8080"
        ).rstrip("/")
        self.timeout_seconds = float(
            os.getenv("VAB_VOICE_BACKEND_TIMEOUT_SECONDS", "35")
        )
        self._client = None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _trusted_turn(self, action: str, text: str = "") -> str:
        self.timing_trace_id = "unscoped"
        from veteran_access_bridge.voice.worker_assertion import sign_turn

        body = {
            "voice_session_id": self.context.voice_session_id,
            "room_name": "vab-" + self.context.voice_session_id,
            "participant_identity": self.participant_identity,
            "participant_sid": self.participant_sid,
            "sequence": self.sequence,
            "action": action,
            "text": text,
        }
        assertion = sign_turn(body, os.environ["VAB_VOICE_WORKER_SECRET"])
        self.sequence += 1
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        response = await self._client.post(
            self.base_url + "/internal/synthetic-primary-care/voice-turn",
            headers={"Authorization": "Bearer " + assertion},
            json=body,
        )
        if response.status_code != 200:
            raise RuntimeError("Trusted voice action was not verified")
        payload = response.json()
        if (
            payload.get("voice_session_id") != self.context.voice_session_id
            or payload.get("synthetic") is not True
            or not isinstance(payload.get("text"), str)
            or not payload["text"]
        ):
            raise RuntimeError("Invalid trusted voice response")
        delivery = payload.get("allow_interruptions", True)
        if not isinstance(delivery, bool):
            raise RuntimeError("Invalid trusted speech delivery policy")
        required = payload.get("requires_last_four", False)
        if not isinstance(required, bool):
            raise RuntimeError("Invalid private identity state")
        self.requires_last_four = required
        pending = payload.get("identity_pending", True)
        if not isinstance(pending, bool):
            raise RuntimeError("Invalid identity state")
        self.identity_pending = pending
        self.silence_prompt = payload.get("silence_prompt") if pending else None
        self.allow_interruptions = delivery
        trace = payload.get("timing_trace_id")
        if isinstance(trace, str) and re.fullmatch(r"[a-f0-9]{32}", trace):
            self.timing_trace_id = trace
        return payload["text"]

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Demo-Role": "SCHEDULER",
            "X-Demo-Actor": "avery-livekit-worker",
            "X-Demo-Case": self.context.case_id,
        }

    async def send_utterance(self, text: str) -> str:
        if self.trusted:
            return await self._trusted_turn("turn", text.strip())
        clean = text.strip()
        if not clean:
            raise ValueError("Veteran utterance must not be empty.")

        url = f"{self.base_url}/api/interactions/{self.context.interaction_id}/messages"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                url,
                headers=self._headers(),
                json={"message": clean},
            )

        if response.status_code >= 400:
            detail = response.text.strip()
            raise RuntimeError(
                f"VAB interaction bridge returned HTTP {response.status_code}: "
                f"{detail[:1200]}"
            )

        payload = response.json()
        answer = str((payload.get("payload") or {}).get("text") or "").strip()
        if not answer:
            raise RuntimeError("VAB interaction bridge returned no Avery text.")
        return answer

    async def latest_agent_opening(self) -> str:
        if self.trusted:
            return await self._trusted_turn("opening")
        url = (
            f"{self.base_url}/api/interactions/"
            f"{self.context.interaction_id}/events?once=1"
        )
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, headers=self._headers())

        if response.status_code >= 400:
            detail = response.text.strip()
            raise RuntimeError(
                f"VAB opening lookup returned HTTP {response.status_code}: "
                f"{detail[:1200]}"
            )

        opening = ""
        for frame in response.text.split("\n\n"):
            event_name = ""
            data_text = ""
            for line in frame.splitlines():
                if line.startswith("event: "):
                    event_name = line.removeprefix("event: ").strip()
                elif line.startswith("data: "):
                    data_text = line.removeprefix("data: ").strip()
            if event_name != "agent_answered" or not data_text:
                continue
            try:
                payload = json.loads(data_text)
            except json.JSONDecodeError:
                continue
            text = str((payload.get("payload") or {}).get("text") or "").strip()
            if text:
                opening = text

        if not opening:
            raise RuntimeError(
                "Canonical Avery opening was not found in interaction history."
            )
        return opening


server = AgentServer()


@server.rtc_session(agent_name=voice_agent_name())
async def avery_voice_session(ctx: JobContext) -> None:
    await ctx.connect()
    participant, context = await wait_for_veteran_participant(ctx.room)
    LOGGER.info(
        "Veteran participant joined identity=%s sid=%s",
        participant.identity,
        participant.sid,
    )
    bridge = VabConversationBridge(
        context,
        participant_identity=participant.identity,
        participant_sid=participant.sid,
    )

    async def close_bridge(*_args):
        await bridge.aclose()

    ctx.add_shutdown_callback(close_bridge)

    stt_model = os.getenv("DEEPGRAM_STT_MODEL", "flux-general-en")
    tts_model = os.getenv("DEEPGRAM_TTS_MODEL", "flux-alexis-en")
    eot_threshold = float(os.getenv("DEEPGRAM_EOT_THRESHOLD", "0.7"))
    eot_timeout_ms = int(os.getenv("DEEPGRAM_EOT_TIMEOUT_MS", "3000"))
    audio_chunk_ms = int(os.getenv("DEEPGRAM_AUDIO_CHUNK_MS", "80"))

    session = AgentSession(
        stt=deepgram.STTv2(
            model=stt_model,
            eot_threshold=eot_threshold,
            eot_timeout_ms=eot_timeout_ms,
            audio_chunk_duration_ms=audio_chunk_ms,
            keyterm=SCHEDULING_KEYTERMS,
        ),
        llm=None,
        tts=deepgram.TTSv2(model=tts_model),
        turn_detection="stt",
    )
    spoken_identity = os.getenv("VAB_SPOKEN_LAST_FOUR") == "true"
    if spoken_identity and not bridge.trusted:
        raise PermissionError("Spoken verification requires the trusted host")
    turn_lock = asyncio.Lock()
    previous_final: tuple[str, float] | None = None
    pending_replies: set[asyncio.Task] = set()

    # The caller can see their own finalized speech without publishing raw
    # verification details to room captions, observers, history, or logs.
    caller_caption_sequence = 0
    caller_caption_tasks: set[asyncio.Task] = set()

    async def caller_caption(message):
        peer = ctx.room.remote_participants.get(participant.identity)
        if peer is None or peer.sid != participant.sid:
            return None
        try:
            return await ctx.room.local_participant.perform_rpc(
                destination_identity=participant.identity,
                method="vab.caller-caption",
                payload=json.dumps(
                    {"session": context.voice_session_id, **message}, ensure_ascii=False
                ),
                response_timeout=3,
            )
        except Exception:
            return None

    private_captions = (
        bridge.trusted and await caller_caption({"kind": "start"}) == "ready"
    )

    prompted_for_silence = False

    @session.on("user_state_changed")
    def on_user_state_changed(event):
        nonlocal prompted_for_silence
        if (
            event.new_state == "away"
            and not prompted_for_silence
            and not pending_replies
            and bridge.silence_prompt
        ):
            prompted_for_silence = True
            session.say(bridge.silence_prompt, allow_interruptions=True)

    def dispatch_reply(transcript: str, source: str) -> None:
        nonlocal prompted_for_silence
        if transcript.strip():
            prompted_for_silence = False
        if len(pending_replies) >= 3:
            LOGGER.warning("Caller reply queue full; input not submitted")
            return
        nonlocal previous_final
        transcript_final_at = time.perf_counter()
        if (
            previous_final
            and previous_final[0] == transcript
            and (transcript_final_at - previous_final[1] < 1.5)
        ):
            LOGGER.info("Dropping repeated final STT segment")
            return
        previous_final = (transcript, transcript_final_at)
        nonlocal caller_caption_sequence
        if source == "speech" and private_captions and 0 < len(transcript) <= 1800:
            caller_caption_sequence += 1
            task = asyncio.create_task(
                caller_caption(
                    {
                        "kind": "final",
                        "seq": caller_caption_sequence,
                        "text": transcript,
                    }
                )
            )
            caller_caption_tasks.add(task)
            task.add_done_callback(caller_caption_tasks.discard)

        async def respond() -> None:
            async with turn_lock:
                if not transcript:
                    LOGGER.warning("Ignoring empty final transcript.")
                    return
                bridge_started_at = time.perf_counter()
                try:
                    reply = await bridge.send_utterance(transcript)
                    reply_ready_at = time.perf_counter()
                    LOGGER.info(
                        "Avery reply ready bridge_ms=%.1f "
                        "final_to_reply_ms=%.1f queue_ms=%.1f input_source=%s "
                        "reply_chars=%d trace_id=%s",
                        (reply_ready_at - bridge_started_at) * 1000,
                        (reply_ready_at - transcript_final_at) * 1000,
                        (bridge_started_at - transcript_final_at) * 1000,
                        source,
                        len(reply),
                        bridge.timing_trace_id,
                    )
                except Exception:
                    LOGGER.exception("Avery bridge failed after finalized STT event")
                    await session.say(
                        "I am having trouble reaching the scheduling service. "
                        "Please contact your facility's scheduling team.",
                        allow_interruptions=False,
                    )
                    return
                if os.getenv("VAB_ENABLE_LATENCY_PROBE") == "true":
                    try:
                        await asyncio.wait_for(
                            ctx.room.local_participant.send_text(
                                json.dumps({"trace_id": bridge.timing_trace_id}),
                                topic="vab.latency.ready",
                            ),
                            timeout=0.25,
                        )
                    except Exception:
                        LOGGER.info("Browser latency marker unavailable")
                speech_started_at = time.perf_counter()
                await session.say(reply, allow_interruptions=bridge.allow_interruptions)
                LOGGER.info(
                    "Avery speech completed say_ms=%.1f "
                    "final_to_speech_complete_ms=%.1f trace_id=%s",
                    (time.perf_counter() - speech_started_at) * 1000,
                    (time.perf_counter() - transcript_final_at) * 1000,
                    bridge.timing_trace_id,
                )

        task = asyncio.create_task(respond())
        pending_replies.add(task)
        task.add_done_callback(pending_replies.discard)

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event) -> None:
        if spoken_identity:
            return  # PrivateSpeechAgent dispatched before redacting SDK events.
        if event.is_final:
            dispatch_reply(str(event.transcript or "").strip(), "speech")

    @session.on("metrics_collected")
    def on_metrics(event) -> None:
        metric = event.metrics
        # Allowlist numeric measurements only; never log speech or provider bodies.
        for field in (
            "end_of_utterance_delay",
            "transcription_delay",
            "ttfb",
            "duration",
        ):
            value = getattr(metric, field, None)
            if isinstance(value, (int, float)) and value >= 0:
                LOGGER.info(
                    "Voice stage metric type=%s field=%s seconds=%.3f",
                    type(metric).__name__,
                    field,
                    value,
                )

    async def receive_typed_reply(reader, sender_identity):
        text = await read_caller_reply(
            reader,
            sender_identity,
            participant,
            ctx.room.remote_participants.get(sender_identity),
        )
        if text:
            dispatch_reply(text, "typed")

    def typed_handler(reader, sender_identity):
        asyncio.create_task(receive_typed_reply(reader, sender_identity))

    ctx.room.register_text_stream_handler("vab.caller-reply", typed_handler)

    @ctx.room.local_participant.register_rpc_method("vab.private-identity")
    async def receive_private_identity(data):
        async def say(reply):
            await session.say(reply, allow_interruptions=False)

        try:
            return await private_identity_rpc(
                data,
                participant,
                ctx.room.remote_participants.get(data.caller_identity),
                bridge,
                turn_lock,
                say,
            )
        except Exception:
            # Never propagate provider errors, payloads or request bodies to peers.
            from livekit.rtc import RpcError

            raise RpcError(1500, "Private verification was not completed") from None

    agent_type = Agent
    agent_kwargs = {}
    if spoken_identity:
        from veteran_access_bridge.voice.private_speech_agent import PrivateSpeechAgent

        agent_type = PrivateSpeechAgent
        agent_kwargs = {
            "dispatch": dispatch_reply,
            "identity_pending": lambda: bridge.identity_pending,
        }
    await session.start(
        room=ctx.room,
        room_options=room_io.RoomOptions(participant_identity=participant.identity),
        agent=agent_type(
            **agent_kwargs,
            instructions=(
                "Avery is the Veteran Access Bridge scheduling voice. "
                "Conversation text comes from the existing VAB Orchestrate runtime."
            ),
        ),
    )
    linked = getattr(getattr(session, "room_io", None), "linked_participant", None)
    if linked is not None and linked.identity != participant.identity:
        raise RuntimeError("Avery is linked to a non-Veteran room participant.")
    LOGGER.info(
        "AgentSession started room=%s linked_participant=%s",
        ctx.room.name,
        getattr(linked, "identity", None),
    )
    publications = getattr(participant, "track_publications", {})
    for publication in publications.values():
        LOGGER.info(
            "Veteran track publication sid=%s source=%s kind=%s subscribed=%s muted=%s",
            getattr(publication, "sid", None),
            getattr(publication, "source", None),
            getattr(publication, "kind", None),
            getattr(publication, "subscribed", None),
            getattr(publication, "muted", None),
        )

    # Give the browser participant a brief moment to finish subscribing to
    # Avery's remote audio track before the first synthesized utterance.
    await asyncio.sleep(0.25)

    try:
        opening = await bridge.latest_agent_opening()
    except Exception:
        if bridge.trusted:
            raise
        LOGGER.exception(
            "Unable to load canonical opening from interaction history. "
            "Using configured fallback."
        )
        opening = AVERY_OPENING_GREETING
    LOGGER.info("Speaking canonical Avery opening chars=%d", len(opening))
    opening_started_at = time.perf_counter()
    try:
        await session.say(opening, allow_interruptions=False)
    except Exception:
        LOGGER.exception("Canonical Avery opening TTS/playout failed.")
        raise
    LOGGER.info(
        "Canonical Avery opening completed duration_ms=%.1f",
        (time.perf_counter() - opening_started_at) * 1000,
    )


def main() -> None:
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
