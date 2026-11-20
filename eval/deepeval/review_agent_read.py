"""Require IBM selections paired with server-authorized, same-case receipts."""

import argparse
import hashlib
import json
from pathlib import Path


def review(evidence, *, expected_case):
    events = evidence.get("activity", {}).get("events", [])
    calls = {}
    for event in events:
        if event.get("event_type") != "mcp_tool_called":
            continue
        payload = event.get("payload", {})
        if event.get("source") != "watsonx_orchestrate":
            raise ValueError(
                "Host-selected calls cannot prove independent agent selection"
            )
        call_id = payload.get("tool_call_id")
        if not call_id or call_id in calls:
            raise ValueError("Missing or duplicated agent call ID")
        calls[call_id] = payload.get("tool_name")
    receipts = []
    for event in events:
        payload = event.get("payload", {})
        if payload.get("evidence") != "server_scope_receipt":
            continue
        if (
            event.get("event_type") != "mcp_tool_result"
            or event.get("source") != "application"
            or payload.get("invoked_by") != "agent"
            or payload.get("scope_verified") is not True
            or payload.get("status") != "succeeded"
            or payload.get("verified_case_id") != expected_case
            or calls.get(payload.get("tool_call_id")) != payload.get("tool_name")
        ):
            raise ValueError("Unverified or cross-case execution receipt")
        receipts.append(payload)
    ids = [r["tool_call_id"] for r in receipts]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicated execution receipt")
    identity = [r for r in receipts if r["tool_name"] == "verify_synthetic_identity"]
    reads = [r for r in receipts if r["tool_name"] == "get_scheduling_encounter"]
    if len(identity) != 1 or identity[0].get("verified") is not True or not reads:
        raise ValueError("Successful identity and case-scoped read evidence required")
    if list(calls.values()).count("verify_synthetic_identity") != 1:
        raise ValueError("Unexpected repeated identity attempt")
    if receipts.index(identity[0]) > receipts.index(reads[0]):
        raise ValueError("Read receipt precedes identity receipt")
    if any(e.get("event_type") == "simulated_booking_recorded" for e in events):
        raise ValueError("This acceptance scenario must remain read-only")
    return {
        "result": "PASS",
        "verified_case_id": expected_case,
        "identity_calls": 1,
        "verified_agent_reads": len(reads),
        "followup_read_verified": len(reads) >= 2,
        "voice_session_id": evidence["voice_session_id"],
        "interaction_id": evidence["interaction_id"],
        "read_call_ids": [r["tool_call_id"] for r in reads],
        "scope": "IBM-selected, server-authorized synthetic reads only",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review(json.loads(args.evidence.read_text()), expected_case=args.case)
    result["evidence_sha256"] = hashlib.sha256(args.evidence.read_bytes()).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
