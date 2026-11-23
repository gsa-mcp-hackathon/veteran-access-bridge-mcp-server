"""Offline 25-tool scope coverage. No listener, database, or model calls.

Real registered wrappers are exercised in remote-gate mode over FastMCP's
in-process client. Separate gate concurrency tests use an invocation sentinel;
they do not establish database concurrency or model injection resistance.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ["VAB_ENABLE_CRM"] = "true"
os.environ["VAB_SCHEDULING_RUNTIME_MODE"] = "demo"
os.environ["VAB_VA_SANDBOX_SOURCE_MODE"] = "unavailable"

from fastmcp import Client
from probe_mcp_contracts import snapshot

from veteran_access_bridge.mcp import session_scope as scope
from veteran_access_bridge.mcp.app import mcp


def value(schema):
    if "enum" in schema:
        return schema["enum"][0]
    if schema.get("type") == "integer":
        return 1
    if schema.get("type") == "boolean":
        return False
    return "EVAL-UNKNOWN"


async def run(out):
    rows = []
    with patch.object(scope, "remote_request", return_value=True):
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 25, "Inventory changed; review coverage first"
            for tool in tools:
                props = tool.inputSchema["properties"]
                args = {
                    key: value(props[key])
                    for key in tool.inputSchema.get("required", [])
                }
                if "case_id" in props:
                    args["case_id"] = "EVAL-CASE-A"
                for key in tool.inputSchema.get("required", []):
                    for kind, supplied in (
                        ("missing_field", {k: v for k, v in args.items() if k != key}),
                        ("wrong_type", {**args, key: {"unexpected": True}}),
                    ):
                        before = snapshot()
                        result = await client.call_tool(
                            tool.name, supplied, raise_on_error=False
                        )
                        rows.append(
                            dict(
                                tool=tool.name,
                                test=kind,
                                field=key,
                                passed=result.is_error and before == snapshot(),
                                layer="registered_wrapper",
                            )
                        )
                if "case_id" not in props:
                    result = await client.call_tool(
                        tool.name, args, raise_on_error=False
                    )
                    expected = (
                        result.is_error
                        if tool.name == "get_scheduling_handoff"
                        else isinstance(result.data, dict)
                        and result.data.get("status") == "UNAVAILABLE"
                        and result.data.get("booking_created") is False
                    )
                    rows.append(
                        dict(
                            tool=tool.name,
                            test="safe_remote_response",
                            passed=bool(expected),
                            layer="registered_wrapper",
                        )
                    )
                    continue
                for kind in (
                    "missing_scope",
                    "forged_scope",
                    "foreign_case",
                    "expired_scope",
                    "revoked_scope",
                ):
                    state = scope.SessionScope(
                        "EVAL-CASE-A",
                        matched_case="EVAL-CASE-A",
                        interaction_id="EVAL-CALL-A",
                    )
                    # Identity uses an unverified scope; foreign case still must fail.
                    if tool.name == "verify_synthetic_identity":
                        state.matched_case = None
                    with scope.trusted_turn(
                        state, expires=time.monotonic() + 30, crm_enabled=True
                    ) as token:
                        supplied = {**args, "session_scope": token}
                        if kind == "missing_scope":
                            supplied.pop("session_scope")
                        elif kind == "forged_scope":
                            supplied["session_scope"] = "vab_scope_EVAL_FORGED"
                        elif kind == "foreign_case":
                            supplied["case_id"] = "EVAL-CASE-B"
                        elif kind == "expired_scope":
                            scope._grants[scope._key(token)].expires = (
                                time.monotonic() - 1
                            )
                        elif kind == "revoked_scope":
                            state.halted = True
                        before = snapshot()
                        result = await client.call_tool(
                            tool.name, supplied, raise_on_error=False
                        )
                        rows.append(
                            dict(
                                tool=tool.name,
                                test=kind,
                                passed=result.is_error and before == snapshot(),
                                layer="registered_wrapper",
                            )
                        )

    # Test the actual shared gate with simultaneous synthetic caller scopes.
    for name in sorted(scope.READ_TOOLS | scope.CRM_TOOLS):
        calls = []

        async def action():
            calls.append("A")
            await asyncio.sleep(0)
            return {}

        state = scope.SessionScope("A", matched_case="A", interaction_id="call-A")
        with scope.trusted_turn(
            state, expires=time.monotonic() + 30, crm_enabled=True
        ) as token:
            results = await asyncio.gather(
                *[scope.scoped_call(token, name, "A", action) for _ in range(2)],
                return_exceptions=True,
            )
            rows.append(
                dict(
                    tool=name,
                    test="concurrent_gate_replay",
                    passed=len(calls) == 1
                    and sum(isinstance(r, PermissionError) for r in results) == 1,
                    layer="scope_gate_sentinel_not_database",
                )
            )
        calls.clear()
        with scope.trusted_turn(
            state, expires=time.monotonic() + 30, crm_enabled=True
        ) as token_a:
            state_b = scope.SessionScope("B", matched_case="B", interaction_id="call-B")
            with scope.trusted_turn(
                state_b, expires=time.monotonic() + 30, crm_enabled=True
            ) as token_b:
                results = await asyncio.gather(
                    scope.scoped_call(token_a, name, "B", action),
                    scope.scoped_call(token_b, name, "A", action),
                    return_exceptions=True,
                )
                rows.append(
                    dict(
                        tool=name,
                        test="two_session_case_swap",
                        passed=not calls
                        and all(isinstance(r, PermissionError) for r in results),
                        layer="scope_gate_sentinel_not_database",
                    )
                )
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip(),
        "scope": "Local source; CRM enabled; no network, model or database acceptance",
        "limitations": [
            "Schema failures can precede authorization failures",
            "Gate replay uses a sentinel, not real database writes",
            "No successful workflow or agent-injection score implied",
        ],
        "tool_count": len(tools),
        "inventory": [t.model_dump(mode="json") for t in tools],
        "cases": rows,
    }
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    failures = [r for r in rows if not r["passed"]]
    print(
        json.dumps(
            {
                "tools": len(tools),
                "checks": len(rows),
                "passed": len(rows) - len(failures),
                "failed": failures,
            }
        )
    )
    return bool(failures)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite evidence")
    raise SystemExit(asyncio.run(run(args.output)))
