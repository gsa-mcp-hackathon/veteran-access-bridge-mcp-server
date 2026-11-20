import unittest

from veteran_access_bridge.mcp.tools.assess_access_standard import run


class MCPAccessStandardTests(unittest.TestCase):
    def test_canonical_cardiology_case_returns_review_signal(self) -> None:
        payload = run("DEMO-CARD-5000335-001")

        self.assertEqual(payload["care_category"], "SPECIALTY")
        self.assertEqual(payload["patient_indicated_date"], "2026-10-01")
        self.assertEqual(payload["standard_days"], 28)
        self.assertEqual(payload["earliest_eligible_va_wait_days"], 35)
        self.assertTrue(payload["wait_standard_exceeded"])
        self.assertTrue(payload["community_care_review_recommended"])
        self.assertEqual(
            payload["community_care_authorization_status"],
            "NOT_EVALUATED",
        )
        self.assertTrue(payload["signal_only"])
        self.assertFalse(payload["authorization_granted"])
        self.assertFalse(payload["eps_invoked"])
        self.assertFalse(payload["booking_created"])
        self.assertEqual(payload["comparator_source_system"], "FEDERAL_EHR_FHIR")
        self.assertTrue(payload["synthetic"])


if __name__ == "__main__":
    unittest.main()
