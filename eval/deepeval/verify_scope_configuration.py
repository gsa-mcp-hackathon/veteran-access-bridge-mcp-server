"""Read-only acceptance checks for the existing IBM toolkit replacement.

Inputs are private CLI metadata exports, never credentials. This does not issue
session capabilities, change IBM configuration, or invoke model/tool endpoints.
"""

import argparse
import json
from pathlib import Path

import yaml

PREFIX = "veteran-access-mcp-remote-m64-canary:"


def verify(before_tools, after_tools, candidate, exported):
    before = {t["name"]: t for t in before_tools if t["name"].startswith(PREFIX)}
    after = {t["name"]: t for t in after_tools if t["name"].startswith(PREFIX)}
    if len(before) != 10 or set(before) != set(after):
        raise ValueError("Existing ten-tool selection was not preserved")
    scoped = 0
    for name, tool in after.items():
        properties = tool.get("input_schema", {}).get("properties", {})
        if "case_id" in properties:
            if properties.get("session_scope", {}).get("type") != "string":
                raise ValueError("Case tool is missing the session scope parameter")
            scoped += 1
        elif name != PREFIX + "get_scheduling_handoff":
            raise ValueError("Unexpected unscoped tool")
        old_binding = before[name].get("binding", {}).get("mcp", {})
        new_binding = tool.get("binding", {}).get("mcp", {})
        for key in ("server_url", "connections"):
            if old_binding.get(key) != new_binding.get(key):
                raise ValueError("Existing endpoint or connection binding changed")
    if scoped != 9:
        raise ValueError("Expected nine case-scoped tool schemas")
    if candidate.get("name") != "veteran_access_agent_m64":
        raise ValueError("Wrong agent candidate")
    for key in ("name", "llm", "tools", "instructions", "context_variables"):
        if candidate.get(key) != exported.get(key):
            raise ValueError("Exported agent differs from prepared candidate: " + key)
    if not {"vab_case_id", "vab_mcp_scope"} <= set(
        exported.get("context_variables", [])
    ):
        raise ValueError("Required application context variables missing")
    return {
        "selected_tools_preserved": 10,
        "case_tools_with_scope": scoped,
        "endpoint_and_connection_preserved": True,
        "agent_candidate_verified": True,
        "live_browser_acceptance": "NOT_RUN_BY_THIS_CHECK",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before-tools", "after-tools", "candidate-agent", "exported-agent"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = verify(
        json.loads(args.before_tools.read_text(encoding="utf-8")),
        json.loads(args.after_tools.read_text(encoding="utf-8")),
        yaml.safe_load(args.candidate_agent.read_text(encoding="utf-8")),
        yaml.safe_load(args.exported_agent.read_text(encoding="utf-8")),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
