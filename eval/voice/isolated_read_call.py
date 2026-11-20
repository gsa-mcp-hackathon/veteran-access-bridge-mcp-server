"""One bounded RTC smoke call to the separate evaluation stack; never books.

Generated speech is not evidence of human pronunciation or browser playback.
Secrets are supplied through the process environment. Call provisioning and
after-call CRM records can be created; appointment selection is never requested.
"""

import asyncio
import json
import os
import time
from array import array
from pathlib import Path

import httpx
from livekit import rtc

BASE = "https://vab-latency-eval-ui.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"


def answer_for(text):
    lower = text.lower()
    if "verification isn't available" in lower:
        return None
    if any(
        x in lower
        for x in (
            "shall i book",
            "confirm your appointment",
            "which appointment",
            "which option",
        )
    ):
        return None
    if any(
        x in lower
        for x in (
            "could not verify",
            "couldn't verify",
            "trouble reaching",
            "unable to verify",
        )
    ):
        return None
    if (
        "judy" in lower
        and any(x in lower for x in ("born", "birth"))
        and any(x in lower for x in ("is that", "correct", "right"))
    ):
        return "Yes."
    if "name" in lower and any(x in lower for x in ("provide", "say", "tell", "your")):
        return "My name is Judy Morrison."
    if "birth" in lower:
        return "May fifth, nineteen forty five."
    if any(x in lower for x in ("topeka", "colmery")) and any(
        x in lower for x in ("would you like to schedule at", "would you like to use")
    ):
        return "Yes."
    if any(x in lower for x in ("time zone", "timezone")):
        return "Central time, in Topeka Kansas."
    if any(
        x in lower
        for x in (
            "how may",
            "how can",
            "help you",
            "prefer",
            "what day",
            "morning",
            "date range",
            "what brings",
        )
    ):
        return (
            "I would like to schedule a primary care appointment next week "
            "in the morning at Topeka."
        )
    return None


async def main():
    output = Path(os.environ["VAB_EVAL_EVIDENCE"])
    if output.exists():
        raise RuntimeError("Preserve existing evidence")
    evidence = {
        "target": BASE,
        "generated_audio": True,
        "transcript": [],
        "no_booking_requested": True,
    }
    room = rtc.Room()
    replies = asyncio.Queue()
    tasks = set()
    pending_pause = None
    last_agent_audio_at = None
    evidence["pause_measurement"] = {
        "endpoint": "generated caller RTC received audio; not browser speaker output",
        "clock": "single local monotonic clock",
        "amplitude_threshold": 200,
        "frame_resolution_ms": 20,
    }

    async def receive_audio(track):
        nonlocal last_agent_audio_at
        async for event in rtc.AudioStream(track):
            samples = array("h", event.frame.data.tobytes())
            if samples and max(abs(v) for v in samples) > 200:
                last_agent_audio_at = time.monotonic()
            if (
                pending_pause is not None
                and "first_agent_audio_at" not in pending_pause
                and samples
                and max(abs(v) for v in samples) > 200
            ):
                pending_pause["first_agent_audio_at"] = time.monotonic()

    @room.on("track_subscribed")
    def subscribed(track, publication, participant):
        if (
            track.kind == rtc.TrackKind.KIND_AUDIO
            and participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
        ):
            task = asyncio.create_task(receive_audio(track))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    async def receive(reader, identity):
        text = (await reader.read_all()).strip()
        participant = room.remote_participants.get(identity)
        if (
            text
            and participant
            and participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
        ):
            await replies.put(text)

    def handler(reader, identity):
        task = asyncio.create_task(receive(reader, identity))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    room.register_text_stream_handler("lk.transcription", handler)

    async def receive_ready(reader, identity):
        text = await reader.read_all()
        participant = room.remote_participants.get(identity)
        if (
            pending_pause is not None
            and len(text) <= 128
            and participant
            and participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
        ):
            payload = json.loads(text)
            trace_id = payload.get("trace_id", "")
            if len(trace_id) == 32 and all(c in "0123456789abcdef" for c in trace_id):
                pending_pause.setdefault("trace_id", trace_id)
                pending_pause.setdefault("reply_ready_received_at", time.monotonic())

    def ready_handler(reader, identity):
        task = asyncio.create_task(receive_ready(reader, identity))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    room.register_text_stream_handler("vab.latency.ready", ready_handler)
    headers = {"Origin": BASE, "Sec-Fetch-Site": "same-origin", "X-VAB-Guest-Call": "1"}
    async with httpx.AsyncClient(timeout=70) as client:
        r = await client.post(
            BASE + "/api/reviewer-login",
            headers=headers,
            json={"code": os.environ["VAB_EVAL_REVIEWER_CODE"]},
        )
        r.raise_for_status()

        async def request(action, **fields):
            r = await client.post(
                BASE + "/api/demo-call",
                headers=headers,
                json={"action": action, **fields},
            )
            r.raise_for_status()
            return r.json()

        call = await request("start")
        voice = call["voice_session_id"]
        evidence["voice_session_id"] = voice
        headers["X-VAB-Guest-Session"] = call["guest_call_token"]
        try:
            await room.connect(call["server_url"], call["participant_token"])
            source = rtc.AudioSource(24000, 1)
            track = rtc.LocalAudioTrack.create_audio_track(
                "isolated-nonbooking-caller", source
            )
            await room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            await request("connected", voice_session_id=voice)
            for _ in range(8):
                text = await asyncio.wait_for(replies.get(), timeout=85)
                evidence["transcript"].append({"speaker": "Avery", "text": text})
                print("AVERY", text, flush=True)
                # Do not estimate voice completion from text length: slow
                # playback can otherwise make the test caller talk over Avery.
                after = (pending_pause or {}).get("caller_speech_end_at", 0)
                deadline = time.monotonic() + 90
                while not (
                    last_agent_audio_at is not None
                    and last_agent_audio_at > after
                    and time.monotonic() - last_agent_audio_at >= 1.2
                ):
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            "No completed agent audio before caller turn"
                        )
                    await asyncio.sleep(0.1)
                answer = answer_for(text)
                if answer is None:
                    evidence["stop_reason"] = (
                        "No safe scripted response; stopped before selection"
                    )
                    break
                r = await client.post(
                    "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=linear16&sample_rate=24000&container=none",
                    headers={
                        "Authorization": "Token " + os.environ["DEEPGRAM_API_KEY"]
                    },
                    json={"text": answer},
                )
                r.raise_for_status()
                evidence["transcript"].append(
                    {"speaker": "generated caller", "text": answer}
                )
                print("CALLER", answer, flush=True)
                # Preserve all speech and internal pauses. Measure the last
                # above-threshold sample; do not count appended test silence.
                pcm = r.content
                samples = array("h", pcm)
                last_signal = next(
                    (
                        i
                        for i in range(len(samples) - 1, -1, -1)
                        if abs(samples[i]) > 200
                    ),
                    None,
                )
                if last_signal is None:
                    raise AssertionError("Generated caller audio contains no signal")
                trailing_seconds = (len(samples) - last_signal - 1) / 24000
                pending_pause = {"turn": len(evidence.get("pause_turns", [])) + 1}
                evidence.setdefault("pause_turns", []).append(pending_pause)
                started = time.monotonic()
                for offset in range(0, len(pcm), 960):
                    await source.capture_frame(
                        rtc.AudioFrame(
                            pcm[offset : offset + 960].ljust(960, b"\0"), 24000, 1, 480
                        )
                    )
                await source.wait_for_playout()
                pending_pause["caller_speech_end_at"] = (
                    time.monotonic() - trailing_seconds - ((-len(pcm)) % 960) / 48000
                )
                # Send silence separately so its duration cannot reduce the
                # measured pause by four seconds.
                for _ in range(200):
                    await source.capture_frame(
                        rtc.AudioFrame(bytes(960), 24000, 1, 480)
                    )
                await source.wait_for_playout()
                evidence.setdefault("caller_playout_seconds", []).append(
                    round(time.monotonic() - started, 3)
                )
            evidence["activity"] = await request("activity", voice_session_id=voice)
            events = evidence["activity"].get("events", [])
            assert not any(
                e.get("event_type") == "simulated_booking_recorded" for e in events
            )
            evidence["options_read_observed"] = any(
                e.get("event_type") in {"mcp_tool_called", "mcp_tool_result"}
                and e.get("payload", {}).get("tool_name") == "search_call_appointments"
                and e.get("payload", {}).get("status") == "succeeded"
                for e in events
            )
            if not evidence["options_read_observed"]:
                raise AssertionError(
                    "No successful options read; not a latency baseline"
                )
        finally:
            for turn in evidence.get("pause_turns", []):
                if "reply_ready_received_at" in turn and "caller_speech_end_at" in turn:
                    turn["speech_end_to_ready_marker_ms"] = round(
                        (turn["reply_ready_received_at"] - turn["caller_speech_end_at"])
                        * 1000,
                        1,
                    )
                if "reply_ready_received_at" in turn and "first_agent_audio_at" in turn:
                    turn["ready_marker_to_audio_ms"] = round(
                        (turn["first_agent_audio_at"] - turn["reply_ready_received_at"])
                        * 1000,
                        1,
                    )
                if "first_agent_audio_at" in turn and "caller_speech_end_at" in turn:
                    turn["speech_end_to_received_audio_ms"] = round(
                        (turn["first_agent_audio_at"] - turn["caller_speech_end_at"])
                        * 1000,
                        1,
                    )
                    turn["overlap_detected"] = (
                        turn["speech_end_to_received_audio_ms"] < 0
                    )
                else:
                    turn["measurement_incomplete"] = True
            evidence["audio_overlap_detected"] = any(
                turn.get("overlap_detected", False)
                for turn in evidence.get("pause_turns", [])
            )
            # A successful scoped read does not validate an overlapping audio
            # measurement. Keep functional and timing acceptance separate.
            evidence["pause_measurement_valid"] = (
                not evidence["audio_overlap_detected"]
                and any(
                    "speech_end_to_received_audio_ms" in turn
                    for turn in evidence.get("pause_turns", [])
                )
            )
            output.write_text(json.dumps(evidence, indent=2))
            for task in tuple(tasks):
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await room.disconnect()
            try:
                evidence["end_response"] = await request("end", voice_session_id=voice)
            except httpx.HTTPStatusError as error:
                evidence["end_error_status"] = error.response.status_code
            output.write_text(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
