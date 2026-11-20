from datetime import datetime, timezone
import unittest

from veteran_access_bridge.domain.models import (
    ClinicalConsult,
    PatientContext,
    WorkflowState,
)
from veteran_access_bridge.domain.workflow import determine_workflow_state


class CardiologyWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patient = PatientContext(
            patient_id="5000335",
            display_name="Mr. Mariano761 Ruelas156",
            birth_date="1907-11-20",
            gender="male",
            city="Colorado Springs",
            state="CO",
            postal_code="80809",
            active_conditions=("Atrial Fibrillation",),
        )

    def test_valid_cardiology_consult_is_ready_to_search(self) -> None:
        consult = ClinicalConsult(
            consult_id="CONSULT-CARD-5000335-001",
            patient_id="5000335",
            specialty="Cardiology",
            status="ACTIVE",
            requested_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
            valid=True,
        )
        self.assertEqual(
            determine_workflow_state(self.patient, consult),
            WorkflowState.READY_TO_SEARCH,
        )

    def test_missing_consult_requires_clinical_review(self) -> None:
        self.assertEqual(
            determine_workflow_state(self.patient, None),
            WorkflowState.CLINICAL_REVIEW_REQUIRED,
        )

    def test_condition_does_not_substitute_for_consult(self) -> None:
        self.assertTrue(self.patient.has_cardiology_context)
        self.assertEqual(
            determine_workflow_state(self.patient, None),
            WorkflowState.CLINICAL_REVIEW_REQUIRED,
        )

    def test_blocked_consult_remains_pending(self) -> None:
        consult = ClinicalConsult(
            consult_id="CONSULT-CARD-5000335-002",
            patient_id="5000335",
            specialty="Cardiology",
            status="ACTIVE",
            requested_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
            valid=True,
            blockers=("clinical-review",),
        )
        self.assertEqual(
            determine_workflow_state(self.patient, consult),
            WorkflowState.CONSULT_PENDING,
        )


if __name__ == "__main__":
    unittest.main()
