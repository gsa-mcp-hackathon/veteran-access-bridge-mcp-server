"""Real RTC acceptance client for an explicitly prepared synthetic fixture.

No server, direct booking request, identity assertion, or policy bypass is used.
Requires DEEPGRAM_API_KEY in the process environment for synthetic caller speech.
Run only after preparing the existing test fixture and deploying the canary.
"""

import asyncio
import json
import os
import time
from array import array
from pathlib import Path

import httpx
from livekit import rtc

BASE = "https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"
CASE = os.getenv("VAB_RUN_SYNTHETIC_BROWSER_ACCEPTANCE", "")
IDENTITY_ONLY = os.getenv("VAB_BROWSER_IDENTITY_ONLY") == "true"
AGENT_FLOW = os.getenv("VAB_ACCEPT_AGENT_LED") == "true"
FIXTURES = {
    "VAB-DEMO-20261113-CASE-047": (
        "My name is Judy Morrison.",
        "May fifth, nineteen forty five.",
    ),
    "VAB-DEMO-20261113-CASE-046": (
        "My name is Judy Morrison.",
        "May fifth, nineteen forty five.",
    ),
    # CASE-031/033/035/037/039 are consumed. CASE-041 was separately approved.
    # Read-only preflight must confirm it remains unused before this run.
    "VAB-DEMO-20261113-CASE-041": (
        "My name is spelled Golf Echo Romeo Romeo Yankee nine one space "
        "Tango Oscar Romeo Papa Hotel Yankee six three zero.",
        "May twenty first, nineteen sixty seven.",
    ),
}
CONSUMED_CASES = frozenset({"VAB-DEMO-20261113-CASE-041", "VAB-DEMO-20261113-CASE-047"})


def continuous_caller_audio(pcm: bytes) -> bytes:
    """Bound TTS pauses for this test caller; never alter recognized speech.

    Preserve every non-quiet 20ms frame; cap quiet runs at 120ms so the generated
    name and confirmation are spoken continuously. This is a controlled-audio test,
    not evidence of resilience to arbitrary pauses or interruptions.
    """
    output = bytearray()
    quiet_frames = 0
    for offset in range(0, len(pcm), 960):
        chunk = pcm[offset : offset + 960]
        samples = array("h", chunk)
        quiet = not samples or max(abs(value) for value in samples) < 200
        quiet_frames = quiet_frames + 1 if quiet else 0
        if not quiet or quiet_frames <= 6:
            output.extend(chunk)
    return bytes(output)


async def main():
    if (CASE == "VAB-DEMO-20261113-CASE-047") != AGENT_FLOW:
        raise PermissionError(
            "Explicit agent-led rehearsal opt-in required for CASE-047"
        )
    if CASE == "VAB-DEMO-20261113-CASE-046" and not IDENTITY_ONLY:
        raise PermissionError("CASE-046 is reserved for the user's rehearsal")
    identity_recheck = (
        AGENT_FLOW and IDENTITY_ONLY and CASE == "VAB-DEMO-20261113-CASE-047"
    )
    if CASE not in FIXTURES or (CASE in CONSUMED_CASES and not identity_recheck):
        raise PermissionError("Explicit approved, unused synthetic fixture required")
    output = Path(os.environ["VAB_BROWSER_ACCEPTANCE_EVIDENCE"])
    if output.exists() or not output.parent.is_dir():
        raise PermissionError("New evidence path in an existing directory required")
    key = os.environ["DEEPGRAM_API_KEY"]
    evidence = {"synthetic": True, "booking_case_id": CASE, "transcript": []}
    room = rtc.Room()
    queue = asyncio.Queue()
    tasks = set()
    awaiting_audio = None

    async def receive_audio(track):
        nonlocal awaiting_audio
        async for event in rtc.AudioStream(track):
            if awaiting_audio is not None:
                samples = array("h", event.frame.data.tobytes())
                if samples and max(abs(v) for v in samples) > 200:
                    evidence.setdefault("first_audio_latency_seconds", []).append(
                        round(time.monotonic() - awaiting_audio, 3)
                    )
                    awaiting_audio = None

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
        if identity == room.local_participant.identity and text:
            print("Caller STT:", text, flush=True)
            evidence.setdefault("caller_stt", []).append(text)
        participant = room.remote_participants.get(identity)
        if (
            participant
            and participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
            and text
        ):
            await queue.put(text)

    def handler(reader, identity):
        task = asyncio.create_task(receive(reader, identity))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    room.register_text_stream_handler("lk.transcription", handler)
    # Reproduce the browser request contract; all server gates remain enabled.
    headers = {
        "Origin": BASE,
        "X-VAB-Guest-Call": "1",
        "Sec-Fetch-Site": "same-origin",
    }
    async with httpx.AsyncClient(timeout=65) as client:
        login = await client.post(
            BASE + "/api/reviewer-login",
            headers={"Origin": BASE},
            json={"code": os.environ["VAB_REVIEWER_ACCESS_CODE"]},
        )
        if login.status_code != 200:
            raise PermissionError("Reviewer sign-in failed")
        # Prepare caller audio before issuing a short-lived guest session.
        # This changes test pacing only, not runtime expiry or authorization.
        name, dob = FIXTURES[CASE]
        if identity_recheck:
            name = "I'm Judy Morris."
        speech = {}
        spelled_retry = name.replace(" ", ", ").replace("Spelled,", "Spelled")
        utterances = (
            "I would like to schedule a Primary Care appointment.",
            name,
            dob,
            spelled_retry,
        )
        if not IDENTITY_ONLY:
            utterances += (
                "Yes, book that appointment.",
                "Yes book that appointment.",
                "Is my appointment already booked?",
            )
        if AGENT_FLOW:
            utterances += (
                "Yes, that's correct.",
                "No, my last name is Morrison.",
                "Central time.",
                "What does your scheduling guidance say about making an appointment?",
                "A routine follow up, mornings please.",
                "The first appointment, please.",
                "Yes, please.",
            )
        for text in utterances:
            response = await client.post(
                "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=linear16&sample_rate=24000&container=none",
                headers={"Authorization": "Token " + key},
                json={"text": text},
            )
            response.raise_for_status()
            speech[text] = (
                response.content
                if identity_recheck
                else continuous_caller_audio(response.content)
            )
        evidence["caller_audio_condition"] = (
            "Original generated caller audio; no pause compression"
            if identity_recheck
            else "All caller TTS quiet runs capped at 120ms; speech frames retained"
        )

        async def request(action, **fields):
            response = await client.post(
                BASE + "/api/demo-call",
                headers=headers,
                json={"action": action, **fields},
            )
            if response.status_code != 200:
                raise RuntimeError(f"Gateway {action} returned {response.status_code}")
            return response.json()

        call = await request("start")
        started = time.monotonic()
        voice = call["voice_session_id"]
        evidence.update(voice_session_id=voice, interaction_id=call["interaction_id"])
        headers["X-VAB-Guest-Session"] = call["guest_call_token"]
        poll = None
        try:
            await room.connect(call["server_url"], call["participant_token"])
            source = rtc.AudioSource(24000, 1)
            track = rtc.LocalAudioTrack.create_audio_track("synthetic-caller", source)
            await room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            await request("connected", voice_session_id=voice)

            async def poll_activity():
                while True:
                    evidence["latest_activity"] = await request(
                        "activity", voice_session_id=voice
                    )
                    await asyncio.sleep(2.5)

            # Match the actual UI's authorized activity polling during a call.
            poll = asyncio.create_task(poll_activity())

            async def reply_contains(expected, retry_name=False, retry_consent=False):
                for _ in range(8):
                    reply = await asyncio.wait_for(queue.get(), timeout=70)
                    print("Avery:", reply, flush=True)
                    evidence["transcript"].append({"speaker": "Avery", "text": reply})
                    if "could not verify" in reply.lower():
                        raise AssertionError("Identity rejected; stop the call")
                    if retry_consent and "not booked" in reply.lower():
                        await asyncio.sleep(max(8, len(reply.split()) / 2 + 2))
                        await speak("Yes book that appointment.")
                        retry_consent = False
                    if retry_name and "please spell" in reply.lower():
                        await asyncio.sleep(max(8, len(reply.split()) / 2 + 2))
                        await speak(spelled_retry)
                        retry_name = False
                    if any(
                        term in reply.lower()
                        for term in (
                            expected if isinstance(expected, tuple) else (expected,)
                        )
                    ):
                        # Transcript delivery may precede audible playback and
                        # the worker may not expose lk.agent.state immediately.
                        # Match the conservative pacing of the CRM voice harness.
                        await asyncio.sleep(max(3, len(reply.split()) / 2 + 2))
                        for _ in range(120):
                            if all(
                                p.attributes.get("lk.agent.state") != "speaking"
                                for p in room.remote_participants.values()
                            ):
                                break
                            await asyncio.sleep(0.25)
                        return
                raise AssertionError("Expected protected prompt was not received")

            async def speak(text):
                nonlocal awaiting_audio
                evidence["transcript"].append(
                    {"speaker": "synthetic caller", "text": text}
                )
                print("Caller:", text, flush=True)
                pcm = speech[text]
                for offset in range(0, len(pcm), 960):
                    chunk = pcm[offset : offset + 960].ljust(960, b"\0")
                    await source.capture_frame(rtc.AudioFrame(chunk, 24000, 1, 480))
                await source.wait_for_playout()
                awaiting_audio = time.monotonic()
                # A browser microphone keeps sending frames after speech. Supply
                # trailing silence so STT can finalize even a short yes/no turn.
                for _ in range(200):
                    await source.capture_frame(
                        rtc.AudioFrame(bytes(960), 24000, 1, 480)
                    )
                await source.wait_for_playout()

            await reply_contains("avery")
            await speak("I would like to schedule a Primary Care appointment.")
            await reply_contains("full name")
            await speak(name)
            await reply_contains("date of birth", retry_name=True)
            await speak(dob)
            if AGENT_FLOW:
                await reply_contains("is that correct")
                if identity_recheck:
                    await speak("No, my last name is Morrison.")
                    await reply_contains("is that correct")
                await speak("Yes, that's correct.")
                await reply_contains("time zone")
                if identity_recheck:
                    page = await request("activity", voice_session_id=voice)
                    assert not any(
                        e.get("event_type") == "simulated_booking_recorded"
                        for e in page.get("events", [])
                    )
                    evidence["identity_correction_verified"] = True
                    evidence["stopped_before_scheduling"] = True
                    evidence["activity"] = page
                    print(
                        "Identity readback and correction verified; "
                        "no scheduling requested",
                        flush=True,
                    )
                    return
                await speak("Central time.")
                await reply_contains("days or times")
                await speak(
                    "What does your scheduling guidance say "
                    "about making an appointment?"
                )
                await reply_contains("draft")
                await speak("A routine follow up, mornings please.")
                await reply_contains(("november", "wednesday", "thursday", "friday"))
                page = await request("activity", voice_session_id=voice)
                options = [
                    e["payload"]
                    for e in page.get("events", [])
                    if e.get("event_type") == "options_presented"
                    and e.get("payload", {}).get("options")
                ]
                assert options and len(options[-1]["options"]) == 2
                assert options[-1]["patient_time_zone"] == "America/Chicago"
                await speak("The first appointment, please.")
                await reply_contains("shall i book")
                await speak("Yes, please.")
                await reply_contains("appointment is confirmed")
                await speak("Is my appointment already booked?")
                await reply_contains("already confirmed")
            else:
                await reply_contains("to confirm")
            if IDENTITY_ONLY:
                page = await request("activity", voice_session_id=voice)
                assert not any(
                    e.get("event_type") == "simulated_booking_recorded"
                    for e in page.get("events", [])
                )
                evidence["identity_and_offer_verified"] = True
                evidence["stopped_before_consent"] = True
                evidence["activity"] = page
                print("Identity and offer verified; stopped before consent", flush=True)
                return
            if not AGENT_FLOW:
                await speak("Yes book that appointment.")
                await reply_contains(
                    "booked and independently verified", retry_consent=True
                )
                await speak("Is my appointment already booked?")
                await reply_contains("already verified")
            page = await request("activity", voice_session_id=voice)
            evidence["activity"] = page
            if AGENT_FLOW:
                observed = {
                    e.get("payload", {}).get("tool_name")
                    for e in page.get("events", [])
                    if e.get("payload", {}).get("invoked_by") == "agent"
                    and e.get("payload", {}).get("scope_verified") is True
                }
                required = {
                    "get_va_patient_health_sandbox_summary",
                    "search_call_knowledge",
                    "search_call_appointments",
                    "select_call_appointment",
                    "book_call_appointment",
                }
                assert required <= observed, (
                    f"Missing agent-selected tool receipts: {required - observed}"
                )
                evidence["agent_selected_tools_verified"] = sorted(required)
            proofs = [
                e["payload"]
                for e in page.get("events", [])
                if e.get("event_type") == "simulated_booking_recorded"
            ]
            assert len(proofs) == 1 and proofs[0]["voice_session_id"] == voice
            assert (
                proofs[0]["booking_case_id"] == CASE and proofs[0]["verified"] is True
            )
            evidence["receipt"] = proofs[0]
            assert proofs[0].get("crm_note_status") == "SAVED"
            assert proofs[0].get("crm_note_origin") == "trusted_booking_host"
            assert proofs[0].get("crm_note_id")
            print("RECEIPT", json.dumps(proofs[0]), flush=True)
        finally:
            if poll is not None:
                poll.cancel()
                await asyncio.gather(poll, return_exceptions=True)
            evidence["elapsed_seconds"] = round(time.monotonic() - started, 2)
            output.write_text(json.dumps(evidence, indent=2))
            await room.disconnect()
            evidence["end_response"] = await request("end", voice_session_id=voice)
            output.write_text(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
