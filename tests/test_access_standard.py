from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from veteran_access_bridge.domain.models import (
    AccessOption,
    OptionReadiness,
    SourceProvenance,
)
from veteran_access_bridge.services.access_standard import evaluate_access_standard


AS_OF = datetime(2026, 10, 16, tzinfo=timezone.utc)
PID = date(2026, 10, 1)


def _option(
    *,
    option_id: str,
    days_after_pid: int,
    source_system: str = "VISTA_ISS",
    readiness: OptionReadiness = OptionReadiness.AVAILABLE,
) -> AccessOption:
    start = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc) + timedelta(
        days=days_after_pid
    )
    return AccessOption(
        option_id=option_id,
        source_system=source_system,
        source_record_id=f"record-{option_id}",
        specialty="Cardiology",
        facility_name="Synthetic VA Facility",
        facility_id="SYN-VA-1",
        slot_start=start,
        slot_end=start + timedelta(minutes=30),
        availability_status="AVAILABLE",
        readiness=readiness,
        provenance=SourceProvenance(
            source_system=source_system,
            source_record_id=f"record-{option_id}",
            retrieved_at=AS_OF,
            synthetic=True,
            environment="synthetic-test",
            freshness="fixture-current",
        ),
    )


class AccessStandardTests(unittest.TestCase):
    def test_specialty_within_28_days_has_no_review_signal(self) -> None:
        result = evaluate_access_standard(
            case_id="CASE-1",
            patient_id="P1",
            consult_id="C1",
            care_category="SPECIALTY",
            patient_indicated_date=PID,
            options=(_option(option_id="o1", days_after_pid=28),),
        )
        self.assertFalse(result.wait_standard_exceeded)
        self.assertFalse(result.community_care_review_recommended)
        self.assertEqual(result.community_care_authorization_status, "NOT_EVALUATED")

    def test_specialty_beyond_28_days_recommends_review(self) -> None:
        result = evaluate_access_standard(
            case_id="CASE-1",
            patient_id="P1",
            consult_id="C1",
            care_category="SPECIALTY",
            patient_indicated_date=PID,
            options=(_option(option_id="o1", days_after_pid=29),),
        )
        self.assertTrue(result.wait_standard_exceeded)
        self.assertTrue(result.community_care_review_recommended)
        self.assertFalse(hasattr(result, "authorization_id"))

    def test_primary_uses_20_day_standard(self) -> None:
        within = evaluate_access_standard(
            case_id="CASE-1",
            patient_id="P1",
            consult_id="C1",
            care_category="PRIMARY",
            patient_indicated_date=PID,
            options=(_option(option_id="o1", days_after_pid=20),),
        )
        beyond = evaluate_access_standard(
            case_id="CASE-1",
            patient_id="P1",
            consult_id="C1",
            care_category="PRIMARY",
            patient_indicated_date=PID,
            options=(_option(option_id="o2", days_after_pid=21),),
        )
        self.assertFalse(within.wait_standard_exceeded)
        self.assertTrue(beyond.wait_standard_exceeded)

    def test_stale_and_community_options_are_not_comparators(self) -> None:
        result = evaluate_access_standard(
            case_id="CASE-1",
            patient_id="P1",
            consult_id="C1",
            care_category="SPECIALTY",
            patient_indicated_date=PID,
            options=(
                _option(
                    option_id="stale",
                    days_after_pid=5,
                    readiness=OptionReadiness.STALE,
                ),
                _option(
                    option_id="community",
                    days_after_pid=10,
                    source_system="COMMUNITY_CARE_EPS",
                ),
                _option(option_id="valid", days_after_pid=35),
            ),
        )
        self.assertEqual(result.earliest_eligible_va_option_id, "valid")
        self.assertEqual(result.earliest_eligible_va_wait_days, 35)
        self.assertTrue(result.community_care_review_recommended)

    def test_pid_is_preserved_and_provenance_returned(self) -> None:
        result = evaluate_access_standard(
            case_id="CASE-1",
            patient_id="P1",
            consult_id="C1",
            care_category="SPECIALTY CARE",
            patient_indicated_date=PID,
            options=(_option(option_id="o1", days_after_pid=30),),
        )
        self.assertEqual(result.patient_indicated_date, PID)
        self.assertEqual(result.comparator_source_system, "VISTA_ISS")
        self.assertEqual(result.comparator_source_record_id, "record-o1")
        self.assertEqual(result.comparator_freshness, "fixture-current")

    def test_no_eligible_internal_option_recommends_review_without_authorization(self) -> None:
        result = evaluate_access_standard(
            case_id="CASE-1",
            patient_id="P1",
            consult_id="C1",
            care_category="MENTAL_HEALTH",
            patient_indicated_date=PID,
            options=(),
        )
        self.assertTrue(result.wait_standard_exceeded)
        self.assertTrue(result.community_care_review_recommended)
        self.assertEqual(result.community_care_authorization_status, "NOT_EVALUATED")
        self.assertIsNone(result.earliest_eligible_va_option_id)


if __name__ == "__main__":
    unittest.main()
