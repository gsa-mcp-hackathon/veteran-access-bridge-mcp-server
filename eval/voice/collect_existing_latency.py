"""Read existing Code Engine logs; export only allowlisted timing fields.

Does not invoke an agent, start a call, or change any deployed configuration.
Run in the existing authenticated Codespace. Raw logs stay in process memory.
"""

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone

PATTERNS = {
    "source": (
        r"VAB source stage=(?P<stage>va_token|va_resource|kb_connection|kb_query) "
        r"duration_ms=(?P<duration_ms>[\d.]+)"
    ),
    "ibm": (
        r"Orchestrate request auth_ms=(?P<auth_ms>[\d.]+) "
        r"request_ms=(?P<request_ms>[\d.]+) "
        r"attempt=(?P<attempt>\d+) status=(?P<status>\d+)"
    ),
    "mcp": (
        r"Voice MCP operation tool=(?P<tool>[a-z_]+) "
        r"duration_ms=(?P<duration_ms>[\d.]+)"
    ),
    "reply": (
        r"Avery reply ready bridge_ms=(?P<bridge_ms>[\d.]+) "
        r"final_to_reply_ms=(?P<final_to_reply_ms>[\d.]+) "
        r"queue_ms=(?P<queue_ms>[\d.]+) "
        r"input_source=(?P<input_source>speech|typed) "
        r"reply_chars=(?P<reply_chars>\d+)"
    ),
    "speech": (
        r"Avery speech completed say_ms=(?P<say_ms>[\d.]+) "
        r"final_to_speech_complete_ms=(?P<final_to_speech_complete_ms>[\d.]+)"
    ),
    "stage": (
        r"Voice stage metric type=(?P<metric_type>[A-Za-z]+) "
        r"field=(?P<field>end_of_utterance_delay|transcription_delay|ttfb|duration) "
        r"seconds=(?P<seconds>[\d.]+)"
    ),
}


def read_ce(*args):
    result = subprocess.run(
        ["ibmcloud", "ce", *args], capture_output=True, text=True, timeout=60
    )
    if result.returncode:
        raise RuntimeError("IBM read failed; raw output suppressed")
    return result.stdout


def snapshot(name):
    app = json.loads(read_ce("app", "get", "-n", name, "-o", "json"))
    digest = hashlib.sha256(
        json.dumps(app["spec"], sort_keys=True).encode()
    ).hexdigest()
    return app["status"]["latestReadyRevisionName"], digest


def main():
    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "kind": "existing_application_log_sample",
        "limitations": [
            "Not a controlled benchmark; no new call was made.",
            "No turn identifiers: do not join spans across processes.",
            "Speech completion includes speaking duration, not first audio.",
            "Current revision does not prove every retained line's revision.",
        ],
        "applications": [],
    }
    for name in ("veteran-access-bridge-m64-canary", "vab-avery-voice-worker"):
        before = snapshot(name)
        raw = read_ce(
            "app", "logs", "-n", name, "--tail", "10000", "--raw", "--timestamps"
        )
        events = []
        for line in raw.splitlines():
            for kind, pattern in PATTERNS.items():
                match = re.search(pattern, line)
                if match:
                    stamp = re.search(r"\d{4}-\d\d-\d\dT[\d:.]+Z", line)
                    trace = re.search(r"\btrace_id=([a-f0-9]{32}|unscoped)\b", line)
                    outcome = re.search(r"\boutcome=(returned|error)\b", line)
                    events.append(
                        {
                            "kind": kind,
                            "timestamp": stamp.group() if stamp else None,
                            **({"trace_id": trace.group(1)} if trace else {}),
                            **({"outcome": outcome.group(1)} if outcome else {}),
                            **{
                                key: float(value)
                                if re.fullmatch(r"[\d.]+", value)
                                else value
                                for key, value in match.groupdict().items()
                            },
                        }
                    )
        report["applications"].append(
            {
                "name": name,
                "observed_ready_revision": before[0],
                "specification_and_revision_unchanged": before == snapshot(name),
                "log_lines_scanned": len(raw.splitlines()),
                "events": events,
            }
        )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
