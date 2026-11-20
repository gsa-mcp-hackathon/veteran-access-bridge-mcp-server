"""End-to-end regression test for remote MCP over the unified ASGI app."""

from __future__ import annotations

import importlib
import os
import unittest

import pytest
from fastmcp import Client, FastMCP
from starlette.testclient import TestClient

from veteran_access_bridge.mcp.tools import (
    get_scheduling_encounter,
    record_option_selection,
    record_veteran_confirmation,
)


@pytest.mark.asyncio
async def test_mcp_durable_writes_reject_untrusted_model_arguments(monkeypatch):
    monkeypatch.setenv("VAB_SCHEDULING_RUNTIME_MODE", "supabase_test")
    server = FastMCP("durable-boundary-test")
    record_option_selection.register(server)
    record_veteran_confirmation.register(server)
    get_scheduling_encounter.register(server)

    async with Client(server) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        parameters = tools["record_veteran_confirmation"].inputSchema["properties"]
        assert "trusted_assertion" not in parameters
        assert "verified_evidence_reference" not in parameters
        confirmation = await client.call_tool(
            "record_veteran_confirmation",
            {
                "case_id": "DEMO-PC-5000335-001",
                "confirmation_request_id": "test-confirmation",
                "option_id": "test-option",
                "response": "CONFIRMED",
                "actor_id": "test-veteran",
                "idempotency_key": "test-confirmation-key",
            },
            raise_on_error=False,
        )
        selection = await client.call_tool(
            "record_option_selection",
            {
                "case_id": "DEMO-PC-5000335-001",
                "handoff_id": "test-handoff",
                "option_id": "test-option",
                "actor_id": "test-scheduler",
                "idempotency_key": "test-selection-key",
            },
            raise_on_error=False,
        )
        encounter = await client.call_tool(
            "get_scheduling_encounter",
            {"case_id": "DEMO-PC-5000335-001"},
            raise_on_error=False,
        )

    assert confirmation.is_error
    assert selection.is_error
    assert encounter.is_error


class MCPRemoteIntegrationTests(unittest.TestCase):
    def test_authenticated_initialize_through_parent_lifespan(self) -> None:
        """Remote MCP must enforce auth and complete a real initialize handshake."""
        import veteran_access_bridge.app.asgi as asgi_mod
        import veteran_access_bridge.mcp.config as cfg_mod

        env_names = ("VAB_MCP_TRANSPORT", "VAB_MCP_API_KEY")
        old_env = {name: os.environ.get(name) for name in env_names}

        os.environ["VAB_MCP_TRANSPORT"] = "streamable-http"
        os.environ["VAB_MCP_API_KEY"] = "integration-test-key"

        initialize_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "vab-integration-test",
                    "version": "0.1.0",
                },
            },
        }
        accept = "application/json, text/event-stream"

        try:
            importlib.reload(cfg_mod)
            importlib.reload(asgi_mod)

            # Entering TestClient as a context manager is intentional: it runs
            # the parent Starlette lifespan, which must initialize FastMCP's
            # StreamableHTTPSessionManager.
            with TestClient(
                asgi_mod.app,
                raise_server_exceptions=False,
            ) as client:
                no_key = client.post(
                    "/mcp/",
                    json=initialize_payload,
                    headers={"Accept": accept},
                )
                self.assertEqual(no_key.status_code, 401)

                wrong_key = client.post(
                    "/mcp/",
                    json=initialize_payload,
                    headers={
                        "Authorization": "Bearer wrong-key",
                        "Accept": accept,
                    },
                )
                self.assertEqual(wrong_key.status_code, 401)

                valid_key = client.post(
                    "/mcp/",
                    json=initialize_payload,
                    headers={
                        "Authorization": "Bearer integration-test-key",
                        "Accept": accept,
                    },
                )
                self.assertEqual(valid_key.status_code, 200)
                self.assertIn("mcp-session-id", valid_key.headers)
                self.assertIn('"protocolVersion":"2025-03-26"', valid_key.text)
                self.assertIn('"id":1', valid_key.text)
        finally:
            for name, value in old_env.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

            # Restore the normal stdio/default module state for subsequent tests.
            importlib.reload(cfg_mod)
            importlib.reload(asgi_mod)


if __name__ == "__main__":
    unittest.main()
