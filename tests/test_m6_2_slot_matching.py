"""M6.2c deterministic slot-matching tests."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from veteran_access_bridge.domain.models import (
    AppointmentIntent,
    CareCategory,
    PatientClinicClassification,
    RequestSource,
    ResourceType,
    SchedulingRequest,
    SchedulingSlot,
    SlotAvailability,
    SlotEligibilityReason,
    SlotTemplateType,
)
from veteran_access_bridge.services.slot_matching import (
    evaluate_slot_eligibility,
    match_scheduling_slots,
)

_NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


class TestSlotMatching(unittest.TestCase):

    def _request(self, **overrides: object) -> SchedulingRequest:
        values: dict[str, object] = {
            "request_id": "REQ-CARD-001",
            "case_id": "DEMO-CARD-5000335-001",
            "patient_id": "5000335",
            "request_source": RequestSource.CONSULT,
            "care_category": CareCategory.SPECIALTY,
            "service": "CARDIOLOGY",
            "canonical_pid": date(2026, 10, 1),
            "facility_id": "549",
            "clinic_id": "CARD-1",
            "stop_code": "303",
            "stop_code_group": "CARDIOLOGY",
            "patient_classification": PatientClinicClassification.NEW,
            "appointment_intent": AppointmentIntent.INITIAL_CONSULT,
            "consult_id": "CONSULT-CARD-5000335-001",
            "required_duration_minutes": 30,
            "required_resource_types": (ResourceType.PHYSICIAN,),
            "required_template_types": (SlotTemplateType.CONSULT,),
            "required_modality": "IN_PERSON",
        }
        values.update(overrides)
        return SchedulingRequest(**values)  # type: ignore[arg-type]

    def _slot(self, **overrides: object) -> SchedulingSlot:
        start = datetime(2026, 11, 5, 13, 0, tzinfo=timezone.utc)
        values: dict[str, object] = {
            "slot_id": "SLOT-CARD-001",
            "source_system": "FEDERAL_EHR_FHIR",
            "source_record_id": "FEHR-SLOT-CARD-001",
            "facility_id": "549",
            "facility_name": "Synthetic VA Facility",
            "clinic_id": "CARD-1",
            "stop_code": "303",
            "stop_code_group": "CARDIOLOGY",
            "service": "CARDIOLOGY",
            "resource_id": "PROV-1",
            "resource_name": "Dr Synthetic",
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

    def test_fully_compatible_slot_is_eligible(self) -> None:
        result = evaluate_slot_eligibility(self._request(), self._slot())
        self.assertTrue(result.eligible)
        self.assertEqual(result.reasons, (SlotEligibilityReason.ELIGIBLE,))

    def test_stale_slot_is_excluded(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(), self._slot(availability=SlotAvailability.STALE)
        )
        self.assertIn(SlotEligibilityReason.STALE, result.reasons)

    def test_unavailable_slot_is_excluded(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(), self._slot(availability=SlotAvailability.UNAVAILABLE)
        )
        self.assertIn(SlotEligibilityReason.UNAVAILABLE, result.reasons)

    def test_slot_before_pid_is_excluded(self) -> None:
        start = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
        result = evaluate_slot_eligibility(
            self._request(),
            self._slot(
                slot_start=start,
                slot_end=start + timedelta(minutes=30),
            ),
        )
        self.assertIn(SlotEligibilityReason.BEFORE_PID, result.reasons)

    def test_service_mismatch_is_excluded(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(), self._slot(service="DERMATOLOGY")
        )
        self.assertIn(SlotEligibilityReason.SERVICE_MISMATCH, result.reasons)

    def test_explicit_facility_constraint_mismatch_is_excluded(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(), self._slot(facility_id="550")
        )
        self.assertIn(SlotEligibilityReason.FACILITY_MISMATCH, result.reasons)

    def test_explicit_clinic_constraint_uses_facility_mismatch_reason(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(), self._slot(clinic_id="CARD-2")
        )
        self.assertIn(SlotEligibilityReason.FACILITY_MISMATCH, result.reasons)

    def test_unknown_patient_classification_fails_closed(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(
                patient_classification=PatientClinicClassification.UNKNOWN
            ),
            self._slot(),
        )
        self.assertIn(
            SlotEligibilityReason.PATIENT_CLASSIFICATION_UNKNOWN,
            result.reasons,
        )

    def test_classification_mismatch_is_excluded(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(
                patient_classification=PatientClinicClassification.ESTABLISHED
            ),
            self._slot(
                eligible_patient_classifications=(PatientClinicClassification.NEW,)
            ),
        )
        self.assertIn(
            SlotEligibilityReason.PATIENT_CLASSIFICATION_MISMATCH,
            result.reasons,
        )

    def test_empty_classification_allow_list_matches_nobody(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(),
            self._slot(eligible_patient_classifications=()),
        )
        self.assertIn(
            SlotEligibilityReason.PATIENT_CLASSIFICATION_MISMATCH,
            result.reasons,
        )

    def test_appointment_intent_mismatch_is_excluded(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(appointment_intent=AppointmentIntent.FOLLOW_UP),
            self._slot(
                eligible_appointment_intents=(
                    AppointmentIntent.INITIAL_CONSULT,
                )
            ),
        )
        self.assertIn(
            SlotEligibilityReason.APPOINTMENT_INTENT_MISMATCH,
            result.reasons,
        )

    def test_empty_intent_allow_list_means_no_intent_restriction(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(),
            self._slot(eligible_appointment_intents=()),
        )
        self.assertNotIn(
            SlotEligibilityReason.APPOINTMENT_INTENT_MISMATCH,
            result.reasons,
        )

    def test_template_mismatch_is_excluded(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(),
            self._slot(template_type=SlotTemplateType.FOLLOW_UP),
        )
        self.assertIn(SlotEligibilityReason.TEMPLATE_MISMATCH, result.reasons)

    def test_resource_mismatch_is_excluded(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(),
            self._slot(resource_type=ResourceType.RN),
        )
        self.assertIn(SlotEligibilityReason.RESOURCE_MISMATCH, result.reasons)

    def test_insufficient_duration_is_excluded(self) -> None:
        start = datetime(2026, 11, 5, 13, 0, tzinfo=timezone.utc)
        result = evaluate_slot_eligibility(
            self._request(required_duration_minutes=45),
            self._slot(
                slot_start=start,
                slot_end=start + timedelta(minutes=30),
                duration_minutes=30,
            ),
        )
        self.assertIn(
            SlotEligibilityReason.DURATION_INSUFFICIENT,
            result.reasons,
        )

    def test_required_modality_mismatch_is_excluded(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(required_modality="VIDEO"),
            self._slot(modality="IN_PERSON"),
        )
        self.assertIn(SlotEligibilityReason.MODALITY_MISMATCH, result.reasons)

    def test_preferences_do_not_override_eligibility(self) -> None:
        request = self._request(
            preferred_facility_ids=("550",),
            preferred_modality=("VIDEO",),
        )
        result = evaluate_slot_eligibility(
            request,
            self._slot(service="DERMATOLOGY"),
        )
        self.assertFalse(result.eligible)
        self.assertIn(SlotEligibilityReason.SERVICE_MISMATCH, result.reasons)

    def test_preferences_do_not_create_eligibility_failure(self) -> None:
        request = self._request(
            preferred_facility_ids=("550",),
            preferred_modality=("VIDEO",),
            preferred_days_of_week=("MONDAY",),
            preferred_time_of_day=("MORNING",),
        )
        result = evaluate_slot_eligibility(request, self._slot())
        self.assertTrue(result.eligible)

    def test_multiple_failures_are_preserved(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(required_duration_minutes=45),
            self._slot(
                availability=SlotAvailability.STALE,
                service="DERMATOLOGY",
            ),
        )
        self.assertFalse(result.eligible)
        self.assertIn(SlotEligibilityReason.STALE, result.reasons)
        self.assertIn(SlotEligibilityReason.SERVICE_MISMATCH, result.reasons)
        self.assertIn(
            SlotEligibilityReason.DURATION_INSUFFICIENT,
            result.reasons,
        )

    def test_match_scheduling_slots_preserves_input_order(self) -> None:
        slot_a = self._slot(slot_id="SLOT-A")
        slot_b = self._slot(
            slot_id="SLOT-B",
            service="DERMATOLOGY",
        )
        results = match_scheduling_slots(self._request(), (slot_a, slot_b))
        self.assertEqual([r.slot_id for r in results], ["SLOT-A", "SLOT-B"])
        self.assertTrue(results[0].eligible)
        self.assertFalse(results[1].eligible)

    def test_service_comparison_is_case_insensitive(self) -> None:
        result = evaluate_slot_eligibility(
            self._request(service="cardiology"),
            self._slot(service="CARDIOLOGY"),
        )
        self.assertTrue(result.eligible)


if __name__ == "__main__":
    unittest.main()
