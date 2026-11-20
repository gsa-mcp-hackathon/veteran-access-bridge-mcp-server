import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path

import aiohttp
from livekit import rtc
from livekit.agents import stt
from livekit.plugins import deepgram

from veteran_access_bridge.voice.livekit_worker import SCHEDULING_KEYTERMS

parser = argparse.ArgumentParser(
    description="Eight generated-audio checks using the existing DEEPGRAM_API_KEY."
)
parser.add_argument("--output", required=True)
OUT = Path(parser.parse_args().output)
if OUT.exists():
    raise RuntimeError("Preserve prior benchmark")
if not os.environ.get("DEEPGRAM_API_KEY"):
    raise RuntimeError("Set the existing approved DEEPGRAM_API_KEY privately")
CASES = [
    ("scheduling", ["I need a primary care appointment with my PACT team."]),
    (
        "identity",
        [
            "My name is Ruben Moreno. My birthday is December thirtieth, "
            "nineteen forty nine."
        ],
    ),
    (
        "paused_birthdate",
        ["My birthday is December thirtieth,", "nineteen", "forty nine."],
    ),
    ("correction", ["No, I said Morrison. M O R R I S O N."]),
]


def tokens(s):
    return re.findall(r"[a-z0-9]+", s.lower())


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        new = [i]
        for j, y in enumerate(b, 1):
            new.append(min(new[-1] + 1, row[j] + 1, row[j - 1] + (x != y)))
        row = new
    return row[-1]


async def main():
    report = {"synthetic_audio": True, "human_pronunciation_test": False, "results": []}
    async with aiohttp.ClientSession() as http:
        tts = deepgram.TTSv2(http_session=http, speed=0.85)
        for name, parts in CASES:
            pcm = b""
            for i, part in enumerate(parts):
                if i:
                    pcm += bytes(24000 * 2)
                async with tts.synthesize(part) as stream:
                    async for audio in stream:
                        pcm += bytes(audio.frame.data)
            for mode in ["baseline", "vocabulary"]:
                recognizer = deepgram.STTv2(
                    http_session=http,
                    eot_threshold=0.7,
                    eot_timeout_ms=3000,
                    audio_chunk_duration_ms=80,
                    **(
                        {"keyterm": SCHEDULING_KEYTERMS} if mode == "vocabulary" else {}
                    ),
                )
                stream = recognizer.stream()
                finals = []
                start = time.monotonic()

                async def receive():
                    async for e in stream:
                        if (
                            e.type == stt.SpeechEventType.FINAL_TRANSCRIPT
                            and e.alternatives
                        ):
                            finals.append(
                                {
                                    "text": e.alternatives[0].text,
                                    "elapsed_s": round(time.monotonic() - start, 3),
                                }
                            )

                listener = asyncio.create_task(receive())
                data = pcm + bytes(24000 * 2 * 4)
                for offset in range(0, len(data), 3840):
                    chunk = data[offset : offset + 3840]
                    stream.push_frame(rtc.AudioFrame(chunk, 24000, 1, len(chunk) // 2))
                    await asyncio.sleep(len(chunk) / (24000 * 2))
                await asyncio.sleep(0.5)
                await stream.aclose()
                await listener
                await recognizer.aclose()
                expected = " ".join(parts)
                actual = " ".join(x["text"] for x in finals)
                row = {
                    "case": name,
                    "mode": mode,
                    "expected": expected,
                    "transcript": actual,
                    "final_segments": len(finals),
                    "word_error_rate": round(
                        distance(tokens(expected), tokens(actual))
                        / len(tokens(expected)),
                        3,
                    ),
                    "finals": finals,
                }
                report["results"].append(row)
                OUT.write_text(json.dumps(report, indent=2))
                print(json.dumps(row), flush=True)
        await tts.aclose()


asyncio.run(main())
