"""M6.3d unified Scheduling Encounter MCP tests."""

# ruff: noqa: I001

import unittest

from veteran_access_bridge.domain.models import (
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
)
from veteran_access_bridge.mcp.cases import demo_as_of
from veteran_access_bridge.mcp.tools.get_scheduling_encounter import run
from veteran_access_bridge.services.events import CaseEventStore


CASE_ID = "DEMO-CARD-5000335-001"


class MCPSchedulingEncounterTests(unittest.TestCase):
    def test_read_only_encounter_composes_m61_m62_and_preferences(self) -> None:
        events = CaseEventStore()
        before = events.get_events(CASE_ID)

        payload = run(CASE_ID, event_store=events)

        self.assertEqual(events.get_events(CASE_ID), before)
        self.assertEqual(payload["case_id"], CASE_ID)
        self.assertTrue(payload["synthetic"])
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["preferences_create_eligibility"])
        self.assertFalse(payload["community_care_authorization_granted"])
        self.assertFalse(payload["eps_invoked"])
        self.assertFalse(payload["booking_created"])

        self.assertEqual(payload["encounter_state"], "OPTIONS_ASSEMBLED")
        self.assertEqual(payload["workflow_state"], "READY_TO_SEARCH")
        self.assertEqual(payload["patient_classification"], "NEW")
        self.assertEqual(payload["request"]["canonical_pid"], "2026-10-01")
        self.assertEqual(len(payload["slots"]), 5)
        self.assertEqual(len(payload["slot_eligibility"]), 5)
        self.assertEqual(len(payload["eligible_options"]), 4)
        self.assertEqual(len(payload["ranked_options"]), 4)

        assessment = payload["access_standard"]
        self.assertEqual(assessment["standard_days"], 28)
        self.assertEqual(assessment["earliest_eligible_va_wait_days"], 35)
        self.assertEqual(
            assessment["earliest_eligible_va_option_id"],
            "OPT-FEHR-SLOT-CARD-5000335-001",
        )
        self.assertTrue(assessment["wait_standard_exceeded"])
        self.assertTrue(assessment["community_care_review_recommended"])
        self.assertEqual(
            assessment["community_care_authorization_status"],
            "NOT_EVALUATED",
        )

        self.assertEqual(
            payload["ranked_options"][0]["option"]["option_id"],
            "OPT-VISTA-SLOT-CARD-5000335-001",
        )
        self.assertIsNotNone(payload["decision"])
        self.assertIsNone(payload["decision"]["lifecycle_state"])
        self.assertEqual(payload["decision"]["event_count"], 0)

    def test_existing_lifecycle_is_projected_without_mutation(self) -> None:
        events = CaseEventStore()
        at = demo_as_of()
        steps = (
            (
                CaseLifecycleState.REQUEST_RECEIVED,
                CaseLifecycleState.READY_TO_SEARCH,
                CaseEventType.WORKFLOW_GATE_EVALUATED,
            ),
            (
                CaseLifecycleState.READY_TO_SEARCH,
                CaseLifecycleState.VA_OPTIONS_AVAILABLE,
                CaseEventType.SEARCH_EXECUTED,
            ),
            (
                CaseLifecycleState.VA_OPTIONS_AVAILABLE,
                CaseLifecycleState.READY_FOR_HANDOFF,
                CaseEventType.OPTIONS_ASSESSED,
            ),
            (
                CaseLifecycleState.READY_FOR_HANDOFF,
                CaseLifecycleState.HUMAN_REVIEW,
                CaseEventType.HANDOFF_PREPARED,
            ),
        )
        for index, (from_state, to_state, event_type) in enumerate(steps):
            events.append(
                CaseEvent(
                    event_id=f"m63d-event-{index}",
                    case_id=CASE_ID,
                    event_type=event_type,
                    from_state=from_state,
                    to_state=to_state,
                    actor_role=ActorRole.SYSTEM,
                    actor_id="synthetic-test",
                    occurred_at=at,
                    idempotency_key=f"m63d-key-{index}",
                    payload=(
                        {"handoff_id": "handoff-m63d-001"}
                        if event_type is CaseEventType.HANDOFF_PREPARED
                        else {}
                    ),
                )
            )

        before = events.get_events(CASE_ID)
        payload = run(CASE_ID, event_store=events)

        self.assertEqual(events.get_events(CASE_ID), before)
        self.assertEqual(payload["encounter_state"], "AWAITING_SCHEDULER_REVIEW")
        self.assertEqual(
            payload["decision"]["lifecycle_state"],
            "HUMAN_REVIEW",
        )
        self.assertEqual(payload["decision"]["event_count"], 4)
        self.assertEqual(
            payload["decision"]["latest_event_type"],
            "HANDOFF_PREPARED",
        )

    def test_primary_care_encounter_uses_same_governed_mcp_path(self) -> None:
        case_id = "DEMO-PC-5000999-001"
        events = CaseEventStore()

        payload = run(case_id, event_store=events)

        self.assertEqual(events.get_events(case_id), ())
        self.assertEqual(payload["case_id"], case_id)
        self.assertEqual(payload["workflow_state"], "READY_TO_SEARCH")
        self.assertEqual(payload["encounter_state"], "OPTIONS_ASSEMBLED")
        self.assertEqual(payload["patient_classification"], "ESTABLISHED")
        self.assertEqual(payload["request"]["care_category"], "PRIMARY_CARE")
        self.assertEqual(payload["request"]["canonical_pid"], "2026-11-01")
        self.assertEqual(len(payload["slots"]), 3)
        self.assertEqual(len(payload["slot_eligibility"]), 3)
        self.assertEqual(len(payload["eligible_options"]), 2)
        self.assertNotIn(
            "OPT-VISTA-SLOT-PC-5000999-002",
            {option["option_id"] for option in payload["eligible_options"]},
        )

        assessment = payload["access_standard"]
        self.assertEqual(assessment["care_category"], "PRIMARY")
        self.assertEqual(assessment["standard_days"], 20)
        self.assertEqual(assessment["earliest_eligible_va_wait_days"], 14)
        self.assertEqual(
            assessment["earliest_eligible_va_option_id"],
            "OPT-VISTA-SLOT-PC-5000999-001",
        )
        self.assertFalse(assessment["wait_standard_exceeded"])
        self.assertFalse(assessment["community_care_review_recommended"])
        self.assertEqual(
            assessment["community_care_authorization_status"],
            "NOT_EVALUATED",
        )
        self.assertFalse(payload["eps_invoked"])
        self.assertFalse(payload["booking_created"])

    def test_sandbox_backed_primary_care_case_uses_same_governed_path(self) -> None:
        case_id = "DEMO-PC-5000335-001"
        events = CaseEventStore()

        payload = run(case_id, event_store=events)

        self.assertEqual(events.get_events(case_id), ())
        self.assertEqual(payload["case_id"], case_id)
        self.assertEqual(payload["workflow_state"], "READY_TO_SEARCH")
        self.assertEqual(payload["encounter_state"], "OPTIONS_ASSEMBLED")
        self.assertEqual(payload["patient_classification"], "ESTABLISHED")
        self.assertEqual(payload["request"]["care_category"], "PRIMARY_CARE")
        self.assertEqual(payload["request"]["canonical_pid"], "2026-11-01")
        self.assertEqual(len(payload["slots"]), 3)
        self.assertEqual(len(payload["eligible_options"]), 1)
        self.assertNotIn(
            "OPT-VISTA-SLOT-PC-5000335-002",
            {option["option_id"] for option in payload["eligible_options"]},
        )

        assessment = payload["access_standard"]
        self.assertEqual(assessment["standard_days"], 20)
        self.assertEqual(assessment["earliest_eligible_va_wait_days"], 14)
        self.assertEqual(
            assessment["earliest_eligible_va_option_id"],
            "OPT-VISTA-SLOT-PC-5000335-001",
        )
        self.assertFalse(assessment["wait_standard_exceeded"])
        self.assertFalse(payload["eps_invoked"])
        self.assertFalse(payload["booking_created"])

    def test_unknown_case_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown synthetic case_id"):
            run("UNKNOWN-CASE", event_store=CaseEventStore())

    def test_repeated_calls_are_deterministic_with_same_store(self) -> None:
        events = CaseEventStore()

        first = run(CASE_ID, event_store=events)
        second = run(CASE_ID, event_store=events)

        self.assertEqual(first, second)
        self.assertEqual(events.get_events(CASE_ID), ())


if __name__ == "__main__":
    unittest.main()
