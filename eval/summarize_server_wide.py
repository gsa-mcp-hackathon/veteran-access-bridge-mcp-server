"""Build a conservative per-tool matrix from recorded evidence, never guesses."""

import csv
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/evaluation/evidence/server-wide-20261116"
scope = json.loads((OUT / "scope-matrix.json").read_text())
contracts = json.loads((OUT / "contracts-final/mcp-probes.json").read_text())
arguments = json.loads((OUT / "arguments-all/adversarial-arguments.json").read_text())


def status(rows):
    if not rows:
        return "NOT TESTED"
    passed = sum(r["passed"] for r in rows)
    return f"{'PASS' if passed == len(rows) else 'FAIL'} {passed}/{len(rows)}"


rows = []
for tool in scope["inventory"]:
    name = tool["name"]
    cases = [r for r in scope["cases"] if r["tool"] == name]
    has_case = "case_id" in tool["inputSchema"]["properties"]
    gated = [
        r for r in cases if r["test"].endswith("scope") or r["test"] == "foreign_case"
    ]
    replay = [r for r in cases if r["test"] == "concurrent_gate_replay"]
    swaps = [r for r in cases if r["test"] == "two_session_case_swap"]
    rows.append(
        {
            "tool": name,
            "read_only_hint": tool["annotations"]["readOnlyHint"],
            "contracts_local": status(
                [r for r in contracts["cases"] if r["tool"] == name]
            ),
            "hostile_arguments_local": status(
                [r for r in arguments["cases"] if r["tool"] == name]
            ),
            "required_field_rejection": status(
                [r for r in cases if r["test"] in ("missing_field", "wrong_type")]
            ),
            "remote_scope_denials": status(gated)
            if has_case
            else (
                "N/A public facility lookup"
                if name != "get_scheduling_handoff"
                else "N/A handoff remote access denied separately"
            ),
            "safe_remote_response": status(
                [r for r in cases if r["test"] == "safe_remote_response"]
            )
            if not has_case
            else "N/A use scoped denial column",
            "concurrent_gate_replay": status(replay)
            if replay
            else "NOT TESTED (identity/restricted/public path)",
            "two_session_case_swap": status(swaps)
            if swaps
            else ("NOT TESTED" if has_case else "N/A no case input"),
            "positive_journey_this_run": "NOT TESTED; see prior evidence separately",
            "agent_tool_result_injection": "NOT TESTED",
            "real_database_concurrency": "NOT TESTED"
            if not tool["annotations"]["readOnlyHint"]
            else "N/A read-only tool; concurrent isolation remains relevant",
        }
    )

with (OUT / "tool-coverage.csv").open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

suite = ElementTree.parse(OUT / "regression-final.xml").getroot().find("testsuite")
summary = {
    "source_commit": scope["source_commit"],
    "tools": len(rows),
    "contracts": status(contracts["cases"]),
    "arguments": status(arguments["cases"]),
    "schema_and_scope": status(scope["cases"]),
    "windows_regression": dict(suite.attrib),
    "warning": "Overlapping checks, not independent journeys. No combined pass rate.",
    "runner_sha256": hashlib.sha256(
        (ROOT / "eval/probe_server_wide.py").read_bytes()
    ).hexdigest(),
}
(OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
lines = [
    "# Coverage of all 25 registered MCP tools",
    "",
    "November 16, 2026. Fresh local checks; **evaluation remains partial**.",
    "",
    "Full matrix: [CSV](evidence/server-wide-20261116/tool-coverage.csv). "
    "Counts overlap and must not be combined into a security percentage.",
    "",
    "| Tool | Local contracts | Hostile arguments | Remote scope denial |",
    "|---|---|---|---|",
]
for row in rows:
    lines.append(
        f"| `{row['tool']}` | {row['contracts_local']} | "
        f"{row['hostile_arguments_local']} | {row['remote_scope_denials']} |"
    )
lines.extend(
    [
        "",
        "## How to read the matrix",
        "",
        "PASS means the listed bounded assertions passed. NOT TESTED is a gap, "
        "not a failure or a pass. N/A includes a specific scope reason. "
        "Contract checks include metadata and safe rejection, not a successful "
        "business journey for each tool. The CSV separately identifies concurrency "
        "at the shared permission gate and true database concurrency.",
        "",
        "The 261 checks include 26 gate-sentinel checks across 13 read/CRM tools. "
        "These prove invocation denial/replay behavior in process; they do not "
        "prove database locking, recovery after restart, or agent resistance to "
        "malicious tool output.",
        "",
        "Prior agent-selected read and CRM acceptance evidence remains dated "
        "separately; it was not rerun here. No new appointment was created.",
    ]
)
(ROOT / "docs/evaluation/server-wide-tool-coverage-20261116.md").write_text(
    "\n".join(lines) + "\n", encoding="utf-8"
)
print(json.dumps(summary, indent=2))
