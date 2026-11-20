"""M6.2b clinic classification service tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from veteran_access_bridge.domain.models import (
    PatientClinicClassification,
    PatientClinicRelationship,
)
from veteran_access_bridge.services.clinic_classification import (
    classify_patient_clinic_relationship,
)

_AS_OF = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


class TestClinicClassification(unittest.TestCase):

    def _relationship(self, **overrides: object) -> PatientClinicRelationship:
        values: dict[str, object] = {
            "patient_id": "5000335",
            "facility_id": "549",
            "stop_code": "303",
            "stop_code_group": "CARDIOLOGY",
            "last_completed_visit": None,
            "as_of": _AS_OF,
        }
        values.update(overrides)
        return PatientClinicRelationship(**values)  # type: ignore[arg-type]

    def test_no_prior_completed_visit_is_new(self) -> None:
        result = classify_patient_clinic_relationship(self._relationship())
        self.assertEqual(result, PatientClinicClassification.NEW)

    def test_visit_within_36_months_is_established(self) -> None:
        result = classify_patient_clinic_relationship(
            self._relationship(
                last_completed_visit=datetime(
                    2024, 3, 10, 9, 0, tzinfo=timezone.utc
                )
            )
        )
        self.assertEqual(result, PatientClinicClassification.ESTABLISHED)

    def test_visit_exactly_36_month_boundary_is_established(self) -> None:
        result = classify_patient_clinic_relationship(
            self._relationship(
                last_completed_visit=datetime(
                    2023, 10, 23, 12, 0, tzinfo=timezone.utc
                )
            )
        )
        self.assertEqual(result, PatientClinicClassification.ESTABLISHED)

    def test_visit_older_than_36_months_is_new(self) -> None:
        result = classify_patient_clinic_relationship(
            self._relationship(
                last_completed_visit=datetime(
                    2023, 10, 23, 11, 59, tzinfo=timezone.utc
                )
            )
        )
        self.assertEqual(result, PatientClinicClassification.NEW)

    def test_missing_stop_code_and_group_is_unknown(self) -> None:
        result = classify_patient_clinic_relationship(
            self._relationship(stop_code=None, stop_code_group=None)
        )
        self.assertEqual(result, PatientClinicClassification.UNKNOWN)

    def test_blank_stop_code_and_group_is_unknown(self) -> None:
        result = classify_patient_clinic_relationship(
            self._relationship(stop_code=" ", stop_code_group=" ")
        )
        self.assertEqual(result, PatientClinicClassification.UNKNOWN)

    def test_stop_code_group_alone_is_sufficient_context(self) -> None:
        result = classify_patient_clinic_relationship(
            self._relationship(
                stop_code=None,
                stop_code_group="CARDIOLOGY",
                last_completed_visit=datetime(
                    2025, 1, 5, 9, 0, tzinfo=timezone.utc
                ),
            )
        )
        self.assertEqual(result, PatientClinicClassification.ESTABLISHED)

    def test_stop_code_alone_is_sufficient_context(self) -> None:
        result = classify_patient_clinic_relationship(
            self._relationship(
                stop_code="303",
                stop_code_group=None,
                last_completed_visit=None,
            )
        )
        self.assertEqual(result, PatientClinicClassification.NEW)

    def test_future_completed_visit_is_unknown(self) -> None:
        result = classify_patient_clinic_relationship(
            self._relationship(
                last_completed_visit=datetime(
                    2026, 10, 24, 12, 0, tzinfo=timezone.utc
                )
            )
        )
        self.assertEqual(result, PatientClinicClassification.UNKNOWN)

    def test_leap_day_boundary_is_calendar_safe(self) -> None:
        relationship = self._relationship(
            as_of=datetime(2028, 2, 29, 12, 0, tzinfo=timezone.utc),
            last_completed_visit=datetime(
                2025, 2, 28, 12, 0, tzinfo=timezone.utc
            ),
        )
        result = classify_patient_clinic_relationship(relationship)
        self.assertEqual(result, PatientClinicClassification.ESTABLISHED)


if __name__ == "__main__":
    unittest.main()
