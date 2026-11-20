import unittest

from run_ibm_scoped import AGENT_ID, scoped_payload

PATH = "/v1/orchestrate/runs?stream=true"


class ScopedTransportTests(unittest.TestCase):
    def test_maps_only_case_context_without_mutating_input(self):
        source = {
            "agent_id": AGENT_ID,
            "context": {"vab_case_id": "DEMO-CARD-5000335-001"},
            "message": {"text": "test"},
        }
        result = scoped_payload(source, PATH)
        self.assertEqual(result["context_variables"], source["context"])
        self.assertNotIn("context", result)
        self.assertIn("context", source)
        self.assertEqual(result["message"], source["message"])

    def test_unrelated_and_missing_context_unchanged(self):
        for payload, path in [
            ({"agent_id": AGENT_ID}, PATH),
            ({"agent_id": "other", "context": {"vab_case_id": "x"}}, PATH),
            ({"context": {}}, "/other"),
        ]:
            self.assertIs(scoped_payload(payload, path), payload)

    def test_rejects_unknown_or_conflicting_scope(self):
        for context in [
            {"vab_case_id": "other"},
            {"vab_case_id": "DEMO-PC-VOICE-INTAKE-001", "other": True},
        ]:
            with self.assertRaises(ValueError):
                scoped_payload({"agent_id": AGENT_ID, "context": context}, PATH)


if __name__ == "__main__":
    unittest.main()
