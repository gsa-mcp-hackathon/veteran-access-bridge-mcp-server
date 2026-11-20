"""Tests for Issue #70 MSA live interaction event model."""

import unittest
from datetime import datetime, timezone

from veteran_access_bridge.domain import (
    InteractionEvent,
    InteractionEventSource,
    InteractionEventType,
    event_to_dict,
)
from veteran_access_bridge.domain.models import (
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
)
from veteran_access_bridge.services import (
    InteractionEventConflictError,
    InteractionEventStore,
    project_case_event,
)

NOW = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)


def make_event(**overrides):
    values = dict(
        event_id="evt-live-001",
        event_type=InteractionEventType.INTENT_CAPTURED,
        interaction_id="int-001",
        case_id="DEMO-PC-5000999-001",
        scheduling_encounter_id="SE-DEMO-PC-5000999-001-REQ-PC-001",
        correlation_id="corr-001",
        source=InteractionEventSource.CONVERSATION,
        occurred_at=NOW,
        payload={"care_category": "PRIMARY_CARE"},
    )
    values.update(overrides)
    return InteractionEvent(**values)


class InteractionEventContractTests(unittest.TestCase):
    def test_valid_conversation_event(self):
        event = make_event()
        self.assertEqual(event.event_type, InteractionEventType.INTENT_CAPTURED)
        self.assertTrue(event.synthetic)

    def test_serialization_matches_sse_contract_shape(self):
        payload = event_to_dict(make_event())
        self.assertEqual(payload["event_type"], "intent_captured")
        self.assertEqual(payload["source"], "conversation")
        self.assertEqual(payload["interaction_id"], "int-001")
        self.assertEqual(payload["correlation_id"], "corr-001")
        self.assertTrue(payload["synthetic"])

    def test_requires_timezone_aware_timestamp(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            make_event(occurred_at=datetime(2026, 10, 25, 15, 0))

    def test_requires_synthetic_mvp_event(self):
        with self.assertRaisesRegex(ValueError, "must be synthetic"):
            make_event(synthetic=False)

    def test_conversation_cannot_emit_eligibility(self):
        with self.assertRaisesRegex(ValueError, "cannot be sourced from conversation"):
            make_event(
                event_type=InteractionEventType.ELIGIBILITY_UPDATED,
                source=InteractionEventSource.CONVERSATION,
            )

    def test_conversation_cannot_emit_access_assessment(self):
        with self.assertRaises(ValueError):
            make_event(
                event_type=InteractionEventType.ACCESS_ASSESSED,
                source=InteractionEventSource.CONVERSATION,
            )

    def test_conversation_cannot_emit_provider_requested_date(self):
        with self.assertRaisesRegex(ValueError, "governed/system evidence"):
            make_event(
                event_type=InteractionEventType.PROVIDER_REQUESTED_DATE_LOADED,
                source=InteractionEventSource.CONVERSATION,
            )

    def test_conversation_cannot_emit_slot_verified(self):
        with self.assertRaises(ValueError):
            make_event(
                event_type=InteractionEventType.SLOT_VERIFIED,
                source=InteractionEventSource.CONVERSATION,
            )

    def test_msa_approval_must_come_from_msa(self):
        with self.assertRaisesRegex(ValueError, "must be emitted by the MSA"):
            make_event(
                event_type=InteractionEventType.MSA_APPROVED,
                source=InteractionEventSource.APPLICATION,
            )

    def test_simulated_booking_must_come_from_application(self):
        with self.assertRaisesRegex(ValueError, "must be emitted by the application"):
            make_event(
                event_type=InteractionEventType.SIMULATED_BOOKING_RECORDED,
                source=InteractionEventSource.DETERMINISTIC_SERVICE,
            )

    def test_store_is_append_only_and_idempotent_for_same_event(self):
        store = InteractionEventStore()
        event = make_event()
        first = store.append(event)
        second = store.append(event)
        self.assertIs(first, second)
        self.assertEqual(store.get_events("int-001"), (event,))

    def test_store_rejects_conflicting_event_id_reuse(self):
        store = InteractionEventStore()
        store.append(make_event())
        with self.assertRaises(InteractionEventConflictError):
            store.append(
                make_event(
                    event_type=InteractionEventType.PREFERENCE_CAPTURED,
                    payload={"preferred_daypart": "MORNING"},
                )
            )

    def test_store_separates_interactions(self):
        store = InteractionEventStore()
        first = make_event(event_id="evt-1", interaction_id="int-1")
        second = make_event(event_id="evt-2", interaction_id="int-2")
        store.append(first)
        store.append(second)
        self.assertEqual(store.get_events("int-1"), (first,))
        self.assertEqual(store.get_events("int-2"), (second,))

    def test_exact_lifecycle_events_project_without_mutating_case_event(self):
        case_event = CaseEvent(
            event_id="case-ver-001",
            case_id="DEMO-PC-5000999-001",
            event_type=CaseEventType.VERIFICATION_PASSED,
            from_state=CaseLifecycleState.OPTION_SELECTED,
            to_state=CaseLifecycleState.VERIFIED_BOOKABLE,
            actor_role=ActorRole.SYSTEM,
            actor_id="synthetic-system",
            occurred_at=NOW,
            idempotency_key="case-ver-key-001",
            payload={"option_id": "OPT-PC-001"},
        )
        projected = project_case_event(
            case_event,
            interaction_id="int-001",
            scheduling_encounter_id="SE-PC-001",
            correlation_id="corr-001",
        )
        self.assertIsNotNone(projected)
        self.assertEqual(projected.event_type, InteractionEventType.SLOT_VERIFIED)
        self.assertEqual(
            projected.source,
            InteractionEventSource.DETERMINISTIC_SERVICE,
        )
        self.assertEqual(projected.payload["case_event_id"], "case-ver-001")
        self.assertEqual(projected.payload["option_id"], "OPT-PC-001")

    def test_unrelated_lifecycle_event_is_not_guessed_into_live_semantics(self):
        case_event = CaseEvent(
            event_id="case-search-001",
            case_id="DEMO-PC-5000999-001",
            event_type=CaseEventType.SEARCH_EXECUTED,
            from_state=CaseLifecycleState.READY_TO_SEARCH,
            to_state=CaseLifecycleState.VA_OPTIONS_AVAILABLE,
            actor_role=ActorRole.SYSTEM,
            actor_id="synthetic-system",
            occurred_at=NOW,
            idempotency_key="case-search-key-001",
            payload={},
        )
        self.assertIsNone(
            project_case_event(
                case_event,
                interaction_id="int-001",
                scheduling_encounter_id="SE-PC-001",
                correlation_id="corr-001",
            )
        )

    def test_lifecycle_booking_projects_to_simulated_booking_event(self):
        case_event = CaseEvent(
            event_id="case-book-001",
            case_id="DEMO-PC-5000999-001",
            event_type=CaseEventType.BOOKED_SIMULATED,
            from_state=CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
            to_state=CaseLifecycleState.BOOKED_SIMULATED,
            actor_role=ActorRole.SCHEDULER,
            actor_id="msa-demo",
            occurred_at=NOW,
            idempotency_key="case-book-key-001",
            payload={"booking_id": "BOOK-DEMO-001"},
        )
        projected = project_case_event(
            case_event,
            interaction_id="int-001",
            scheduling_encounter_id="SE-PC-001",
            correlation_id="corr-001",
        )
        self.assertEqual(
            projected.event_type,
            InteractionEventType.SIMULATED_BOOKING_RECORDED,
        )
        self.assertEqual(projected.source, InteractionEventSource.APPLICATION)


if __name__ == "__main__":
    unittest.main()
