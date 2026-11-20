"""Prepare a reversible instruction-only overlay on an exported agent."""

import argparse
import hashlib
import json
from pathlib import Path

import yaml

MARKER = "Response evidence rules — revision 2"


def prepare(before, rules):
    if before.get("name") != "veteran_access_agent_m64":
        raise ValueError("Wrong target agent")
    instructions = before.get("instructions")
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("Missing existing instructions")
    if MARKER in instructions:
        raise ValueError("Revision already present; do not duplicate")
    if not rules.startswith(MARKER):
        raise ValueError("Unexpected response rules")
    after = dict(before)
    after["instructions"] = (
        rules.strip() + "\n\nExisting instructions:\n" + instructions
    )
    assert {k: v for k, v in before.items() if k != "instructions"} == {
        k: v for k, v in after.items() if k != "instructions"
    }
    return after


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raw = args.before.read_bytes()
    before = yaml.safe_load(raw)
    after = prepare(before, args.rules.read_text(encoding="utf-8"))
    if args.output.exists():
        raise ValueError("Refusing to overwrite prepared evidence")
    args.output.write_text(yaml.safe_dump(after, sort_keys=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "changed_fields": ["instructions"],
                "tools_preserved": len(after.get("tools", [])),
                "before_sha256": hashlib.sha256(raw).hexdigest(),
                "candidate_sha256": hashlib.sha256(
                    args.output.read_bytes()
                ).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
