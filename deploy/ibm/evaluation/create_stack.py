"""Create only the approved, separately named evaluation applications.

Run in the authenticated Codespace. Credentials remain in private temporary
files and Code Engine secrets, never command arguments or stdout. Never updates
an existing app/secret. The state directory is intentionally retained for audit.
"""

import argparse
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

SOURCES = {
    "api": "veteran-access-bridge-m64-canary",
    "worker": "vab-avery-voice-worker",
    "ui": "vab-avery-callcenter",
}
DOMAIN = "2fmg3lakuuzb.ca-tor.codeengine.appdomain.cloud"
ROOT = Path("/tmp/vab-latency-eval-20261117")


def ce(*args, as_json=True):
    result = subprocess.run(
        ["ibmcloud", "ce", *args], capture_output=True, text=True, timeout=90
    )
    if result.returncode:
        raise RuntimeError(
            f"IBM operation failed: {args[0]} {args[1]}; output suppressed"
        )
    return json.loads(result.stdout) if as_json else result.stdout


def effective_environment(app):
    container = app["spec"]["template"]["spec"]["containers"][0]
    values = {}
    for reference in container.get("envFrom", []):
        if set(reference) != {"secretRef"}:
            raise ValueError("Unexpected source configuration reference")
        values.update(
            ce("secret", "get", "-n", reference["secretRef"]["name"], "-o", "json")[
                "data"
            ]
        )
    for entry in container.get("env", []):
        if entry["name"].startswith("CE_"):
            continue
        if "value" not in entry:
            raise ValueError("Explicit secret-key references require review")
        values[entry["name"]] = entry["value"]
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", choices=tuple(SOURCES), required=True)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    prefixes = {
        "api": "veteran-access-bridge:sha-",
        "worker": "veteran-access-bridge:avery-worker-",
        "ui": "veteran-appointment-bridge:avery-callcenter-",
    }
    if not re.fullmatch(
        re.escape("ghcr.io/wbgreen0405/" + prefixes[args.component]) + r"[0-9a-f]{40}",
        args.image,
    ):
        raise ValueError("Immutable experiment image required")
    os.umask(0o077)
    ROOT.mkdir(mode=0o700, exist_ok=True)
    os.chmod(ROOT, 0o700)
    state_path = ROOT / "keys.json"
    if not state_path.exists():
        state_path.write_text(
            json.dumps(
                {
                    name: secrets.token_hex(32)
                    for name in ("mcp", "worker", "activity", "operator", "reviewer")
                }
            )
        )
    keys = json.loads(state_path.read_text())
    target = "vab-latency-eval-" + args.component
    secret = target + "-config"
    inventory = ce("app", "list", "-o", "json")
    items = inventory.get("items", []) if isinstance(inventory, dict) else inventory
    if any(item["metadata"]["name"] == target for item in items):
        raise RuntimeError("Target already exists; inspect rather than overwrite")
    source = ce("app", "get", "-n", SOURCES[args.component], "-o", "json")
    (ROOT / (args.component + "-source.json")).write_text(json.dumps(source))
    values = effective_environment(source)
    api = f"https://vab-latency-eval-api.{DOMAIN}"
    ui = f"https://vab-latency-eval-ui.{DOMAIN}"
    for key, value in list(values.items()):
        if isinstance(value, str) and value.startswith("https://"):
            values[key] = value.replace(
                f"https://{SOURCES['api']}.{DOMAIN}", api
            ).replace(f"https://{SOURCES['ui']}.{DOMAIN}", ui)
    if args.component == "api":
        values.update(
            VAB_VOICE_AGENT_NAME="vab-avery-latency-eval",
            VAB_EVAL_READ_ONLY="true",
            VAB_MCP_API_KEY=keys["mcp"],
            VAB_VOICE_WORKER_SECRET=keys["worker"],
            VAB_CALL_ACTIVITY_SERVICE_KEY=keys["activity"],
            ORCHESTRATE_AGENT_ID="vab_latency_eval_agent_pending",
        )
    elif args.component == "worker":
        values.update(
            VAB_VOICE_AGENT_NAME="vab-avery-latency-eval",
            VAB_VOICE_BACKEND_URL=api,
            VAB_VOICE_WORKER_SECRET=keys["worker"],
            VAB_ENABLE_LATENCY_PROBE="true",
        )
    else:
        values.update(
            VAB_API_BASE_URL=api,
            VAB_MSA_MONITOR_SERVICE_KEY=keys["mcp"],
            VAB_CALL_ACTIVITY_SERVICE_KEY=keys["activity"],
            VAB_MSA_OPERATOR_ACCESS_CODE=keys["operator"],
            VAB_REVIEWER_ACCESS_CODE=keys["reviewer"],
        )
    files = ROOT / args.component
    files.mkdir(mode=0o700, exist_ok=True)
    command = ["secret", "create", "-n", secret]
    for index, (key, value) in enumerate(values.items()):
        path = files / str(index)
        path.write_text(value)
        command.extend(["--from-file", f"{key}={path}"])
    ce(*command, as_json=False)
    command = [
        "app",
        "create",
        "-n",
        target,
        "--image",
        args.image,
        "--registry-secret",
        "ghcr-veteran-access",
        "--env-from-secret",
        secret,
        "--cpu",
        "1",
        "--memory",
        "4G" if args.component == "api" else "2G",
        "--min-scale",
        "1",
        "--max-scale",
        "1",
        "--port",
        "8081" if args.component == "worker" else "8080",
        "--visibility",
        "project" if args.component == "worker" else "public",
        "--no-wait",
    ]
    if args.component == "api":
        command.extend(["--mount-secret", "/app/supabase-ca=vab-pr205-supabase-ca"])
    ce(*command, as_json=False)
    unchanged = (
        ce("app", "get", "-n", SOURCES[args.component], "-o", "json")["spec"]
        == source["spec"]
    )
    print(
        json.dumps({"created": target, "secret": secret, "source_untouched": unchanged})
    )
    if not unchanged:
        raise RuntimeError("Source configuration changed concurrently; stop for review")


if __name__ == "__main__":
    main()
