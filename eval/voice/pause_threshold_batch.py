"""Compare speech-end detection without changing any worker or booking records.

Generated audio is reused across thresholds. This does not validate human speech.
Uses the existing approved Deepgram credential privately from the environment.
"""

import argparse
import asyncio
import json
import os
import time
from array import array
from pathlib import Path

import aiohttp
from livekit import rtc
from livekit.agents import stt
from livekit.plugins import deepgram

# Pinned to the evaluated worker's vocabulary; do not import an unrelated
# Codespace checkout when benchmarking a deployed image.
SCHEDULING_KEYTERMS = ["primary care", "Veterans Affairs", "VA Video Connect", "PACT"]

CASES = [
    ("request", ["I would like a primary care appointment next week."], 0),
    ("name", ["My name is Judy Morrison."], 0),
    ("paused_name", ["My name is Judy", "Morrison."], 1.0),
    ("paused_birthdate", ["May fifth", "nineteen", "forty five."], 1.0),
    ("long_pause_correction", ["No, I said Judy", "Morrison."], 1.5),
    ("confirmation", ["Yes, that is correct."], 0),
]


async def measure(http, pcm, threshold):
    recognizer = deepgram.STTv2(
        http_session=http,
        model="flux-general-en",
        eot_threshold=threshold,
        eot_timeout_ms=3000,
        audio_chunk_duration_ms=80,
        keyterm=SCHEDULING_KEYTERMS,
    )
    stream = recognizer.stream()
    finals = []
    speech_end = None

    async def receive():
        async for event in stream:
            if (
                event.type == stt.SpeechEventType.FINAL_TRANSCRIPT
                and event.alternatives
            ):
                finals.append(
                    {"at": time.monotonic(), "text": event.alternatives[0].text}
                )

    listener = asyncio.create_task(receive())
    samples = array("h", pcm)
    last = max(i for i, v in enumerate(samples) if abs(v) > 200)
    last_byte = last * 2
    data = pcm + bytes(48000 * 4)
    try:
        # Relative sleeps avoid bursting queued audio after scheduler stalls.
        for offset in range(0, len(data), 3840):
            chunk = data[offset : offset + 3840]
            sent = time.monotonic()
            stream.push_frame(rtc.AudioFrame(chunk, 24000, 1, len(chunk) // 2))
            if offset <= last_byte < offset + len(chunk):
                speech_end = sent + (last_byte - offset + 2) / 48000
            await asyncio.sleep(len(chunk) / 48000)
        await asyncio.sleep(0.5)
    finally:
        await stream.aclose()
        await asyncio.wait_for(listener, timeout=10)
        await recognizer.aclose()
    assert speech_end is not None
    return {
        "threshold": threshold,
        "final_segments": len(finals),
        "early_final_count": sum(x["at"] < speech_end - 0.15 for x in finals),
        "last_final_after_speech_ms": (
            round((finals[-1]["at"] - speech_end) * 1000, 1) if finals else None
        ),
        "transcript": " ".join(x["text"] for x in finals),
    }


async def main(output):
    if output.exists():
        raise RuntimeError("Preserve existing evidence")
    report = {
        "synthetic_audio": True,
        "human_pronunciation_test": False,
        "timeout_ms": 3000,
        "keyterms": SCHEDULING_KEYTERMS,
        "repetitions": 2,
        "results": [],
        "limitations": [
            "STT component comparison, not end-to-end voice latency.",
            "Early final signals truncation risk, not a proven spoken interruption.",
            "Generated audio reused; independent human repetitions still needed.",
            "Streaming timing has up to one 80 ms audio-chunk uncertainty.",
        ],
    }
    async with aiohttp.ClientSession() as http:
        for name, parts, pause in CASES:
            pcm = b""
            for index, part in enumerate(parts):
                if index:
                    pcm += bytes(int(48000 * pause))
                async with http.post(
                    "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en"
                    "&encoding=linear16&sample_rate=24000&container=none",
                    headers={
                        "Authorization": "Token " + os.environ["DEEPGRAM_API_KEY"]
                    },
                    json={"text": part},
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"TTS failed HTTP {response.status}")
                    pcm += await response.read()
            for repetition in range(2):
                thresholds = [0.85, 0.7, 0.6]
                if repetition:
                    thresholds.reverse()
                for threshold in thresholds:
                    row = await measure(http, pcm, threshold)
                    row.update(
                        case=name, repetition=repetition + 1, expected=" ".join(parts)
                    )
                    report["results"].append(row)
                    output.write_text(json.dumps(report, indent=2))
                    print(
                        json.dumps(
                            {
                                k: v
                                for k, v in row.items()
                                if k not in {"expected", "transcript"}
                            }
                        ),
                        flush=True,
                    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    asyncio.run(main(parser.parse_args().output))
