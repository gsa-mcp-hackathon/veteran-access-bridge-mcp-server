"""Failed experiment retained for reproducibility; execution is disabled.

IBM accepted is_async=False but execution failed with HTTP 424 fetching tool
details on 2026-11-17. The isolated flow was restored to asynchronous execution.
Do not use this as a supported deployment or latency fix.
"""

import json
import os
from pathlib import Path

from ibm_watsonx_orchestrate.agent_builder.tools.types import ToolSpec
from ibm_watsonx_orchestrate.client.tools.tool_client import ToolClient
from ibm_watsonx_orchestrate.client.utils import instantiate_client

NAME = "vab_latency_eval_options_flow"


def main():
    os.umask(0o077)
    root = Path("/tmp/vab-latency-eval-20261117")
    if not root.is_dir():
        raise RuntimeError("Existing isolated evaluation setup required")
    client = instantiate_client(ToolClient)
    matches = client.get_draft_by_name(NAME)
    if len(matches) != 1:
        raise RuntimeError("Expected one isolated flow")
    original = matches[0]
    if original["name"] != NAME or original["permission"] != "read_only":
        raise RuntimeError("Unexpected target or permission")
    registered = json.loads((root / "flow-tool-backup.json").read_text())
    if (
        original["id"] != registered["id"]
        or original.get("binding", {}).get("flow", {}).get("flow_id")
        != registered.get("binding", {}).get("flow", {}).get("flow_id")
    ):
        raise RuntimeError("Registered evaluation flow identity must match backup")
    backup = root / "flow-before-sync-private.json"
    if not backup.exists():
        backup.write_text(json.dumps(original))
    payload = ToolSpec.model_validate(original).model_dump(
        mode="json", exclude_none=True, by_alias=True
    )
    payload.pop("id", None)
    payload["is_async"] = False
    client.update(original["id"], payload)
    saved = client.get_draft_by_id(original["id"])
    if saved.get("is_async") is not False or saved.get("permission") != "read_only":
        raise RuntimeError("Synchronous read-only configuration not confirmed")
    print("Isolated flow configured synchronously; live Avery unchanged")


if __name__ == "__main__":
    raise SystemExit("Disabled: synchronous flow experiment failed runtime acceptance.")
