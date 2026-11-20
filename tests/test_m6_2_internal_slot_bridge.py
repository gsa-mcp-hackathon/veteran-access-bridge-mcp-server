"""M6.2d internal slot bridge tests."""

import unittest
from datetime import date, datetime, timezone

from veteran_access_bridge.adapters.federal_ehr import FederalEHRAdapter
from veteran_access_bridge.adapters.vista import VistAAdapter
from veteran_access_bridge.domain.models import (
    AppointmentIntent, CareCategory, PatientClinicClassification,
    RequestSource, ResourceType, SchedulingRequest, SlotAvailability,
    SlotTemplateType,
)
from veteran_access_bridge.services.internal_slot_bridge import (
    search_internal_eligible_options,
)

AS_OF = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def request(**overrides):
    values = dict(
        request_id="REQ-CARD-M62D-001",
        case_id="DEMO-CARD-5000335-001",
        patient_id="5000335",
        request_source=RequestSource.CONSULT,
        care_category=CareCategory.SPECIALTY,
        service="Cardiology",
        canonical_pid=date(2026, 10, 1),
        patient_classification=PatientClinicClassification.NEW,
        appointment_intent=AppointmentIntent.INITIAL_CONSULT,
        consult_id="CONSULT-CARD-5000335-001",
        required_duration_minutes=30,
        required_resource_types=(ResourceType.PHYSICIAN,),
        required_template_types=(SlotTemplateType.CONSULT,),
        required_modality="IN_PERSON",
    )
    values.update(overrides)
    return SchedulingRequest(**values)


class TestM62dBridge(unittest.TestCase):
    def test_vista_slot_metadata_and_stale(self):
        slots = VistAAdapter(as_of=AS_OF).search_scheduling_slots(
            "5000335", "Cardiology", as_of=AS_OF
        )
        self.assertEqual(len(slots), 3)
        self.assertEqual(slots[0].template_type, SlotTemplateType.CONSULT)
        self.assertEqual(slots[0].resource_type, ResourceType.PHYSICIAN)
        self.assertEqual(
            slots[0].eligible_patient_classifications,
            (PatientClinicClassification.NEW,),
        )
        stale = next(s for s in slots if s.slot_id.endswith("-002"))
        self.assertEqual(stale.availability, SlotAvailability.STALE)

    def test_federal_slot_metadata(self):
        slots = FederalEHRAdapter(as_of=AS_OF).search_scheduling_slots(
            "5000335", "Cardiology", as_of=AS_OF
        )
        self.assertEqual(len(slots), 2)
        self.assertTrue(all(s.template_type is SlotTemplateType.CONSULT for s in slots))

    def test_existing_access_options_unchanged(self):
        vista = VistAAdapter(as_of=AS_OF).search(
            "5000335", "Cardiology", as_of=AS_OF
        )
        fehr = FederalEHRAdapter(as_of=AS_OF).search(
            "5000335", "Cardiology", as_of=AS_OF
        )
        self.assertEqual([o.wait_days for o in vista.options], [25, 5, 32])
        self.assertEqual([o.wait_days for o in fehr.options], [20, 27])

    def test_bridge_returns_only_eligible_internal_options(self):
        options = search_internal_eligible_options(request(), _as_of=AS_OF)
        self.assertEqual(
            [o.option_id for o in options],
            [
                "OPT-VISTA-SLOT-CARD-5000335-001",
                "OPT-VISTA-SLOT-CARD-5000335-003",
                "OPT-FEHR-SLOT-CARD-5000335-001",
                "OPT-FEHR-SLOT-CARD-5000335-002",
            ],
        )
        self.assertNotIn("COMMUNITY_CARE_EPS", {o.source_system for o in options})

    def test_incompatible_request_fails_closed(self):
        options = search_internal_eligible_options(
            request(appointment_intent=AppointmentIntent.FOLLOW_UP),
            _as_of=AS_OF,
        )
        self.assertEqual(options, ())

    def test_unavailable_internal_sources_do_not_fall_back_to_community(self):
        options = search_internal_eligible_options(
            request(),
            _vista=VistAAdapter(simulate_unavailable=True, as_of=AS_OF),
            _federal_ehr=FederalEHRAdapter(simulate_unavailable=True, as_of=AS_OF),
            _as_of=AS_OF,
        )
        self.assertEqual(options, ())


if __name__ == "__main__":
    unittest.main()
