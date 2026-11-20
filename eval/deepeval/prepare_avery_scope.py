"""Correct guideline links to already-assigned tools and specify case context."""

import argparse
import copy
import json
from pathlib import Path

import yaml


def prepare(before, rules):
    if before.get("name") != "veteran_access_agent_m64":
        raise ValueError("Wrong agent")
    if "Case routing evidence — revision 3" in before["instructions"]:
        raise ValueError("Already patched")
    after = copy.deepcopy(before)
    assigned = set(before["tools"])
    changes = []
    for guideline in after.get("guidelines", []):
        old = guideline.get("tool")
        if not old or old in assigned:
            continue
        prefix, name = old.split(":", 1)
        target = "veteran-access-mcp-remote-m64-canary:" + name
        if prefix != "veteran-access-mcp-unified-candidate" or target not in assigned:
            raise ValueError(f"Cannot repair unassigned guideline: {old}")
        guideline["tool"] = target
        changes.append({"from": old, "to": target})
    for guideline in after.get("guidelines", []):
        if guideline.get("display_name") == "Veteran chooses an option":
            guideline["condition"] = (
                "Verified caller identifies a newly presented option and no "
                "current approved selection has reached VERIFIED_BOOKABLE."
            )
        if guideline.get("display_name") == "Confirmation request":
            guideline["condition"] = (
                "An existing current approved selection has already reached "
                "VERIFIED_BOOKABLE, the caller is not changing options, and "
                "a Veteran confirmation must be requested."
            )
    after["context_variables"] = list(before.get("context_variables") or [])
    if "vab_case_id" not in after["context_variables"]:
        after["context_variables"].append("vab_case_id")
    after["instructions"] = rules.strip() + "\n\n" + before["instructions"]
    allowed = {"instructions", "guidelines", "context_variables"}
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    if not changed <= allowed or after["tools"] != before["tools"]:
        raise ValueError("Unexpected configuration change")
    return after, changes


def main():
    p = argparse.ArgumentParser()
    for name in ("before", "rules", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError("Output already exists")
    after, changes = prepare(
        yaml.safe_load(args.before.read_text()), args.rules.read_text(encoding="utf-8")
    )
    args.output.write_text(yaml.safe_dump(after, sort_keys=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "guideline_links_repaired": len(changes),
                "tools_unchanged": len(after["tools"]),
                "changes": changes,
            }
        )
    )


if __name__ == "__main__":
    main()
