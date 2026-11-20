"""Tests for Issue #80 interaction/runtime correlation."""

import unittest
from datetime import datetime, timezone

from veteran_access_bridge.domain import (
    CorrelationConflictError,
    CorrelationRegistry,
    InteractionChannel,
    InteractionCorrelation,
)

NOW = datetime(2026, 10, 25, 16, 0, tzinfo=timezone.utc)


def make_record(**overrides):
    values = dict(
        interaction_id="int-001",
        case_id="DEMO-PC-5000999-001",
        scheduling_encounter_id="SE-PC-001",
        correlation_id="corr-001",
        channel=InteractionChannel.PHONE,
        created_at=NOW,
        orchestrate_run_id=None,
        orchestrate_session_id=None,
    )
    values.update(overrides)
    return InteractionCorrelation(**values)


class CorrelationRegistryTests(unittest.TestCase):
    def test_register_and_lookup(self):
        registry = CorrelationRegistry()
        record = registry.register(make_record())
        self.assertEqual(registry.require("int-001"), record)
        self.assertEqual(registry.get_by_correlation_id("corr-001"), record)

    def test_same_record_is_idempotent(self):
        registry = CorrelationRegistry()
        record = make_record()
        self.assertIs(registry.register(record), record)
        self.assertEqual(registry.register(record), record)

    def test_interaction_cannot_rebind_to_another_encounter(self):
        registry = CorrelationRegistry()
        registry.register(make_record())
        with self.assertRaises(CorrelationConflictError):
            registry.register(
                make_record(scheduling_encounter_id="SE-PC-002")
            )

    def test_correlation_id_cannot_be_shared(self):
        registry = CorrelationRegistry()
        registry.register(make_record())
        with self.assertRaises(CorrelationConflictError):
            registry.register(
                make_record(
                    interaction_id="int-002",
                    correlation_id="corr-001",
                )
            )

    def test_runtime_metadata_can_be_attached_later(self):
        registry = CorrelationRegistry()
        registry.register(make_record())
        updated = registry.attach_runtime(
            "int-001",
            orchestrate_run_id="run-001",
            orchestrate_session_id="session-001",
        )
        self.assertEqual(updated.case_id, "DEMO-PC-5000999-001")
        self.assertEqual(updated.scheduling_encounter_id, "SE-PC-001")
        self.assertEqual(updated.orchestrate_run_id, "run-001")
        self.assertEqual(registry.get_by_run_id("run-001"), updated)

    def test_retry_can_replace_run_id_without_rebinding_encounter(self):
        registry = CorrelationRegistry()
        registry.register(make_record())
        first = registry.attach_runtime(
            "int-001",
            orchestrate_run_id="run-001",
        )
        second = registry.attach_runtime(
            "int-001",
            orchestrate_run_id="run-002",
        )
        self.assertEqual(first.scheduling_encounter_id, second.scheduling_encounter_id)
        self.assertEqual(second.correlation_id, "corr-001")
        self.assertIsNone(registry.get_by_run_id("run-001"))
        self.assertEqual(registry.get_by_run_id("run-002"), second)

    def test_run_id_cannot_be_shared_across_interactions(self):
        registry = CorrelationRegistry()
        registry.register(make_record())
        registry.register(
            make_record(
                interaction_id="int-002",
                correlation_id="corr-002",
                scheduling_encounter_id="SE-PC-002",
                channel=InteractionChannel.CHAT,
            )
        )
        registry.attach_runtime("int-001", orchestrate_run_id="run-001")
        with self.assertRaises(CorrelationConflictError):
            registry.attach_runtime("int-002", orchestrate_run_id="run-001")

    def test_duplicate_stream_event_is_ignored(self):
        registry = CorrelationRegistry()
        self.assertTrue(registry.accept_stream_event("evt-stream-001"))
        self.assertFalse(registry.accept_stream_event("evt-stream-001"))

    def test_ids_are_opaque_machine_safe(self):
        with self.assertRaises(ValueError):
            make_record(correlation_id="William Green 123")

    def test_timestamp_must_be_timezone_aware(self):
        with self.assertRaises(ValueError):
            make_record(created_at=datetime(2026, 10, 25, 16, 0))


if __name__ == "__main__":
    unittest.main()
