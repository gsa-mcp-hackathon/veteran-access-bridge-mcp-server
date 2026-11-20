import unittest

from veteran_access_bridge.mcp.tools.search_availability import run


class MCPSearchToolTests(unittest.TestCase):
    def test_demo_search_preserves_three_source_results(self) -> None:
        payload = run("DEMO-CARD-5000335-001")
        sources = {item["source_system"] for item in payload["source_results"]}
        self.assertEqual(
            sources,
            {"VISTA_ISS", "FEDERAL_EHR_FHIR", "COMMUNITY_CARE_EPS"},
        )
        self.assertFalse(payload["creates_scheduling_handoff"])

    def test_search_preserves_provenance(self) -> None:
        payload = run("DEMO-CARD-5000335-001")
        self.assertGreater(len(payload["options"]), 0)
        for option in payload["options"]:
            self.assertIn("provenance", option)
            self.assertTrue(option["provenance"]["synthetic"])
            self.assertIn("retrieved_at", option["provenance"])

    def test_community_authorization_readiness_is_preserved(self) -> None:
        payload = run("DEMO-CARD-5000335-001")
        community = [
            option
            for option in payload["options"]
            if option["source_system"] == "COMMUNITY_CARE_EPS"
        ]
        readiness = [option["readiness"] for option in community]
        self.assertEqual(readiness.count("AVAILABLE_NOT_AUTHORIZED"), 2)
        self.assertEqual(readiness.count("AUTHORIZED_NOT_VERIFIED"), 1)
        self.assertNotIn("VERIFIED_BOOKABLE", readiness)


if __name__ == "__main__":
    unittest.main()
