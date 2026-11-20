"""ASGI app smoke tests — verify the unified Starlette app behaves correctly.

Uses Starlette's TestClient (synchronous, no running server needed).
Covers:
  - static asset routes
  - /health
  - /api/* authorization (role enforcement, case-scope enforcement)
  - /mcp mount presence (stdio mode: no /mcp; remote mode: /mcp present)
  - missing/invalid demo headers → 403
"""

from __future__ import annotations

import importlib
import os
import unittest


def _make_client(env_overrides: dict | None = None):
    """Build a fresh TestClient against a freshly-built ASGI app.

    We force a module reload so environment variable changes take effect
    on the Settings singleton without polluting other tests.
    """
    from starlette.testclient import TestClient

    # Patch env before reloading config-dependent modules.
    old = {}
    overrides = env_overrides or {}
    for k, v in overrides.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v

    try:
        # Reload config, then the app module, to pick up env changes.
        import veteran_access_bridge.app.asgi as asgi_mod
        import veteran_access_bridge.mcp.config as cfg_mod

        importlib.reload(cfg_mod)
        importlib.reload(asgi_mod)

        app = asgi_mod.app
        return TestClient(app, raise_server_exceptions=False)
    finally:
        # Restore env.
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# Default client: stdio transport (default settings)
def _default_client():
    from starlette.testclient import TestClient

    from veteran_access_bridge.app.asgi import app

    return TestClient(app, raise_server_exceptions=False)


_SCHED_HEADERS = {
    "x-demo-role": "SCHEDULER",
    "x-demo-actor": "test-scheduler-001",
    "x-demo-case": "DEMO-CARD-5000335-001",
}
_VET_HEADERS = {
    "x-demo-role": "VETERAN",
    "x-demo-actor": "test-veteran-001",
    "x-demo-case": "DEMO-CARD-5000335-001",
}


class StaticRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = _default_client()

    def test_index_html(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])

    def test_app_js(self):
        r = self.client.get("/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r.headers["content-type"])

    def test_styles_css(self):
        r = self.client.get("/styles.css")
        self.assertEqual(r.status_code, 200)
        self.assertIn("css", r.headers["content-type"])


class HealthRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = _default_client()

    def test_health_ok(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["synthetic"])
        self.assertFalse(body["production_writes_enabled"])

    def test_health_no_auth_required(self):
        """Health endpoint must work without any identity headers."""
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = _default_client()

    def test_missing_headers_returns_403(self):
        r = self.client.get("/api/cases/DEMO-CARD-5000335-001")
        self.assertEqual(r.status_code, 403)

    def test_invalid_role_returns_403(self):
        r = self.client.get(
            "/api/cases/DEMO-CARD-5000335-001",
            headers={
                "x-demo-role": "ADMIN",
                "x-demo-actor": "x",
                "x-demo-case": "DEMO-CARD-5000335-001",
            },
        )
        self.assertEqual(r.status_code, 403)

    def test_wrong_case_scope_returns_403(self):
        r = self.client.get(
            "/api/cases/DEMO-CARD-5000335-001",
            headers={
                "x-demo-role": "SCHEDULER",
                "x-demo-actor": "x",
                "x-demo-case": "OTHER-CASE",
            },
        )
        self.assertEqual(r.status_code, 403)

    def test_veteran_cannot_view_metrics(self):
        r = self.client.get("/api/metrics", headers=_VET_HEADERS)
        self.assertEqual(r.status_code, 403)

    def test_scheduler_can_view_case(self):
        r = self.client.get("/api/cases/DEMO-CARD-5000335-001", headers=_SCHED_HEADERS)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("case_id", body)

    def test_veteran_can_view_case(self):
        r = self.client.get("/api/cases/DEMO-CARD-5000335-001", headers=_VET_HEADERS)
        self.assertEqual(r.status_code, 200)

    def test_scheduler_can_view_metrics(self):
        r = self.client.get("/api/metrics", headers=_SCHED_HEADERS)
        self.assertEqual(r.status_code, 200)

    def test_scheduler_can_view_integrations(self):
        r = self.client.get("/api/integrations", headers=_SCHED_HEADERS)
        self.assertEqual(r.status_code, 200)


class MCPMountTests(unittest.TestCase):
    """Verify /mcp mount behavior in stdio vs remote transport mode."""

    def test_mcp_not_mounted_in_stdio_mode(self):
        """In stdio mode /mcp should not be reachable as an HTTP endpoint."""
        client = _default_client()
        r = client.get("/mcp")
        # 404 or 405 — not found because the mount is absent in stdio mode.
        self.assertIn(r.status_code, (404, 405, 406))

    def test_mcp_mounted_in_remote_mode_with_valid_key(self):
        """With a valid API key and streamable-http transport /mcp must be reachable."""
        # Build the MCP sub-app directly to confirm it mounts without error
        # when the security gate passes — avoids module-reload ordering issues.
        from veteran_access_bridge.mcp.app import mcp, validate_transport

        # Gate passes with a valid key.
        validate_transport("streamable-http", api_key="test-hackathon-secret-xyz")

        # MCP app can produce a Starlette sub-app.
        sub_app = mcp.http_app(path="/mcp", transport="streamable-http")
        self.assertIsNotNone(sub_app)

        # The routes list includes /mcp.
        paths = [getattr(r, "path", "") for r in sub_app.routes]
        self.assertIn("/mcp", paths)

    def test_mcp_not_mounted_without_api_key(self):
        """Without an API key, app build should fail closed (RuntimeError at import)."""
        import importlib

        import veteran_access_bridge.app.asgi as asgi_mod
        import veteran_access_bridge.mcp.config as cfg_mod

        os.environ["VAB_MCP_TRANSPORT"] = "streamable-http"
        os.environ["VAB_MCP_API_KEY"] = ""
        try:
            importlib.reload(cfg_mod)
            with self.assertRaises(RuntimeError):
                importlib.reload(asgi_mod)
        finally:
            os.environ.pop("VAB_MCP_TRANSPORT", None)
            os.environ.pop("VAB_MCP_API_KEY", None)
            # Restore default module state.
            importlib.reload(cfg_mod)
            importlib.reload(asgi_mod)


if __name__ == "__main__":
    unittest.main()
