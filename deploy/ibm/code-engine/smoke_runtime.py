from __future__ import annotations

import argparse
import json
import sys

import httpx

from veteran_access_bridge.app.runtime_smoke import run_runtime_smoke


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--allow-fake", action="store_true")
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()

    with httpx.Client(
        base_url=args.url.rstrip("/"),
        timeout=args.timeout,
        follow_redirects=True,
    ) as client:
        report = run_runtime_smoke(
            client,
            require_remote=not args.allow_fake,
        )

    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
