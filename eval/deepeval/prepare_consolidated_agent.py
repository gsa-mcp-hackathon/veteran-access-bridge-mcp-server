"""Prepare a reviewable agent candidate without contacting IBM."""

import argparse
import copy
import json
from pathlib import Path

import yaml
from verify_consolidated_configuration import ALLOWED, CATALOG


def prepare(before, rules, prefix):
    if before.get("name") != "veteran_access_agent_m64" or not prefix.endswith(":"):
        raise ValueError("Wrong agent or toolkit prefix")
    old_tools = before.get("tools", [])
    allowed_prefixes = (
        "veteran-access-mcp-remote-m64-canary:",
        "veteran-access-mcp-va-readonly-m64:",
    )
    # Fresh November 15 export also contained these five reviewed bindings.
    # KB imports remain backed up, but are outside the scoped canary catalog.
    reviewed_extras = {
        "veteran-access-mcp-unified-candidate:" + name
        for name in (
            "search_kb_articles",
            "get_kb_article",
            "get_kb_policy_references",
            "get_kb_evidence",
        )
    } | {"veteran-access-mcp-m64-ccg-canary:check_community_care_eligibility"}
    if not old_tools or any(
        t not in reviewed_extras
        and (not t.startswith(allowed_prefixes) or t.split(":", 1)[1] not in CATALOG)
        for t in old_tools
    ):
        raise ValueError("Unexpected existing tools; review before replacement")
    if "revision 5" not in rules or not all(
        x in rules for x in ("{vab_case_id}", "{vab_mcp_scope}")
    ):
        raise ValueError("Expected reviewed consolidated rules")
    after = copy.deepcopy(before)
    after["tools"] = sorted(prefix + t for t in ALLOWED)
    after["instructions"] = rules.strip()
    # Replace conflicting legacy guidelines with one authoritative policy.
    # Identity, clinical escalation and voice guidance are retained in that policy.
    after["guidelines"] = []
    after["context_variables"] = list(before.get("context_variables") or [])
    for name in ("vab_case_id", "vab_mcp_scope"):
        if name not in after["context_variables"]:
            after["context_variables"].append(name)
    permitted = {"tools", "instructions", "guidelines", "context_variables"}
    changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
    if not changed <= permitted:
        raise ValueError("Unexpected unrelated configuration change")
    return after, {
        "changed_fields": sorted(changed),
        "old_tools": len(old_tools),
        "new_tools": len(after["tools"]),
        "retired_out_of_catalog_bindings": sorted(
            t for t in old_tools if t.split(":", 1)[1] not in CATALOG
        ),
        "legacy_guidelines_replaced": len(before.get("guidelines") or []),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "rules", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()
    after, summary = prepare(
        yaml.safe_load(args.before.read_text()),
        args.rules.read_text(encoding="utf-8"),
        args.prefix,
    )
    with args.output.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(after, stream, sort_keys=False, allow_unicode=True)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
