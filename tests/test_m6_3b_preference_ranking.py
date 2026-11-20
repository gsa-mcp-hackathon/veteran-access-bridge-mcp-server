"""M6.3b deterministic preference-ranking tests."""

import unittest
from datetime import date, datetime, timedelta, timezone

from veteran_access_bridge.domain.models import (
    AccessOption,
    CareCategory,
    OptionReadiness,
    PatientClinicClassification,
    RequestSource,
    ResourceType,
    SchedulingRequest,
    SchedulingSlot,
    SlotAvailability,
    SlotTemplateType,
    SourceProvenance,
)
from veteran_access_bridge.services.preference_ranking import rank_eligible_options

AS_OF = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def _request(**overrides):
    values = dict(
        request_id="REQ-RANK-001",
        case_id="CASE-RANK-001",
        patient_id="P1",
        request_source=RequestSource.VETERAN_REQUEST,
        care_category=CareCategory.PRIMARY_CARE,
        service="PRIMARY_CARE",
        canonical_pid=date(2026, 11, 1),
        patient_classification=PatientClinicClassification.ESTABLISHED,
        preferred_facility_ids=("VA-A",),
        preferred_modality=("IN_PERSON",),
        preferred_days_of_week=("MONDAY",),
        preferred_time_of_day=("MORNING",),
    )
    values.update(overrides)
    return SchedulingRequest(**values)


def _slot(
    slot_id,
    *,
    facility_id,
    start,
    modality="IN_PERSON",
):
    return SchedulingSlot(
        slot_id=slot_id,
        source_system="VISTA_ISS",
        source_record_id=slot_id,
        facility_id=facility_id,
        facility_name=f"Synthetic {facility_id}",
        clinic_id=None,
        stop_code=None,
        stop_code_group=None,
        service="PRIMARY_CARE",
        resource_id=f"RES-{slot_id}",
        resource_name="Synthetic PCP",
        resource_type=ResourceType.PHYSICIAN,
        template_type=SlotTemplateType.ESTABLISHED,
        modality=modality,
        slot_start=start,
        slot_end=start + timedelta(minutes=30),
        duration_minutes=30,
        availability=SlotAvailability.AVAILABLE,
        eligible_patient_classifications=(
            PatientClinicClassification.ESTABLISHED,
        ),
        provenance=SourceProvenance(
            source_system="VISTA_ISS",
            source_record_id=slot_id,
            retrieved_at=AS_OF,
            synthetic=True,
            environment="synthetic-test",
            freshness="fixture-current",
        ),
    )


def _option(slot):
    return AccessOption(
        option_id=f"OPT-{slot.slot_id}",
        source_system=slot.source_system,
        source_record_id=slot.source_record_id,
        specialty=slot.service,
        facility_name=slot.facility_name,
        facility_id=slot.facility_id,
        slot_start=slot.slot_start,
        slot_end=slot.slot_end,
        availability_status="AVAILABLE",
        readiness=OptionReadiness.AVAILABLE,
        provenance=slot.provenance,
        provider=slot.resource_name,
        duration_minutes=slot.duration_minutes,
    )


class TestM63bPreferenceRanking(unittest.TestCase):
    def test_preferences_reorder_but_preserve_exact_eligible_set(self):
        monday_morning = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
        sunday_afternoon = datetime(2026, 11, 1, 14, 0, tzinfo=timezone.utc)

        preferred = _slot(
            "SLOT-PREFERRED",
            facility_id="VA-A",
            start=monday_morning,
        )
        nonpreferred = _slot(
            "SLOT-NONPREFERRED",
            facility_id="VA-B",
            start=sunday_afternoon,
            modality="VIDEO",
        )

        eligible = (_option(nonpreferred), _option(preferred))
        ranked = rank_eligible_options(
            _request(),
            (nonpreferred, preferred),
            eligible,
        )

        self.assertEqual(
            {item.option.option_id for item in ranked},
            {option.option_id for option in eligible},
        )
        self.assertEqual(len(ranked), len(eligible))
        self.assertEqual(ranked[0].option.option_id, "OPT-SLOT-PREFERRED")
        self.assertEqual(ranked[0].preference_match_count, 4)
        self.assertTrue(ranked[0].fully_matches_preferences)
        self.assertEqual(
            ranked[0].matched_dimensions,
            ("FACILITY", "MODALITY", "DAY_OF_WEEK", "TIME_OF_DAY"),
        )
        self.assertEqual(ranked[1].preference_match_count, 0)

    def test_omitted_preferences_are_neutral_and_earlier_slot_breaks_tie(self):
        later = _slot(
            "SLOT-LATER",
            facility_id="VA-A",
            start=datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc),
        )
        earlier = _slot(
            "SLOT-EARLIER",
            facility_id="VA-B",
            start=datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
        )
        request = _request(
            preferred_facility_ids=(),
            preferred_modality=(),
            preferred_days_of_week=(),
            preferred_time_of_day=(),
        )

        ranked = rank_eligible_options(
            request,
            (later, earlier),
            (_option(later), _option(earlier)),
        )

        self.assertEqual(
            [item.option.option_id for item in ranked],
            ["OPT-SLOT-EARLIER", "OPT-SLOT-LATER"],
        )
        self.assertTrue(
            all(item.explicit_preference_count == 0 for item in ranked)
        )
        self.assertTrue(
            all(not item.fully_matches_preferences for item in ranked)
        )

    def test_missing_slot_metadata_cannot_fabricate_modality_match(self):
        slot = _slot(
            "SLOT-ONE",
            facility_id="VA-A",
            start=datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc),
        )
        option = _option(slot)
        request = _request(
            preferred_facility_ids=(),
            preferred_days_of_week=(),
            preferred_time_of_day=(),
            preferred_modality=("IN_PERSON",),
        )

        ranked = rank_eligible_options(request, (), (option,))

        self.assertEqual(ranked[0].matched_dimensions, ())
        self.assertEqual(ranked[0].unmatched_dimensions, ("MODALITY",))
        self.assertEqual(ranked[0].preference_match_count, 0)


if __name__ == "__main__":
    unittest.main()
