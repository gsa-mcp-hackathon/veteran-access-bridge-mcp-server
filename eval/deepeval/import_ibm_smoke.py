"""Import single-user-turn IBM evidence without executing serialized Python reprs."""

import argparse
import ast
import hashlib
import json
from pathlib import Path

CANARY_TOOLS = {
    "verify_synthetic_identity",
    "determine_workflow_state",
    "get_scheduling_encounter",
    "search_availability",
    "assess_access_standard",
    "get_case_lifecycle_state",
    "prepare_scheduling_handoff",
    "get_scheduling_handoff",
    "validate_option_selection",
    "prepare_veteran_confirmation_request",
}


def decode_result(serialized):
    """Read literal fields and TextContent text; never eval a trace."""
    tree = ast.parse(serialized, mode="eval").body
    if not isinstance(tree, ast.Dict):
        raise ValueError("Expected a result dictionary")
    fields = {ast.literal_eval(k): v for k, v in zip(tree.keys, tree.values)}
    content = fields.get("content")
    if not isinstance(content, ast.List):
        raise ValueError("Expected content list")
    blocks = []
    for item in content.elts:
        if not (
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "TextContent"
            and not item.args
        ):
            raise ValueError("Unsupported content representation")
        values = {kw.arg: ast.literal_eval(kw.value) for kw in item.keywords}
        if values.get("type") != "text" or not isinstance(values.get("text"), str):
            raise ValueError("Expected literal text content")
        blocks.append({"type": "text", "text": values["text"]})
    result = {"content": blocks, "isError": ast.literal_eval(fields["isError"])}
    if "structuredContent" in fields:
        result["structuredContent"] = ast.literal_eval(fields["structuredContent"])
    return result


def convert(path, registry, registry_hash):
    messages = [m.get("message", m) for m in json.loads(path.read_text())]
    users = [m["content"] for m in messages if m.get("role") == "user"]
    if len(users) != 1:
        raise ValueError("Single-turn metric requires exactly one user turn")
    calls, pending = [], {}
    for message in messages:
        if message.get("type") == "tool_call":
            call = json.loads(message["content"])
            if call["name"] not in CANARY_TOOLS:
                raise ValueError("Non-canary call requires a separate metric context")
            if call["id"] in pending:
                raise ValueError("Duplicate call id")
            pending[call["id"]] = call
        elif message.get("type") == "tool_response":
            response = json.loads(message["content"])
            call = pending.pop(response["tool_call_id"])
            if call["name"] != response["name"]:
                raise ValueError("Tool response does not match call")
            calls.append(
                {
                    "name": call["name"],
                    "args": call["args"],
                    "result": decode_result(response["content"]),
                    "initiator": "agent",
                }
            )
    if pending:
        raise ValueError("Missing tool response")
    output = [
        m["content"]
        for m in messages
        if m.get("role") == "assistant" and m.get("type") == "text"
    ][-1]
    return {
        "test_id": path.name.split(".")[0],
        "input": users[0],
        "actual_output": output,
        "calls": calls,
        "available_tools": [t for t in registry if t["name"] in CANARY_TOOLS],
        "trace_source": "actual_agent_trace",
        "schema_commit": "live-registry-sha256:" + registry_hash,
        "runtime_version": "IBM observation 2026-11-14; deployed image unverified",
        "trace_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scope": "Canary toolkit only; excludes other agent toolkits",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.registry.read_bytes()
    registry = json.loads(raw)
    if not CANARY_TOOLS.issubset({t["name"] for t in registry}):
        raise ValueError("Captured registry is missing assigned tools")
    records = [
        convert(
            args.run / "messages" / f"{case}.messages.json",
            registry,
            hashlib.sha256(raw).hexdigest(),
        )
        for case in ("A02", "A03", "A11")
    ]
    args.output.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    print(
        json.dumps(
            {
                "imported": len(records),
                "mcp_calls": sum(len(r["calls"]) for r in records),
            }
        )
    )


if __name__ == "__main__":
    main()
