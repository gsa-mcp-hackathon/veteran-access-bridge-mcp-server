"""Validate/score real MCP traces. Never synthesize missing tool calls.

Default is offline validation only. Scoring requires an explicit configured model
and an input bundle containing actual agent-selected calls and frozen schemas.
No application or database mutation is performed here.
"""

import argparse
import json
import os
from pathlib import Path

os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "YES"
os.environ.pop("CONFIDENT_API_KEY", None)

from deepeval.test_case import LLMTestCase, MCPServer, MCPToolCall  # noqa: E402
from mcp.types import CallToolResult  # noqa: E402


def build_case(record):
    for field in (
        "test_id",
        "input",
        "actual_output",
        "schema_commit",
        "calls",
        "available_tools",
        "trace_source",
        "runtime_version",
    ):
        if field not in record:
            raise ValueError(f"Missing trace evidence field: {field}")
    if record["trace_source"] != "actual_agent_trace":
        raise ValueError("Agent evaluation requires actual agent-selected calls")
    names = {t["name"] for t in record["available_tools"]}
    calls = []
    for call in record["calls"]:
        if call.get("initiator") != "agent":
            raise ValueError("Host-invoked calls cannot count as agent selection")
        if call["name"] not in names:
            raise ValueError("Observed tool missing from the captured registry")
        if not isinstance(call.get("args"), dict) or "result" not in call:
            raise ValueError("Actual arguments and returned result are required")
        calls.append(
            MCPToolCall(
                name=call["name"],
                args=call["args"],
                result=CallToolResult.model_validate(call["result"]),
            )
        )
    return LLMTestCase(
        input=record["input"],
        actual_output=record["actual_output"],
        mcp_servers=[
            MCPServer(
                server_name="Veteran Access MCP",
                available_tools=record["available_tools"],
            )
        ],
        mcp_tools_called=calls,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.score and not args.model:
        parser.error("Scoring requires an explicitly approved model; no default model")
    records = [
        json.loads(line)
        for line in args.input.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not records:
        raise ValueError("No actual traces supplied; empty run is not a pass")
    cases = [build_case(r) for r in records]
    rows = []
    for record, case in zip(records, cases):
        row = {
            "test_id": record["test_id"],
            "status": "VALIDATED_NOT_SCORED",
            "schema_commit": record["schema_commit"],
            "runtime_version": record["runtime_version"],
        }
        if args.score:
            from deepeval.metrics import MCPUseMetric

            metric = MCPUseMetric(
                model=args.model,
                threshold=0.8,
                eval_mode="llm",
                async_mode=False,
                include_reason=True,
            )
            metric.measure(case)
            row.update(
                status="SCORED",
                score=metric.score,
                reason=metric.reason,
                judge_model=args.model,
                threshold=0.8,
                evaluation_cost_usd=str(metric.evaluation_cost),
            )
        rows.append(row)
    args.output.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "validated": len(rows),
                "scored": sum(r["status"] == "SCORED" for r in rows),
            }
        )
    )


if __name__ == "__main__":
    main()
