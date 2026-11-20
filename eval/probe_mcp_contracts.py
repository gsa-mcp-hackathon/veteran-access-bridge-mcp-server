"""Bounded probes of the existing MCP server in process; no network or DB writes.

These measure schema/denial contracts, not agent tool selection or full functional
coverage. Fixture-mode observations and durable-mode denials are kept separate.
"""

import argparse
import asyncio
import copy
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# A reused Codespace interpreter may be editable-installed from another checkout.
# These probes explicitly evaluate this checkout's source, never that other tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastmcp import Client

from veteran_access_bridge.mcp import state
from veteran_access_bridge.mcp.app import mcp

OUT = Path("eval/results/20261114-baseline")
CASE = "DEMO-CARD-5000335-001"


def snapshot():
    return copy.deepcopy(
        {
            k: vars(v)
            for k, v in vars(state).items()
            if k.endswith("_store") and hasattr(v, "__dict__")
        }
    )


def denied(result):
    if result.is_error:
        return True
    data = result.data
    return isinstance(data, dict) and (
        data.get("verified") is False
        or data.get("found") is False
        or data.get("status") == "UNAVAILABLE"
        or data.get("valid") is False
        or data.get("booking_ready") is False
        or data.get("passed") is False
    )


async def main():
    os.environ["VAB_SCHEDULING_RUNTIME_MODE"] = "demo"
    os.environ["VAB_VA_SANDBOX_SOURCE_MODE"] = "unavailable"
    rows = []
    async with Client(mcp) as client:
        tools = await client.list_tools()
        for tool in tools:
            props = tool.inputSchema["properties"]
            required = tool.inputSchema.get("required", [])
            args = {k: props[k].get("enum", ["EVAL-UNKNOWN"])[0] for k in required}
            rows.append(
                {
                    "tool": tool.name,
                    "category": "metadata",
                    "passed": bool(
                        tool.description
                        and props
                        and required
                        and tool.annotations is not None
                    ),
                    "scope": "local_registry",
                }
            )
            for kind, supplied in [
                ("missing_required", {}),
                ("wrong_type", {**args, required[0]: {"unexpected": True}}),
                ("unknown_reference", args),
            ]:
                before = snapshot()
                start = time.perf_counter()
                result = await client.call_tool(
                    tool.name, supplied, raise_on_error=False
                )
                rows.append(
                    {
                        "tool": tool.name,
                        "category": kind,
                        "scope": "local_fixture_mode",
                        "input": supplied,
                        "passed": denied(result) and before == snapshot(),
                        "state_unchanged": before == snapshot(),
                        "is_error": result.is_error,
                        "response": result.data,
                        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                    }
                )
            if tool.annotations and not tool.annotations.readOnlyHint:
                os.environ["VAB_SCHEDULING_RUNTIME_MODE"] = "supabase_test"
                before = snapshot()
                result = await client.call_tool(
                    tool.name, {**args, "case_id": CASE}, raise_on_error=False
                )
                rows.append(
                    {
                        "tool": tool.name,
                        "category": "durable_public_write_denied",
                        "scope": "local_durable_mode_no_connection",
                        "passed": result.is_error and before == snapshot(),
                        "state_unchanged": before == snapshot(),
                    }
                )
                os.environ["VAB_SCHEDULING_RUNTIME_MODE"] = "demo"

        timing = []
        for name in [
            "get_scheduling_encounter",
            "assess_access_standard",
            "determine_workflow_state",
            "search_availability",
            "check_community_care_eligibility",
            "get_case_lifecycle_state",
        ]:
            for repeat in range(20):
                start = time.perf_counter()
                result = await client.call_tool(
                    name, {"case_id": CASE}, raise_on_error=False
                )
                timing.append(
                    {
                        "tool": name,
                        "repeat": repeat,
                        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
                        "is_error": result.is_error,
                    }
                )
        OUT.joinpath("local-tool-timing.json").write_text(
            json.dumps(
                {
                    "scope": "in_process_fixture_mode_not_deployed_network_latency",
                    "samples": timing,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    OUT.joinpath("mcp-probes.json").write_text(
        json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tool_count": len(tools),
                "cases": rows,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "probes": len(rows),
                "passed": sum(r["passed"] for r in rows),
                "failed": [
                    {"tool": r["tool"], "category": r["category"]}
                    for r in rows
                    if not r["passed"]
                ],
                "timing_samples": len(timing),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    OUT = parser.parse_args().output_dir
    OUT.mkdir(parents=True, exist_ok=False)
    asyncio.run(main())
    evidence = json.loads(OUT.joinpath("mcp-probes.json").read_text(encoding="utf-8"))
    if not evidence["cases"] or any(not row["passed"] for row in evidence["cases"]):
        raise SystemExit(1)
