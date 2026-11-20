"""Harness validation only; these fixtures are not agent evaluation evidence."""

import copy
import unittest

from score_traces import build_case


class TraceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "test_id": "adapter-unit-fixture",
            "input": "Fixture input",
            "actual_output": "Fixture output",
            "schema_commit": "fixture-only",
            "runtime_version": "fixture-only",
            "trace_source": "actual_agent_trace",
            "available_tools": [
                {
                    "name": "lookup",
                    "description": "Fixture",
                    "inputSchema": {"type": "object"},
                }
            ],
            "calls": [
                {
                    "name": "lookup",
                    "args": {},
                    "result": {"content": [{"type": "text", "text": "fixture"}]},
                    "initiator": "agent",
                }
            ],
        }

    def test_complete_record_builds(self):
        self.assertEqual(len(build_case(self.record).mcp_tools_called), 1)

    def test_missing_evidence_rejected(self):
        for field in self.record:
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                del record[field]
                with self.assertRaises(ValueError):
                    build_case(record)

    def test_host_call_rejected(self):
        self.record["calls"][0]["initiator"] = "host"
        with self.assertRaises(ValueError):
            build_case(self.record)

    def test_unknown_tool_rejected(self):
        self.record["calls"][0]["name"] = "other"
        with self.assertRaises(ValueError):
            build_case(self.record)

    def test_missing_result_rejected(self):
        del self.record["calls"][0]["result"]
        with self.assertRaises(ValueError):
            build_case(self.record)

    def test_synthetic_source_rejected(self):
        self.record["trace_source"] = "generated"
        with self.assertRaises(ValueError):
            build_case(self.record)


if __name__ == "__main__":
    unittest.main()
