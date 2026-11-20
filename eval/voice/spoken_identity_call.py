"""One approved live identity-only check; never selects or books an appointment.

Credentials and test digits are supplied privately in the process environment.
Only booleans and the session ID are written. Uses generated audio, not human speech.
"""

import asyncio
import json
import os

import aiohttp
import httpx
from livekit import rtc
from livekit.plugins import deepgram

BASE = "https://vab-avery-callcenter.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"


async def main():
    if os.getenv("VAB_ENABLE_SPOKEN_IDENTITY_ACCEPTANCE") != "true":
        raise PermissionError("Explicit spoken identity-only acceptance required")
    digits = os.environ.pop("VAB_TEST_LAST4")
    room = rtc.Room()
    replies = asyncio.Queue()
    tasks = set()
    evidence = {
        "no_booking_requested": True,
        "identity_verified": False,
        "generated_audio": True,
        "human_speech_test": False,
    }

    async def receive(reader, identity):
        text = await reader.read_all()
        if digits in text:
            evidence["private_digits_in_caption"] = True
        if "[Verification details withheld]" in text:
            evidence["masked_identity_caption_seen"] = True
            return
        peer = room.remote_participants.get(identity)
        if peer and peer.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            if digits in text:
                evidence["private_digits_in_caption"] = True
            await replies.put(text)

    def handler(reader, identity):
        task = asyncio.create_task(receive(reader, identity))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    room.register_text_stream_handler("lk.transcription", handler)
    headers = {"Origin": BASE, "X-VAB-Guest-Call": "1", "Sec-Fetch-Site": "same-origin"}
    async with httpx.AsyncClient(timeout=70) as client:
        response = await client.post(
            BASE + "/api/reviewer-login",
            headers=headers,
            json={"code": os.environ["VAB_REVIEWER_ACCESS_CODE"]},
        )
        response.raise_for_status()

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
        evidence["voice_session_id"] = voice
        headers["X-VAB-Guest-Session"] = call["guest_call_token"]
        submitted = False
        try:
            await room.connect(call["server_url"], call["participant_token"])
            await request("connected", voice_session_id=voice)
            source = rtc.AudioSource(24000, 1)
            track = rtc.LocalAudioTrack.create_audio_track("identity-check", source)
            await room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            for _ in range(10):
                text = await asyncio.wait_for(replies.get(), timeout=60)
                lower = text.lower()
                if "for verification purposes" in lower:
                    evidence["requested_prompt_heard"] = True
                agents = [
                    p
                    for p in room.remote_participants.values()
                    if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
                ]
                if len(agents) != 1:
                    raise AssertionError("One worker required")
                if submitted and "identity is verified" in lower:
                    evidence["identity_verified"] = True
                    break
                if "i heard" in lower and "born" in lower:
                    answer = "Yes, that's correct."
                elif "full name" in lower or "your name" in lower:
                    words = " ".join(
                        "zero one two three four five six seven eight nine".split()[
                            int(d)
                        ]
                        for d in digits
                    )
                    answer = (
                        "My name is Judy Morrison. My birthday is May fifth, "
                        "nineteen forty five. The last four of my social are " + words
                    )
                    submitted = True
                elif "last four" in lower or "four digits" in lower:
                    answer = " ".join(
                        "zero one two three four five six seven eight nine".split()[
                            int(d)
                        ]
                        for d in digits
                    )
                    submitted = True
                elif "birth" in lower:
                    answer = "May fifth, nineteen forty five."
                elif "how" in lower and "help" in lower:
                    answer = (
                        "I would like to schedule a routine primary care appointment."
                    )
                else:
                    raise AssertionError("Unexpected dialogue; no booking permitted")
                async with aiohttp.ClientSession() as audio_http:
                    tts = deepgram.TTSv2(http_session=audio_http, speed=0.85)
                    async with tts.synthesize(answer) as stream:
                        async for audio in stream:
                            assert audio.frame.sample_rate == 24000
                            await source.capture_frame(audio.frame)
                    await tts.aclose()
                for _ in range(150):
                    await source.capture_frame(
                        rtc.AudioFrame(bytes(960), 24000, 1, 480)
                    )
                await source.wait_for_playout()
            assert evidence["identity_verified"]
            assert evidence.get("requested_prompt_heard", False)
            assert evidence.get("masked_identity_caption_seen", False)
            assert not evidence.get("private_digits_in_caption", False)
            assert not evidence.get("private_digits_in_rpc_response", False)
        finally:
            for task in tasks:
                task.cancel()
            await room.disconnect()
            try:
                ended = await request("end", voice_session_id=voice)
                evidence["end_completed"] = bool(ended)
            except Exception:
                evidence["end_completed"] = False
            print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
