"""M2-1 model-layer tests.

Verifies:
- WorkflowState remains a computed/stateless enum (M1 values unchanged)
- CaseLifecycleState is a distinct persisted concept with its own enum
- ALLOWED_LIFECYCLE_TRANSITIONS covers every CaseLifecycleState
- Terminal states (COMPLETED, CANCELLED) have no outbound transitions
- CaseEvent is append-oriented, immutable, and carries idempotency_key
- Invalid from/to state combinations are detectable via the transition table
- ActorRole is a closed validated enum
- BookingRecord, SlotReservationEntry, CaseLifecycleRecord construct correctly
- SchedulingHandoff carries M2 fields
- WorkflowState and CaseLifecycleState are separate types that cannot be
  accidentally substituted for each other
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from veteran_access_bridge.domain.models import (
    ALLOWED_LIFECYCLE_TRANSITIONS,
    ActorRole,
    BookingRecord,
    CaseEvent,
    CaseEventType,
    CaseLifecycleRecord,
    CaseLifecycleState,
    OptionReadiness,
    SchedulingHandoff,
    SlotReservationEntry,
    WorkflowState,
)

_NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# WorkflowState — computed readiness gate (M1 values must be unchanged)
# ---------------------------------------------------------------------------


class TestWorkflowStateM1Stability(unittest.TestCase):
    """M1 WorkflowState values must not change."""

    def test_m1_states_present(self) -> None:
        expected = {
            "REQUEST_RECEIVED",
            "CLINICAL_REVIEW_REQUIRED",
            "CONSULT_PENDING",
            "READY_TO_SEARCH",
            "VA_OPTIONS_AVAILABLE",
            "COMMUNITY_CARE_REVIEW_REQUIRED",
            "COMMUNITY_OPTIONS_AVAILABLE",
            "READY_FOR_HANDOFF",
            "HUMAN_REVIEW",
            "READY_TO_VERIFY",
            "VERIFIED_BOOKABLE",
            "BOOKED_SIMULATED",
            "SOURCE_UNAVAILABLE",
            "AUTH_REQUIRED",
        }
        actual = {s.value for s in WorkflowState}
        self.assertTrue(
            expected.issubset(actual),
            f"Missing M1 WorkflowState values: {expected - actual}",
        )

    def test_m2_states_added_to_workflow_state_enum(self) -> None:
        """New M2 lifecycle states are added to WorkflowState for enum reuse."""
        m2_values = {
            "OPTION_SELECTED",
            "PENDING_VETERAN_CONFIRMATION",
            "PENDING_SCHEDULER_APPROVAL",
            "COMPLETED",
            "NO_SHOW",
            "CANCELLED",
            "RESCHEDULED",
        }
        actual = {s.value for s in WorkflowState}
        self.assertTrue(
            m2_values.issubset(actual),
            f"Missing M2 WorkflowState values: {m2_values - actual}",
        )

    def test_workflow_state_is_str_enum(self) -> None:
        self.assertEqual(WorkflowState.READY_TO_SEARCH, "READY_TO_SEARCH")

    def test_workflow_state_and_lifecycle_state_are_separate_types(self) -> None:
        """WorkflowState and CaseLifecycleState must be distinct enum types.

        Both are StrEnums, so members with the same string value compare equal
        by Python's str equality semantics — that is expected and intentional.
        The important invariant is that the *types* are distinct so they can be
        used in type annotations and isinstance checks without confusion.
        """
        # Types are distinct classes
        self.assertIsNot(WorkflowState, CaseLifecycleState)
        # Members are not the same object
        self.assertIsNot(
            WorkflowState.READY_TO_SEARCH,
            CaseLifecycleState.READY_TO_SEARCH,
        )
        # Type checks distinguish them
        self.assertIsInstance(WorkflowState.READY_TO_SEARCH, WorkflowState)
        self.assertNotIsInstance(WorkflowState.READY_TO_SEARCH, CaseLifecycleState)
        self.assertIsInstance(CaseLifecycleState.READY_TO_SEARCH, CaseLifecycleState)
        self.assertNotIsInstance(CaseLifecycleState.READY_TO_SEARCH, WorkflowState)


# ---------------------------------------------------------------------------
# CaseLifecycleState — persisted lifecycle position
# ---------------------------------------------------------------------------


class TestCaseLifecycleState(unittest.TestCase):

    def test_all_lifecycle_states_present(self) -> None:
        expected = {
            "REQUEST_RECEIVED",
            "CLINICAL_REVIEW_REQUIRED",
            "CONSULT_PENDING",
            "READY_TO_SEARCH",
            "VA_OPTIONS_AVAILABLE",
            "COMMUNITY_CARE_REVIEW_REQUIRED",
            "COMMUNITY_OPTIONS_AVAILABLE",
            "READY_FOR_HANDOFF",
            "HUMAN_REVIEW",
            "OPTION_SELECTED",
            "READY_TO_VERIFY",
            "AUTH_REQUIRED",
            "VERIFIED_BOOKABLE",
            "PENDING_VETERAN_CONFIRMATION",
            "PENDING_SCHEDULER_APPROVAL",
            "BOOKED_SIMULATED",
            "COMPLETED",
            "NO_SHOW",
            "CANCELLED",
            "RESCHEDULED",
            "SOURCE_UNAVAILABLE",
        }
        actual = {s.value for s in CaseLifecycleState}
        self.assertEqual(expected, actual)

    def test_is_str_enum(self) -> None:
        self.assertEqual(CaseLifecycleState.BOOKED_SIMULATED, "BOOKED_SIMULATED")

    def test_terminal_states_defined(self) -> None:
        terminals = {CaseLifecycleState.COMPLETED, CaseLifecycleState.CANCELLED}
        for state in terminals:
            self.assertIn(state, CaseLifecycleState)


# ---------------------------------------------------------------------------
# ALLOWED_LIFECYCLE_TRANSITIONS — transition table completeness and rules
# ---------------------------------------------------------------------------


class TestAllowedLifecycleTransitions(unittest.TestCase):

    def test_every_lifecycle_state_has_an_entry(self) -> None:
        """Every CaseLifecycleState must appear as a key."""
        for state in CaseLifecycleState:
            self.assertIn(
                state,
                ALLOWED_LIFECYCLE_TRANSITIONS,
                f"{state!r} has no entry in ALLOWED_LIFECYCLE_TRANSITIONS",
            )

    def test_terminal_states_have_no_outbound_transitions(self) -> None:
        self.assertEqual(
            ALLOWED_LIFECYCLE_TRANSITIONS[CaseLifecycleState.COMPLETED],
            frozenset(),
        )
        self.assertEqual(
            ALLOWED_LIFECYCLE_TRANSITIONS[CaseLifecycleState.CANCELLED],
            frozenset(),
        )

    def test_ready_to_search_can_reach_availability_states(self) -> None:
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS[CaseLifecycleState.READY_TO_SEARCH]
        self.assertIn(CaseLifecycleState.VA_OPTIONS_AVAILABLE, allowed)
        self.assertIn(CaseLifecycleState.COMMUNITY_OPTIONS_AVAILABLE, allowed)
        self.assertIn(CaseLifecycleState.SOURCE_UNAVAILABLE, allowed)

    def test_booked_simulated_can_reach_all_outcome_states(self) -> None:
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS[CaseLifecycleState.BOOKED_SIMULATED]
        self.assertIn(CaseLifecycleState.COMPLETED, allowed)
        self.assertIn(CaseLifecycleState.NO_SHOW, allowed)
        self.assertIn(CaseLifecycleState.CANCELLED, allowed)
        self.assertIn(CaseLifecycleState.RESCHEDULED, allowed)

    def test_completed_cannot_transition_anywhere(self) -> None:
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS[CaseLifecycleState.COMPLETED]
        self.assertEqual(len(allowed), 0)

    def test_cancelled_cannot_transition_anywhere(self) -> None:
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS[CaseLifecycleState.CANCELLED]
        self.assertEqual(len(allowed), 0)

    def test_pending_scheduler_approval_transitions(self) -> None:
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS[
            CaseLifecycleState.PENDING_SCHEDULER_APPROVAL
        ]
        self.assertIn(CaseLifecycleState.BOOKED_SIMULATED, allowed)
        self.assertIn(CaseLifecycleState.HUMAN_REVIEW, allowed)
        # Must NOT skip directly to COMPLETED
        self.assertNotIn(CaseLifecycleState.COMPLETED, allowed)

    def test_verified_bookable_cannot_skip_veteran_confirmation(self) -> None:
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS[CaseLifecycleState.VERIFIED_BOOKABLE]
        self.assertNotIn(CaseLifecycleState.BOOKED_SIMULATED, allowed)
        self.assertIn(CaseLifecycleState.PENDING_VETERAN_CONFIRMATION, allowed)

    def test_all_transition_targets_are_valid_lifecycle_states(self) -> None:
        """Every target in the transition table must be a CaseLifecycleState."""
        valid = set(CaseLifecycleState)
        for from_state, targets in ALLOWED_LIFECYCLE_TRANSITIONS.items():
            for to_state in targets:
                self.assertIn(
                    to_state,
                    valid,
                    f"Invalid target {to_state!r} from {from_state!r}",
                )

    def test_invalid_transition_detectable(self) -> None:
        """Verify a known-invalid transition is not in the table."""
        # Cannot jump from READY_TO_SEARCH directly to BOOKED_SIMULATED
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS[CaseLifecycleState.READY_TO_SEARCH]
        self.assertNotIn(CaseLifecycleState.BOOKED_SIMULATED, allowed)


# ---------------------------------------------------------------------------
# CaseEventType — append-oriented event vocabulary
# ---------------------------------------------------------------------------


class TestCaseEventType(unittest.TestCase):

    def test_booked_simulated_event_exists(self) -> None:
        self.assertIn("BOOKED_SIMULATED", [e.value for e in CaseEventType])

    def test_post_booking_outcome_events_exist(self) -> None:
        values = {e.value for e in CaseEventType}
        for expected in (
            "APPOINTMENT_COMPLETED",
            "VETERAN_NO_SHOW",
            "APPOINTMENT_CANCELLED",
            "RESCHEDULE_REQUESTED",
        ):
            self.assertIn(expected, values)

    def test_veteran_and_scheduler_confirmation_events_exist(self) -> None:
        values = {e.value for e in CaseEventType}
        for expected in (
            "VETERAN_CONFIRMED",
            "VETERAN_DECLINED",
            "VETERAN_REQUESTED_CHANGE",
            "SCHEDULER_APPROVED",
            "SCHEDULER_REQUESTED_REVISION",
        ):
            self.assertIn(expected, values)


# ---------------------------------------------------------------------------
# ActorRole — closed validated enum
# ---------------------------------------------------------------------------


class TestActorRole(unittest.TestCase):

    def test_three_roles_defined(self) -> None:
        self.assertEqual(
            {r.value for r in ActorRole},
            {"SCHEDULER", "VETERAN", "SYSTEM"},
        )

    def test_is_str_enum(self) -> None:
        self.assertEqual(ActorRole.SCHEDULER, "SCHEDULER")

    def test_invalid_role_not_in_enum(self) -> None:
        with self.assertRaises(ValueError):
            ActorRole("ADMIN")


# ---------------------------------------------------------------------------
# CaseEvent — immutable, idempotency_key, append-oriented
# ---------------------------------------------------------------------------


class TestCaseEvent(unittest.TestCase):

    def _make_event(self, **overrides: object) -> CaseEvent:
        defaults: dict[str, object] = {
            "event_id": "evt-001",
            "case_id": "DEMO-CARD-5000335-001",
            "event_type": CaseEventType.OPTION_SELECTED,
            "from_state": CaseLifecycleState.HUMAN_REVIEW,
            "to_state": CaseLifecycleState.OPTION_SELECTED,
            "actor_role": ActorRole.SCHEDULER,
            "actor_id": "sched-demo-001",
            "occurred_at": _NOW,
            "idempotency_key": "DEMO-CARD-5000335-001:OPTION_SELECTED:opt-001",
        }
        defaults.update(overrides)
        return CaseEvent(**defaults)  # type: ignore[arg-type]

    def test_event_constructs(self) -> None:
        evt = self._make_event()
        self.assertEqual(evt.case_id, "DEMO-CARD-5000335-001")
        self.assertEqual(evt.actor_role, ActorRole.SCHEDULER)
        self.assertTrue(evt.synthetic)

    def test_event_is_frozen(self) -> None:
        evt = self._make_event()
        with self.assertRaises((AttributeError, TypeError)):
            evt.event_id = "modified"  # type: ignore[misc]

    def test_idempotency_key_is_present(self) -> None:
        evt = self._make_event()
        self.assertIsNotNone(evt.idempotency_key)
        self.assertGreater(len(evt.idempotency_key), 0)

    def test_payload_defaults_to_none(self) -> None:
        evt = self._make_event()
        self.assertIsNone(evt.payload)

    def test_payload_accepts_dict(self) -> None:
        evt = self._make_event(payload={"option_id": "OPT-VISTA-001"})
        self.assertEqual(evt.payload, {"option_id": "OPT-VISTA-001"})


# ---------------------------------------------------------------------------
# BookingRecord — T26 atomic commit artifact
# ---------------------------------------------------------------------------


class TestBookingRecord(unittest.TestCase):

    def test_booking_record_constructs(self) -> None:
        from veteran_access_bridge.domain.models import AppointmentIntent
        rec = BookingRecord(
            booking_id="booking-001",
            case_id="DEMO-CARD-5000335-001",
            option_id="OPT-VISTA-001",
            slot_id="SLOT-VISTA-001",
            patient_id="5000335",
            consult_id="CONSULT-CARD-5000335-001",
            handoff_id="handoff-abc",
            facility_name="Denver VA Medical Center",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            appointment_start=_NOW,
            appointment_end=_NOW,
            source_system="VISTA_ISS",
            booked_at=_NOW,
            booked_by_role=ActorRole.SCHEDULER,
            booked_by_id="sched-demo-001",
            idempotency_key="DEMO-CARD-5000335-001:OPT-VISTA-001:SLOT-VISTA-001",
        )
        self.assertTrue(rec.synthetic)
        self.assertEqual(rec.booked_by_role, ActorRole.SCHEDULER)
        self.assertIsNone(rec.notes)

    def test_booking_record_is_frozen(self) -> None:
        from veteran_access_bridge.domain.models import AppointmentIntent
        rec = BookingRecord(
            booking_id="b", case_id="c", option_id="o", slot_id="s",
            patient_id="p", consult_id="ci", handoff_id="h",
            facility_name="f",
            appointment_intent=AppointmentIntent.INITIAL_CONSULT,
            appointment_start=_NOW, appointment_end=_NOW,
            source_system="ss", booked_at=_NOW,
            booked_by_role=ActorRole.SCHEDULER, booked_by_id="u",
            idempotency_key="k",
        )
        with self.assertRaises((AttributeError, TypeError)):
            rec.booking_id = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SlotReservationEntry — double-booking protection model
# ---------------------------------------------------------------------------


class TestSlotReservationEntry(unittest.TestCase):

    def test_entry_constructs(self) -> None:
        entry = SlotReservationEntry(
            slot_id="SLOT-VISTA-001",
            case_id="DEMO-CARD-5000335-001",
            option_id="OPT-VISTA-001",
            reserved_at=_NOW,
            idempotency_key="DEMO-CARD-5000335-001:OPT-VISTA-001:SLOT-VISTA-001",
        )
        self.assertFalse(entry.released)
        self.assertTrue(entry.synthetic)

    def test_entry_is_frozen(self) -> None:
        entry = SlotReservationEntry(
            slot_id="s", case_id="c", option_id="o",
            reserved_at=_NOW, idempotency_key="k",
        )
        with self.assertRaises((AttributeError, TypeError)):
            entry.released = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CaseLifecycleRecord — current lifecycle position summary
# ---------------------------------------------------------------------------


class TestCaseLifecycleRecord(unittest.TestCase):

    def test_record_constructs(self) -> None:
        rec = CaseLifecycleRecord(
            case_id="DEMO-CARD-5000335-001",
            current_state=CaseLifecycleState.READY_TO_SEARCH,
            last_event_type=CaseEventType.BLOCKER_CLEARED,
            last_event_at=_NOW,
            event_count=2,
        )
        self.assertEqual(rec.current_state, CaseLifecycleState.READY_TO_SEARCH)
        self.assertTrue(rec.synthetic)

    def test_record_is_frozen(self) -> None:
        rec = CaseLifecycleRecord(
            case_id="c",
            current_state=CaseLifecycleState.CANCELLED,
            last_event_type=CaseEventType.APPOINTMENT_CANCELLED,
            last_event_at=_NOW,
            event_count=1,
        )
        with self.assertRaises((AttributeError, TypeError)):
            rec.event_count = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SchedulingHandoff — M2 fields
# ---------------------------------------------------------------------------


class TestSchedulingHandoffM2Fields(unittest.TestCase):

    def test_m2_fields_present(self) -> None:
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(SchedulingHandoff)}
        for expected in ("viable_option_count", "source_summary",
                         "requires_verification", "synthetic"):
            self.assertIn(
                expected, field_names,
                f"SchedulingHandoff missing M2 field: {expected!r}",
            )

    def test_defaults(self) -> None:
        handoff = SchedulingHandoff(
            handoff_id="h-001",
            patient_id="5000335",
            consult_id="CONSULT-CARD-5000335-001",
            prepared_at=_NOW,
        )
        self.assertEqual(handoff.viable_option_count, 0)
        self.assertEqual(handoff.source_summary, "")
        self.assertFalse(handoff.requires_verification)
        self.assertTrue(handoff.synthetic)
