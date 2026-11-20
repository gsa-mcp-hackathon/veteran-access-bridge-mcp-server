import unittest

from veteran_access_bridge.mcp.tools.determine_workflow_state import run


class MCPWorkflowToolTests(unittest.TestCase):
    def test_demo_case_is_ready_to_search(self) -> None:
        payload = run("DEMO-CARD-5000335-001")
        self.assertEqual(payload["workflow_state"], "READY_TO_SEARCH")
        self.assertTrue(payload["synthetic"])

    def test_unknown_case_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run("UNKNOWN")


if __name__ == "__main__":
    unittest.main()
