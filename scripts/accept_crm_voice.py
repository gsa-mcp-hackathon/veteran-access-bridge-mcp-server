"""Synthetic CRM RTC acceptance: IBM selects identity and CRM reads/writes.

Uses an existing synthetic caller. Never sends booking consent or requests a
booking, issues capabilities, or invokes MCP tools directly. Model-selected tool
activity must be observed in the deployed frontend's authorized activity feed.
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
CASE = "DEMO-PC-P114-001"
UTTERANCES = (
    "I would like to review my call notes and follow-up requests. Do not book "
    "anything.",
    "My name is spelled Lima Uniform India Sierra nine two three space Mike "
    "Alpha Yankee Echo Romeo three seven zero. My date of birth is July "
    "third, nineteen sixty nine. Please read my call notes. Do not book "
    "anything.",
    "Please save a call note that I prefer morning callbacks. This is a "
    "synthetic test only. No staff contact is requested. Do not book "
    "anything.",
    "Please create a synthetic test follow-up for the MSA queue, due November "
    "seventeenth twenty twenty six at ten AM Central Standard Time. The "
    "description is test only, no staff contact requested. Do not book "
    "anything.",
    "Please cancel that test follow-up because this test is finished. Then "
    "read back my saved call note and confirm the task is cancelled. Do not "
    "book anything.",
)


def continuous_caller_audio(pcm: bytes) -> bytes:
    """Preserve speech frames and cap quiet TTS runs at 120ms for this fixture.

    This controlled-audio test does not establish arbitrary pause robustness.
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
    if os.getenv("VAB_RUN_CRM_VOICE_ACCEPTANCE") != CASE:
        raise PermissionError("Explicit synthetic CRM scenario opt-in required")
    output = Path(os.environ["VAB_CRM_VOICE_EVIDENCE"])
    if output.exists() or not output.parent.is_dir():
        raise PermissionError("New evidence file in an existing directory required")
    room = rtc.Room()
    replies = asyncio.Queue()
    tasks = set()
    evidence = {
        "synthetic": True,
        "expected_case": CASE,
        "transcript": [],
        "audio_condition": "TTS quiet runs capped at 120ms; speech frames retained",
    }

    async def receive(reader, identity):
        text = (await reader.read_all()).strip()
        if text and identity == room.local_participant.identity:
            evidence.setdefault("recognized_caller_transcript", []).append(text)
            return
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
    headers = {"Origin": BASE, "X-VAB-Guest-Call": "1", "Sec-Fetch-Site": "same-origin"}
    async with httpx.AsyncClient(timeout=65) as client:
        login = await client.post(
            BASE + "/api/reviewer-login",
            headers={"Origin": BASE},
            json={"code": os.environ["VAB_REVIEWER_ACCESS_CODE"]},
        )
        if login.status_code != 200:
            raise PermissionError("Reviewer sign-in failed")
        audio = {}
        for text in UTTERANCES:
            response = await client.post(
                "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=linear16&sample_rate=24000&container=none",
                headers={"Authorization": "Token " + os.environ["DEEPGRAM_API_KEY"]},
                json={"text": text},
            )
            response.raise_for_status()
            audio[text] = continuous_caller_audio(response.content)

        async def request(action, **fields):
            response = await client.post(
                BASE + "/api/demo-call",
                headers=headers,
                json={"action": action, **fields},
            )
            response.raise_for_status()
            return response.json()

        call = await request("start")
        voice = call["voice_session_id"]
        evidence.update(voice_session_id=voice, interaction_id=call["interaction_id"])
        headers["X-VAB-Guest-Session"] = call["guest_call_token"]
        started = time.monotonic()
        poll = None
        try:
            await room.connect(call["server_url"], call["participant_token"])
            source = rtc.AudioSource(24000, 1)
            track = rtc.LocalAudioTrack.create_audio_track(
                "synthetic-crm-caller", source
            )
            await room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            await request("connected", voice_session_id=voice)

            async def polling():
                while True:
                    evidence["activity"] = await request(
                        "activity", voice_session_id=voice
                    )
                    await asyncio.sleep(2.5)

            poll = asyncio.create_task(polling())

            async def hear():
                text = await asyncio.wait_for(replies.get(), timeout=85)
                evidence["transcript"].append({"speaker": "Avery", "text": text})
                print("AVERY", text, flush=True)
                await asyncio.sleep(max(3, len(text.split()) / 2.0 + 2))
                return text

            await hear()
            for text in UTTERANCES:
                evidence["transcript"].append(
                    {"speaker": "synthetic caller", "text": text}
                )
                print("CALLER", text, flush=True)
                pcm = audio[text]
                for offset in range(0, len(pcm), 960):
                    await source.capture_frame(
                        rtc.AudioFrame(
                            pcm[offset : offset + 960].ljust(960, b"\0"), 24000, 1, 480
                        )
                    )
                for _ in range(200):
                    await source.capture_frame(
                        rtc.AudioFrame(bytes(960), 24000, 1, 480)
                    )
                await source.wait_for_playout()
                answer = await hear()
                evidence["activity"] = await request("activity", voice_session_id=voice)
                identity_calls = {
                    event.get("payload", {}).get("tool_call_id")
                    for event in evidence["activity"].get("events", [])
                    if event.get("event_type") == "mcp_tool_called"
                    and event.get("payload", {}).get("tool_name")
                    == "verify_synthetic_identity"
                }
                if len(identity_calls - {None}) > 1:
                    raise AssertionError("Repeated identity call; stop this session")
                if any(
                    term in answer.lower()
                    for term in (
                        "could not verify",
                        "couldn't verify",
                        "unable to verify",
                        "identity review",
                        "wasn't able to verify",
                        "was not able to verify",
                        "wasn't able to complete identity",
                        "was not able to complete identity",
                        "could not complete identity",
                        "couldn't complete identity",
                    )
                ):
                    raise AssertionError(
                        "Identity not verified; stop without trying another identity"
                    )
            evidence["activity"] = await request("activity", voice_session_id=voice)
            events = evidence["activity"].get("events", [])
            calls = [e for e in events if e.get("event_type") == "mcp_tool_called"]
            evidence["observed_calls"] = [
                {"source": e.get("source"), **e.get("payload", {})} for e in calls
            ]
            assert not any(
                e.get("event_type") == "simulated_booking_recorded" for e in events
            )
            receipts = [
                e["payload"]["crm_receipt"]
                for e in events
                if isinstance(e.get("payload", {}).get("crm_receipt"), dict)
            ]
            evidence["crm_receipts"] = receipts
            evidence["crm_acceptance_passed"] = all(
                any(
                    r.get("operation") == name and r.get("persisted") is True
                    for r in receipts
                )
                for name in (
                    "record_crm_interaction",
                    "create_crm_follow_up",
                    "update_crm_follow_up",
                )
            )
            print(
                "CRM_RECEIPTS",
                len(receipts),
                "PASS",
                evidence["crm_acceptance_passed"],
                flush=True,
            )
            assert evidence["crm_acceptance_passed"], "Missing persisted CRM receipts"
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
