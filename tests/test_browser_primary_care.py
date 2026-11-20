import json
import time
from types import SimpleNamespace

import pytest

from veteran_access_bridge.app.browser_primary_care import (
    INTAKE_CASE,
    read_intake_via_mcp,
)
from veteran_access_bridge.mcp.session_scope import SessionScope, trusted_turn


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "issuer",
    [
        "http://example.com",
        "https://user@example.com",
        "https://example.com/path",
        "https://example.com?token=x",
    ],
)
async def test_mcp_requires_pinned_secure_origin(issuer):
    with pytest.raises(PermissionError):
        await read_intake_via_mcp(issuer, "test-key")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", [{}, {"case_id": "other"}, {"synthetic": False}, {"read_only": False}]
)
async def test_mcp_response_scope_is_checked(monkeypatch, change):
    payload = {"case_id": INTAKE_CASE, "synthetic": True, "read_only": True} | change
    calls = []

    class Client:
        def __init__(self, url, auth):
            assert url == "https://example.com/mcp" and auth == "test-key"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])

    monkeypatch.setattr("fastmcp.Client", Client)
    with trusted_turn(
        SessionScope(INTAKE_CASE), expires=time.monotonic() + 30, host_intake=True
    ) as token:
        if change:
            with pytest.raises(PermissionError):
                await read_intake_via_mcp("https://example.com", "test-key")
        else:
            assert (
                await read_intake_via_mcp("https://example.com", "test-key") == payload
            )
    assert calls == [
        ("get_scheduling_encounter", {"case_id": INTAKE_CASE, "session_scope": token})
    ]
