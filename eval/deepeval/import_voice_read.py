"""Assemble a complete read conversation from native IBM inputs and tool spans.

Requires exact history-prefix and server-receipt correlations. Never invents
missing calls or results. The final answer is the observed LiveKit delivery;
application-rewritten answers are rejected for this agent-only scoring lane.
"""

import argparse
import hashlib
import json
from pathlib import Path

from review_agent_read import review
from score_current_conversations import convert, sanitize


def history(groups):
    messages = next(x for x in groups if isinstance(x, list))
    if any(x.get("role") not in {"system", "user", "assistant"} for x in messages):
        raise ValueError("Unsupported history roles; cannot silently discard tools")
    result = [
        {"role": x["role"], "type": "text", "content": x["content"]}
        for x in messages
        if x["role"] != "system"
    ]
    if not result or any(not isinstance(x["content"], str) for x in result):
        raise ValueError("Complete text history required")
    return result


def tool_messages(observations):
    messages = []
    for o in sorted(observations, key=lambda x: x.get("startTime", "")):
        if o["type"] != "TOOL":
            raise ValueError("Only native tool observations are accepted")
        output = o["output"]
        name = o["name"].removeprefix("tool.")
        if output["name"].split(":")[-1] != name:
            raise ValueError("Tool name mismatch")
        content = output["content"]
        text = content if isinstance(content, str) else json.dumps(content)
        result = {
            "content": [{"type": "text", "text": text}],
            "isError": text.startswith("Error calling tool "),
        }
        messages += [
            {
                "type": "tool_call",
                "content": json.dumps(
                    {"name": name, "id": output["tool_call_id"], "args": o["input"]}
                ),
            },
            {
                "type": "tool_response",
                "content": json.dumps(
                    {
                        "name": name,
                        "tool_call_id": output["tool_call_id"],
                        "content": result,
                    }
                ),
            },
        ]
    return messages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--initial-trace", required=True)
    parser.add_argument("--followup-trace", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    p = args.directory

    def read(name):
        return json.loads((p / name).read_text())

    proof = read("v11-read01-evidence.json")
    verified = review(proof, expected_case="DEMO-PC-P114-001")
    if verified["verified_agent_reads"] != 2:
        raise ValueError("Exactly two read turns required")
    if any(
        e["event_type"] == "agent_answered" and e["source"] != "watsonx_orchestrate"
        for e in proof["activity"]["events"]
    ):
        raise ValueError("Application-modified delivery is not raw agent scoring")
    first = history(read(args.initial_trace + "-v11-inputs-private.json"))
    second = history(read(args.followup_trace + "-v11-inputs-private.json"))
    if second[: len(first)] != first or second[len(first)]["role"] != "assistant":
        raise ValueError("Native history prefix does not match")
    first_tools = read(args.initial_trace + "-v11-tools-private.json")
    second_tools = read(args.followup_trace + "-v11-tools-private.json")
    wanted = {
        e["payload"]["tool_call_id"]
        for e in proof["activity"]["events"]
        if e.get("payload", {}).get("evidence") == "server_scope_receipt"
    }
    actual = [o["output"]["tool_call_id"] for o in first_tools + second_tools]
    if set(actual) != wanted or len(actual) != len(wanted):
        raise ValueError("Native call IDs do not match server receipts")
    capture = read("v11-read01-private.json")
    if capture.get("end_response", {}).get("ok") is not True:
        raise ValueError("Completed call required")
    answer = capture["transcript"][-1]
    if answer["speaker"] != "Avery":
        raise ValueError("Final spoken assistant answer required")
    messages = (
        second[: len(first)]
        + tool_messages(first_tools)
        + second[len(first) :]
        + tool_messages(second_tools)
        + [{"role": "assistant", "type": "text", "content": answer["text"]}]
    )
    messages = sanitize(messages)
    convert(messages)  # Reject orphan calls, incomplete results and turn boundaries.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as f:
        json.dump(messages, f, indent=2)
    print(
        json.dumps(
            {
                "messages": len(messages),
                "tool_calls": len(actual),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
