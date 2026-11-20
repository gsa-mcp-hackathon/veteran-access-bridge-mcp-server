import unittest

from veteran_access_bridge.mcp.routes import health_payload, version_payload


class MCPHealthTests(unittest.TestCase):
    def test_health_is_synthetic_only(self) -> None:
        payload = health_payload()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "veteran-access-mcp")
        self.assertTrue(payload["synthetic_only"])

    def test_version_is_reported(self) -> None:
        self.assertEqual(version_payload()["version"], "0.4.1")


if __name__ == "__main__":
    unittest.main()
