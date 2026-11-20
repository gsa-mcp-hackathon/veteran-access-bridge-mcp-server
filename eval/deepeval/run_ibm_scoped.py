"""Evaluation-only compatibility shim for IBM v1 context variables.

The installed adapter sends runtime_context as context. The public RunOrchestrate
schema exposes agent variables separately as context_variables. Do not alter the
installed package, credentials, headers, endpoint, or application runtime.
"""

import copy

AGENT_ID = "b38da637-92e4-4c5c-9c7e-d4f8dce28160"


def scoped_payload(payload, path):
    if path != "/v1/orchestrate/runs?stream=true":
        return payload
    if payload.get("agent_id") != AGENT_ID:
        return payload
    context = payload.get("context")
    if not isinstance(context, dict) or "vab_case_id" not in context:
        return payload
    if set(context) != {"vab_case_id"} or "context_variables" in payload:
        raise ValueError("Ambiguous evaluation context")
    case = context["vab_case_id"]
    if case not in {"DEMO-CARD-5000335-001", "DEMO-PC-VOICE-INTAKE-001"}:
        raise ValueError("Unapproved evaluation case")
    result = copy.deepcopy(payload)
    result["context_variables"] = result.pop("context")
    return result


def main():
    import sys

    from agentops.wxo_client import WXOClient
    from ibm_watsonx_orchestrate.cli.main import app

    if sys.argv[1:3] != ["evaluations", "evaluate"]:
        raise SystemExit("This launcher supports evaluations evaluate only")
    original = WXOClient.post

    def post(self, payload, path, *args, **kwargs):
        mapped = scoped_payload(payload, path)
        if mapped is not payload:
            print("[VAB EVAL] Forwarded approved case as context_variables", flush=True)
        return original(self, mapped, path, *args, **kwargs)

    WXOClient.post = post
    try:
        app()
    finally:
        WXOClient.post = original


if __name__ == "__main__":
    main()
