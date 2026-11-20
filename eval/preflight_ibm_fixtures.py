"""Read-only fixture checks on the existing IBM canary; never print credentials."""

import asyncio
import json
import subprocess
from pathlib import Path

from fastmcp import Client


async def main():
    base = "https://veteran-access-bridge-m64-canary.2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"
    secret = json.loads(
        subprocess.check_output(
            [
                "ibmcloud",
                "ce",
                "secret",
                "get",
                "-n",
                "veteran-access-mcp-key",
                "-o",
                "json",
            ],
            stderr=subprocess.DEVNULL,
        )
    )
    key = secret["data"]["VAB_MCP_API_KEY"]
    rows = []
    async with Client(base + "/mcp/", auth=key) as client:
        registry = await client.list_tools()
        for scenario in ["A02", "A03", "A11"]:
            data = json.loads(
                Path(f"eval/watsonx/current_release_smoke/{scenario}.json").read_text()
            )
            for step in data["goal_details"]:
                if step["type"] != "tool_call":
                    continue
                result = await client.call_tool(
                    step["tool_name"], step["args"], raise_on_error=False
                )
                rows.append(
                    {
                        "scenario": scenario,
                        "tool": step["tool_name"],
                        "is_error": result.is_error,
                        "data": result.data,
                    }
                )
    out = Path("eval/results/ibm-preflight")
    out.mkdir(parents=True, exist_ok=True)
    (out / "fixture-results.json").write_text(json.dumps(rows, indent=2, default=str))
    (out / "registry.json").write_text(
        json.dumps([t.model_dump(mode="json") for t in registry], indent=2)
    )
    print(
        json.dumps(
            {
                "tool_count": len(registry),
                "checks": len(rows),
                "errors": sum(r["is_error"] for r in rows),
            }
        )
    )
    for row in rows:
        data = row["data"] if isinstance(row["data"], dict) else {}
        print(
            json.dumps(
                {
                    "scenario": row["scenario"],
                    "tool": row["tool"],
                    "is_error": row["is_error"],
                    "summary": {
                        k: data[k]
                        for k in ("verified", "found", "case_id", "status")
                        if k in data
                    },
                }
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
