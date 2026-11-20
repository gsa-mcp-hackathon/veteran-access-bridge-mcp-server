"""M6.2 closeout Primary Care scheduling scenarios."""

import unittest
from datetime import date, datetime, timedelta, timezone

from veteran_access_bridge.domain.models import (
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
from veteran_access_bridge.services.slot_matching import evaluate_slot_eligibility

START = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)


def pc_request(classification, template, duration=30):
    return SchedulingRequest(
        request_id=f"REQ-PC-{classification.value}",
        case_id="DEMO-PC-001",
        patient_id="5000999",
        request_source=RequestSource.VETERAN_REQUEST,
        care_category=CareCategory.PRIMARY_CARE,
        service="PRIMARY_CARE",
        canonical_pid=date(2026, 11, 1),
        facility_id="PC-VA-001",
        clinic_id="PC-CLINIC-1",
        stop_code="323",
        stop_code_group="PRIMARY_CARE",
        patient_classification=classification,
        required_duration_minutes=duration,
        required_resource_types=(ResourceType.PHYSICIAN, ResourceType.NP),
        required_template_types=(template,),
        required_modality="IN_PERSON",
    )


def pc_slot(template, classifications, minutes=30):
    return SchedulingSlot(
        slot_id=f"SLOT-PC-{template.value}",
        source_system="SYNTHETIC_PRIMARY_CARE",
        source_record_id=f"SRC-{template.value}",
        facility_id="PC-VA-001",
        facility_name="Synthetic Primary Care Clinic",
        clinic_id="PC-CLINIC-1",
        stop_code="323",
        stop_code_group="PRIMARY_CARE",
        service="PRIMARY_CARE",
        resource_id="PC-PROV-1",
        resource_name="Synthetic PCP",
        resource_type=ResourceType.PHYSICIAN,
        template_type=template,
        modality="IN_PERSON",
        slot_start=START,
        slot_end=START + timedelta(minutes=minutes),
        duration_minutes=minutes,
        availability=SlotAvailability.AVAILABLE,
        eligible_patient_classifications=classifications,
    )


class TestPrimaryCareScenarios(unittest.TestCase):
    def test_established_primary_care_matches_established_block(self):
        result = evaluate_slot_eligibility(
            pc_request(PatientClinicClassification.ESTABLISHED, SlotTemplateType.ESTABLISHED),
            pc_slot(
                SlotTemplateType.ESTABLISHED,
                (PatientClinicClassification.ESTABLISHED,),
            ),
        )
        self.assertTrue(result.eligible)

    def test_established_primary_care_rejects_new_patient_block(self):
        result = evaluate_slot_eligibility(
            pc_request(PatientClinicClassification.ESTABLISHED, SlotTemplateType.ESTABLISHED),
            pc_slot(
                SlotTemplateType.NEW_PATIENT,
                (PatientClinicClassification.NEW,),
            ),
        )
        self.assertFalse(result.eligible)
        self.assertIn(SlotEligibilityReason.PATIENT_CLASSIFICATION_MISMATCH, result.reasons)
        self.assertIn(SlotEligibilityReason.TEMPLATE_MISMATCH, result.reasons)

    def test_new_primary_care_matches_new_patient_block(self):
        result = evaluate_slot_eligibility(
            pc_request(PatientClinicClassification.NEW, SlotTemplateType.NEW_PATIENT, 60),
            pc_slot(
                SlotTemplateType.NEW_PATIENT,
                (PatientClinicClassification.NEW,),
                60,
            ),
        )
        self.assertTrue(result.eligible)

    def test_new_primary_care_rejects_short_block(self):
        result = evaluate_slot_eligibility(
            pc_request(PatientClinicClassification.NEW, SlotTemplateType.NEW_PATIENT, 60),
            pc_slot(
                SlotTemplateType.NEW_PATIENT,
                (PatientClinicClassification.NEW,),
                30,
            ),
        )
        self.assertIn(SlotEligibilityReason.DURATION_INSUFFICIENT, result.reasons)

    def test_unknown_primary_care_classification_fails_closed(self):
        result = evaluate_slot_eligibility(
            pc_request(PatientClinicClassification.UNKNOWN, SlotTemplateType.NEW_PATIENT),
            pc_slot(
                SlotTemplateType.NEW_PATIENT,
                (PatientClinicClassification.NEW,),
            ),
        )
        self.assertIn(SlotEligibilityReason.PATIENT_CLASSIFICATION_UNKNOWN, result.reasons)


if __name__ == "__main__":
    unittest.main()
