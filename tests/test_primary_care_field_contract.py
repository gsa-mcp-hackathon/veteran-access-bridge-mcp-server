"""Tests for Issue #68 Primary Care field ownership contract."""

import unittest
from datetime import datetime, timezone

from veteran_access_bridge.domain import (
    FieldSource,
    PrimaryCareFieldName,
    PrimaryCareFieldValue,
    allowed_sources,
    field_ownership_summary,
)

NOW = datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc)


class PrimaryCareFieldContractTests(unittest.TestCase):
    def test_conversation_may_capture_veteran_preference(self):
        value = PrimaryCareFieldValue(
            field_name=PrimaryCareFieldName.VETERAN_PREFERRED_DAYPART,
            value="MORNING",
            source=FieldSource.CONVERSATION,
            captured_at=NOW,
            confidence=0.94,
        )
        self.assertEqual(value.value, "MORNING")
        self.assertEqual(value.source, FieldSource.CONVERSATION)

    def test_provider_requested_date_cannot_come_from_conversation(self):
        with self.assertRaisesRegex(ValueError, "cannot be populated from conversation"):
            PrimaryCareFieldValue(
                field_name=PrimaryCareFieldName.PROVIDER_REQUESTED_DATE,
                value="2026-11-10",
                source=FieldSource.CONVERSATION,
                captured_at=NOW,
            )

    def test_provider_requested_date_requires_governed_record_id(self):
        with self.assertRaisesRegex(ValueError, "require source_record_id"):
            PrimaryCareFieldValue(
                field_name=PrimaryCareFieldName.PROVIDER_REQUESTED_DATE,
                value="2026-11-10",
                source=FieldSource.GOVERNED_SOURCE,
                captured_at=NOW,
            )

        value = PrimaryCareFieldValue(
            field_name=PrimaryCareFieldName.PROVIDER_REQUESTED_DATE,
            value="2026-11-10",
            source=FieldSource.GOVERNED_SOURCE,
            captured_at=NOW,
            source_record_id="SYNTH-ORDER-PC-001",
        )
        self.assertEqual(value.source_record_id, "SYNTH-ORDER-PC-001")

    def test_new_established_cannot_be_inferred_from_conversation(self):
        with self.assertRaisesRegex(ValueError, "cannot be populated from conversation"):
            PrimaryCareFieldValue(
                field_name=PrimaryCareFieldName.PATIENT_CLASSIFICATION,
                value="ESTABLISHED",
                source=FieldSource.CONVERSATION,
                captured_at=NOW,
            )

    def test_eligibility_and_access_result_are_deterministic_only(self):
        for field_name in (
            PrimaryCareFieldName.ELIGIBLE_OPTIONS,
            PrimaryCareFieldName.EXCLUDED_OPTIONS,
            PrimaryCareFieldName.ACCESS_COMPARATOR_DATE,
            PrimaryCareFieldName.ACCESS_STANDARD_RESULT,
        ):
            with self.subTest(field_name=field_name):
                self.assertEqual(
                    allowed_sources(field_name),
                    frozenset({FieldSource.DETERMINISTIC_SERVICE}),
                )
                with self.assertRaises(ValueError):
                    PrimaryCareFieldValue(
                        field_name=field_name,
                        value="synthetic-value",
                        source=FieldSource.CONVERSATION,
                        captured_at=NOW,
                    )

    def test_verification_and_booking_cannot_be_conversation_derived(self):
        for field_name in (
            PrimaryCareFieldName.VERIFICATION_STATUS,
            PrimaryCareFieldName.BOOKING_STATUS,
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValueError):
                    PrimaryCareFieldValue(
                        field_name=field_name,
                        value="COMPLETE",
                        source=FieldSource.CONVERSATION,
                        captured_at=NOW,
                    )

    def test_veteran_selection_and_confirmation_require_veteran_action(self):
        for field_name in (
            PrimaryCareFieldName.VETERAN_SELECTED_OPTION,
            PrimaryCareFieldName.VETERAN_CONFIRMATION,
        ):
            with self.subTest(field_name=field_name):
                self.assertEqual(
                    allowed_sources(field_name),
                    frozenset({FieldSource.VETERAN_ACTION}),
                )

    def test_msa_approval_is_msa_owned(self):
        self.assertEqual(
            allowed_sources(PrimaryCareFieldName.MSA_APPROVAL),
            frozenset({FieldSource.MSA}),
        )
        with self.assertRaises(ValueError):
            PrimaryCareFieldValue(
                field_name=PrimaryCareFieldName.MSA_APPROVAL,
                value="APPROVED",
                source=FieldSource.DETERMINISTIC_SERVICE,
                captured_at=NOW,
            )

    def test_msa_may_correct_conversation_derived_field(self):
        value = PrimaryCareFieldValue(
            field_name=PrimaryCareFieldName.VETERAN_PREFERRED_DAYPART,
            value="AFTERNOON",
            source=FieldSource.MSA,
            captured_at=NOW,
            corrected_from_event_id="evt-pref-001",
        )
        self.assertEqual(value.corrected_from_event_id, "evt-pref-001")

    def test_correction_metadata_is_not_allowed_for_governed_fact(self):
        with self.assertRaises(ValueError):
            PrimaryCareFieldValue(
                field_name=PrimaryCareFieldName.PATIENT_CLASSIFICATION,
                value="ESTABLISHED",
                source=FieldSource.MSA,
                captured_at=NOW,
                corrected_from_event_id="evt-class-001",
            )

    def test_confidence_is_conversation_only_and_bounded(self):
        with self.assertRaisesRegex(ValueError, "conversation-derived"):
            PrimaryCareFieldValue(
                field_name=PrimaryCareFieldName.PROVIDER_REQUESTED_DATE,
                value="2026-11-10",
                source=FieldSource.GOVERNED_SOURCE,
                source_record_id="SYNTH-ORDER-PC-001",
                captured_at=NOW,
                confidence=1.0,
            )

        with self.assertRaisesRegex(ValueError, "between 0.0 and 1.0"):
            PrimaryCareFieldValue(
                field_name=PrimaryCareFieldName.VETERAN_PREFERRED_DATE,
                value="2026-11-12",
                source=FieldSource.CONVERSATION,
                captured_at=NOW,
                confidence=1.1,
            )

    def test_unknown_values_require_explicit_reason(self):
        with self.assertRaisesRegex(ValueError, "unknown_reason"):
            PrimaryCareFieldValue(
                field_name=PrimaryCareFieldName.VETERAN_PREFERRED_DATE,
                value=None,
                source=FieldSource.CONVERSATION,
                captured_at=NOW,
            )

        value = PrimaryCareFieldValue(
            field_name=PrimaryCareFieldName.VETERAN_PREFERRED_DATE,
            value=None,
            source=FieldSource.CONVERSATION,
            captured_at=NOW,
            unknown_reason="Veteran did not state a preferred date.",
        )
        self.assertIsNone(value.value)

    def test_non_synthetic_values_fail_closed_for_mvp(self):
        with self.assertRaisesRegex(ValueError, "must be synthetic"):
            PrimaryCareFieldValue(
                field_name=PrimaryCareFieldName.REQUEST_INTENT,
                value="SCHEDULE_PRIMARY_CARE",
                source=FieldSource.CONVERSATION,
                captured_at=NOW,
                synthetic=False,
            )

    def test_ownership_summary_covers_every_field(self):
        summary = field_ownership_summary()
        self.assertEqual(
            set(summary),
            {field_name.value for field_name in PrimaryCareFieldName},
        )
        self.assertTrue(all(summary[field] for field in summary))


if __name__ == "__main__":
    unittest.main()
