"""M6.2a scheduling contract tests."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone

from veteran_access_bridge.domain.models import (
    AppointmentIntent,
    CareCategory,
    PatientClinicClassification,
    PatientClinicRelationship,
    RequestSource,
    ResourceType,
    SchedulingRequest,
    SchedulingSlot,
    SlotAvailability,
    SlotEligibilityReason,
    SlotEligibilityResult,
    SlotTemplateType,
)

_NOW = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)


class TestSchedulingRequest(unittest.TestCase):

    def _request(self, **overrides: object) -> SchedulingRequest:
        values: dict[str, object] = {
            "request_id": "REQ-CARD-001",
            "case_id": "DEMO-CARD-5000335-001",
            "patient_id": "5000335",
            "request_source": RequestSource.CONSULT,
            "care_category": CareCategory.SPECIALTY,
            "service": "CARDIOLOGY",
            "canonical_pid": date(2026, 10, 1),
            "consult_id": "CONSULT-CARD-5000335-001",
            "appointment_intent": AppointmentIntent.INITIAL_CONSULT,
            "patient_classification": PatientClinicClassification.NEW,
            "required_duration_minutes": 30,
        }
        values.update(overrides)
        return SchedulingRequest(**values)  # type: ignore[arg-type]

    def test_constructs_and_preserves_pid(self) -> None:
        request = self._request()
        self.assertEqual(request.canonical_pid, date(2026, 10, 1))
        self.assertEqual(request.care_category, CareCategory.SPECIALTY)
        self.assertTrue(request.synthetic)

    def test_is_frozen(self) -> None:
        request = self._request()
        with self.assertRaises(FrozenInstanceError):
            request.canonical_pid = date(2026, 10, 2)  # type: ignore[misc]

    def test_consult_requires_consult_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "CONSULT requests require consult_id"):
            self._request(consult_id=None)

    def test_duration_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            self._request(required_duration_minutes=0)

    def test_demo_request_fails_closed_on_non_synthetic(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be synthetic"):
            self._request(synthetic=False)


class TestPatientClinicRelationship(unittest.TestCase):

    def test_unknown_classification_is_explicit_enum_value(self) -> None:
        self.assertEqual(
            PatientClinicClassification.UNKNOWN.value,
            "UNKNOWN",
        )

    def test_relationship_requires_synthetic_demo_record(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be synthetic"):
            PatientClinicRelationship(
                patient_id="5000335",
                facility_id="549",
                stop_code="303",
                stop_code_group="CARDIOLOGY",
                last_completed_visit=None,
                as_of=_NOW,
                synthetic=False,
            )


class TestSchedulingSlot(unittest.TestCase):

    def _slot(self, **overrides: object) -> SchedulingSlot:
        start = _NOW + timedelta(days=10)
        values: dict[str, object] = {
            "slot_id": "SLOT-CARD-001",
            "source_system": "VISTA_ISS",
            "source_record_id": "SRC-SLOT-CARD-001",
            "facility_id": "549",
            "facility_name": "Synthetic VA Facility",
            "clinic_id": "CARD-CLINIC-1",
            "stop_code": "303",
            "stop_code_group": "CARDIOLOGY",
            "service": "CARDIOLOGY",
            "resource_id": "PROV-1",
            "resource_name": "Dr. Synthetic",
            "resource_type": ResourceType.PHYSICIAN,
            "template_type": SlotTemplateType.CONSULT,
            "modality": "IN_PERSON",
            "slot_start": start,
            "slot_end": start + timedelta(minutes=30),
            "duration_minutes": 30,
            "availability": SlotAvailability.AVAILABLE,
            "eligible_patient_classifications": (
                PatientClinicClassification.NEW,
            ),
            "eligible_appointment_intents": (
                AppointmentIntent.INITIAL_CONSULT,
            ),
        }
        values.update(overrides)
        return SchedulingSlot(**values)  # type: ignore[arg-type]

    def test_constructs(self) -> None:
        slot = self._slot()
        self.assertEqual(slot.duration_minutes, 30)
        self.assertEqual(slot.availability, SlotAvailability.AVAILABLE)
        self.assertTrue(slot.synthetic)

    def test_slot_end_must_follow_start(self) -> None:
        start = _NOW + timedelta(days=10)
        with self.assertRaisesRegex(ValueError, "slot_end must be after slot_start"):
            self._slot(slot_start=start, slot_end=start)

    def test_duration_must_match_interval(self) -> None:
        with self.assertRaisesRegex(ValueError, "must equal the normalized slot interval"):
            self._slot(duration_minutes=45)

    def test_demo_slot_fails_closed_on_non_synthetic(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be synthetic"):
            self._slot(synthetic=False)


class TestSlotEligibilityResult(unittest.TestCase):

    def test_eligible_result_has_only_eligible_reason(self) -> None:
        result = SlotEligibilityResult(
            request_id="REQ-1",
            slot_id="SLOT-1",
            eligible=True,
            reasons=(SlotEligibilityReason.ELIGIBLE,),
        )
        self.assertTrue(result.eligible)

    def test_eligible_result_rejects_failure_reason(self) -> None:
        with self.assertRaisesRegex(ValueError, "must contain only"):
            SlotEligibilityResult(
                request_id="REQ-1",
                slot_id="SLOT-1",
                eligible=True,
                reasons=(SlotEligibilityReason.SERVICE_MISMATCH,),
            )

    def test_ineligible_result_rejects_eligible_reason(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not contain"):
            SlotEligibilityResult(
                request_id="REQ-1",
                slot_id="SLOT-1",
                eligible=False,
                reasons=(SlotEligibilityReason.ELIGIBLE,),
            )

    def test_ineligible_result_can_carry_multiple_reasons(self) -> None:
        result = SlotEligibilityResult(
            request_id="REQ-1",
            slot_id="SLOT-1",
            eligible=False,
            reasons=(
                SlotEligibilityReason.SERVICE_MISMATCH,
                SlotEligibilityReason.DURATION_INSUFFICIENT,
            ),
        )
        self.assertEqual(len(result.reasons), 2)


if __name__ == "__main__":
    unittest.main()
