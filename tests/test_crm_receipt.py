from uuid import uuid4

import pytest

from veteran_access_bridge.app import asgi
from veteran_access_bridge.mcp.crm_receipt import safe_crm_receipt


def receipt():
    return dict(
        persisted=True,
        synthetic=True,
        booking_created=False,
        operation="record_crm_interaction",
        case_id="case-A",
        interaction_id="call-A",
        record_id=str(uuid4()),
        version=1,
        actor="AVERY",
        replayed=False,
        summary="private note",
    )


@pytest.mark.parametrize(
    "change",
    [
        {"persisted": False},
        {"synthetic": False},
        {"booking_created": True},
        {"case_id": "case-B"},
        {"interaction_id": "call-B"},
        {"version": True},
        {"version": 0},
        {"record_id": "not-a-uuid"},
        {"operation": "get_crm_case"},
        {"actor": "caller"},
    ],
)
def test_rejects_unverified_or_mismatched_receipts(change):
    assert (
        safe_crm_receipt(
            receipt() | change,
            tool="record_crm_interaction",
            case_id="case-A",
            interaction_id="call-A",
        )
        is None
    )


@pytest.mark.parametrize("source", ["application", "watsonx_orchestrate"])
def test_monitor_projects_only_server_receipt_without_content(monkeypatch, source):
    raw = dict(
        event_type="mcp_tool_result",
        source=source,
        interaction_id="call-A",
        payload=dict(
            tool_name="record_crm_interaction",
            tool_call_id="tool-1",
            status="succeeded",
            evidence="server_scope_receipt",
            scope_verified=True,
            invoked_by="agent",
            verified_case_id="case-A",
            voice_session_id="voice-A",
            crm_receipt=receipt(),
        ),
    )
    monkeypatch.setattr(asgi, "event_to_dict", lambda _: raw)
    payload = asgi._msa_monitor_event(object())["payload"]
    assert ("crm_receipt" in payload) == (source == "application")
    assert "private note" not in str(payload)
    if source == "application":
        assert payload["crm_receipt"]["booking_created"] is False
        assert payload["voice_session_id"] == "voice-A"
