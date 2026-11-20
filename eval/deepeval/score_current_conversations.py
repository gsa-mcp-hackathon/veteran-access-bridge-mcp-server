"""Score complete recorded IBM conversations, retaining real turn boundaries.

No agent, server or database calls. Model scoring is explicit; telemetry is off.
Security authorization and no-call assertions remain separate from judge scores.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
os.environ.pop("CONFIDENT_API_KEY", None)

from import_ibm_smoke import decode_result  # noqa: E402
from verify_consolidated_configuration import ALLOWED  # noqa: E402


def sanitize(value):
    if isinstance(value, str):
        return re.sub(r"vab_scope_[A-Za-z0-9_-]+", "[REDACTED_SCOPE]", value)
    if isinstance(value, list):
        return [sanitize(x) for x in value]
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    return value


def convert(messages):
    turns, pending, completed = [], {}, []
    for wrapped in messages:
        message = wrapped.get("message", wrapped)
        kind, role = message.get("type"), message.get("role")
        if kind == "tool_call":
            call = json.loads(message["content"])
            name = call["name"].split(":")[-1]
            if name not in ALLOWED or call["id"] in pending:
                raise ValueError("Unreviewed or duplicate tool call")
            pending[call["id"]] = {**call, "name": name}
        elif kind == "tool_response":
            response = json.loads(message["content"])
            call = pending.pop(response["tool_call_id"])
            if response["name"].split(":")[-1] != call["name"]:
                raise ValueError("Mismatched tool response")
            content = response["content"]
            if isinstance(content, str) and content.startswith("Error calling tool "):
                result = {
                    "content": [{"type": "text", "text": content}],
                    "isError": True,
                }
            elif isinstance(content, dict):
                result = content
            else:
                result = decode_result(content)
            completed.append(
                {"name": call["name"], "args": call["args"], "result": result}
            )
        elif role in {"user", "assistant"} and kind == "text":
            if role == "user" and (pending or completed):
                raise ValueError("Unresolved tool activity before next user turn")
            turn = {"role": role, "content": message["content"]}
            if role == "assistant":
                if pending:
                    raise ValueError("Missing tool result")
                turn["calls"] = completed
                completed = []
            turns.append(turn)
    if pending or completed or not turns or turns[-1]["role"] != "assistant":
        raise ValueError("Incomplete conversation evidence")
    return sanitize(turns)


def interaction_turns(turns):
    """Represent observed MCP events before their spoken assistant answer.

    DeepEval 4.3.4's task extractor skips two-message user/assistant units.
    Combining calls with speech therefore silently produces no scored tasks.
    Empty content denotes an actual tool event, never invented model speech.
    """
    result = []
    for turn in turns:
        for call in turn.get("calls", []):
            result.append({"role": "assistant", "content": "", "calls": [call]})
        result.append({"role": turn["role"], "content": turn["content"], "calls": []})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--runtime-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Never overwrite evaluation evidence")
    if args.score and not args.model:
        parser.error("Scoring requires an explicit approved judge model")

    from deepeval.test_case import ConversationalTestCase, MCPServer, MCPToolCall, Turn
    from mcp.types import CallToolResult

    raw_registry = args.registry.read_bytes()
    registry = json.loads(raw_registry)
    selected = [t for t in registry if t["name"] in ALLOWED]
    if len(registry) != 21 or {t["name"] for t in selected} != ALLOWED:
        raise ValueError("Require captured 21-tool registry and 13 assigned tools")
    rows = []
    for case in args.cases.split(","):
        path = args.run / "messages" / (case + ".messages.json")
        raw = path.read_bytes()
        turns = convert(json.loads(raw))
        count = sum(len(t.get("calls", [])) for t in turns)
        record = {
            "case": case,
            "runtime_version": args.runtime_version,
            "trace_sha256": hashlib.sha256(raw).hexdigest(),
            "registry_sha256": hashlib.sha256(raw_registry).hexdigest(),
            "turns": len(turns),
            "observed_mcp_calls": count,
            "scope": (
                "Recorded conversation and observed tool events; not booking acceptance"
            ),
            "status": "VALIDATED_NOT_SCORED",
            "scope_values_redacted": True,
        }
        test = ConversationalTestCase(
            turns=[
                Turn(
                    role=t["role"],
                    content=t["content"],
                    mcp_tools_called=[
                        MCPToolCall(
                            name=c["name"],
                            args=c["args"],
                            result=CallToolResult.model_validate(c["result"]),
                        )
                        for c in t.get("calls", [])
                    ],
                )
                for t in interaction_turns(turns)
            ],
            mcp_servers=[
                MCPServer(server_name="Veteran Access MCP", available_tools=selected)
            ],
        )
        if args.score and count:
            from deepeval.metrics import MultiTurnMCPUseMetric

            metric = MultiTurnMCPUseMetric(
                model=args.model, threshold=0.8, eval_mode="llm", async_mode=False
            )
            # Guard the adapter against silently scoring an empty task set.
            from importlib import import_module

            units = import_module(type(metric).__module__).get_unit_interactions(
                test.turns
            )
            tasks = metric._get_tasks(units)
            if not tasks:
                raise ValueError("Observed MCP calls produced no DeepEval tasks")
            metric.measure(test)
            record.update(
                status="SCORED",
                score=metric.score,
                reason=metric.reason,
                judge_model=args.model,
                evaluation_cost_usd=str(metric.evaluation_cost),
                evaluated_tasks=len(metric.tasks),
                primitive_scores=metric.tools_scores_reasons_list,
                argument_scores=metric.args_scores_reasons_list,
            )
        elif args.score:
            record.update(
                status="NOT_APPLICABLE_NO_MCP_CALLS",
                reason=(
                    "Use the deterministic no-call assertion; zero interactions "
                    "is not a tool-use quality score."
                ),
            )
        rows.append(record)
        args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
