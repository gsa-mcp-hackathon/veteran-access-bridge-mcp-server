"""Report actual calls separately from IBM semantic success for no-scope cases."""

import argparse
import hashlib
import json
from pathlib import Path

from verify_consolidated_configuration import CATALOG


def review(path):
    messages = [m.get("message", m) for m in json.loads(path.read_text())]
    calls = [json.loads(m["content"]) for m in messages if m.get("type") == "tool_call"]
    protected = [c for c in calls if c["name"].split(":")[-1] in CATALOG]
    answers = [
        m for m in messages if m.get("role") == "assistant" and m.get("type") == "text"
    ]
    return {
        "scenario": path.name.split(".")[0],
        "trace_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "observed_tool_calls": [c["name"] for c in calls],
        "mcp_calls": len(protected),
        "assistant_answers": len(answers),
        "no_mcp_call_assertion": "FAIL"
        if protected
        else "PASS"
        if answers
        else "INCOMPLETE",
        "server_denial": "REVIEW_TOOL_RESPONSES" if protected else "NOT_EXERCISED",
        "scope": "No-scope negative control only; not authorized journey acceptance",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [review(args.run / "messages" / f"A{i}.messages.json") for i in (25, 26, 27)]
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(rows, stream, indent=2)
    print(json.dumps(rows, indent=2))
