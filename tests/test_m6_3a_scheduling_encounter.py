"""M6.3a Scheduling Encounter composition tests."""

import unittest
from datetime import date, datetime, timedelta, timezone

from veteran_access_bridge.domain.models import (
    AccessOption,
    AppointmentIntent,
    ActorRole,
    CareCategory,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    ClinicalConsult,
    OptionReadiness,
    PatientClinicClassification,
    PatientClinicRelationship,
    PatientContext,
    RequestSource,
    ResourceType,
    SchedulingRequest,
    SchedulingSlot,
    SlotAvailability,
    SlotEligibilityReason,
    SlotTemplateType,
    SourceProvenance,
    SourceSearchResult,
    SourceSearchStatus,
    WorkflowState,
)
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.scheduling_encounter import (
    SchedulingEncounterState,
    assemble_scheduling_encounter,
)

AS_OF = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def cardiology_request(**overrides):
    values = dict(
        request_id="REQ-CARD-M63A-001",
        case_id="DEMO-CARD-5000335-001",
        patient_id="5000335",
        request_source=RequestSource.CONSULT,
        care_category=CareCategory.SPECIALTY,
        service="Cardiology",
        canonical_pid=date(2026, 10, 1),
        patient_classification=PatientClinicClassification.UNKNOWN,
        appointment_intent=AppointmentIntent.INITIAL_CONSULT,
        consult_id="CONSULT-CARD-5000335-001",
        required_duration_minutes=30,
        required_resource_types=(ResourceType.PHYSICIAN,),
        required_template_types=(SlotTemplateType.CONSULT,),
        required_modality="IN_PERSON",
        preferred_time_of_day=("MORNING",),
    )
    values.update(overrides)
    return SchedulingRequest(**values)


def cardiology_patient():
    return PatientContext(
        patient_id="5000335",
        display_name="Synthetic Veteran",
        birth_date="1970-01-01",
        gender="M",
        city="Denver",
        state="CO",
        postal_code="80200",
        active_conditions=("Atrial fibrillation",),
    )


def cardiology_consult():
    return ClinicalConsult(
        consult_id="CONSULT-CARD-5000335-001",
        patient_id="5000335",
        specialty="Cardiology",
        status="ACTIVE",
        requested_at=datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc),
        valid=True,
    )


def cardiology_relationship(**overrides):
    values = dict(
        patient_id="5000335",
        facility_id="549",
        stop_code="303",
        stop_code_group="CARDIOLOGY",
        last_completed_visit=None,
        as_of=AS_OF,
    )
    values.update(overrides)
    return PatientClinicRelationship(**values)


class _PrimaryCareVista:
    def search_scheduling_slots(self, patient_id, specialty, *, as_of=None):
        start = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)
        provenance = SourceProvenance(
            source_system="VISTA_ISS",
            source_record_id="PC-SLOT-001",
            retrieved_at=as_of,
            synthetic=True,
            environment="synthetic-test",
            freshness="fixture-current",
        )
        return (
            SchedulingSlot(
                slot_id="PC-SLOT-001",
                source_system="VISTA_ISS",
                source_record_id="PC-SLOT-001",
                facility_id="PC-VA-001",
                facility_name="Synthetic Primary Care Clinic",
                clinic_id="PC-CLINIC-1",
                stop_code="323",
                stop_code_group="PRIMARY_CARE",
                service="PRIMARY_CARE",
                resource_id="PC-PROV-1",
                resource_name="Synthetic PCP",
                resource_type=ResourceType.PHYSICIAN,
                template_type=SlotTemplateType.ESTABLISHED,
                modality="IN_PERSON",
                slot_start=start,
                slot_end=start + timedelta(minutes=30),
                duration_minutes=30,
                availability=SlotAvailability.AVAILABLE,
                eligible_patient_classifications=(
                    PatientClinicClassification.ESTABLISHED,
                ),
                provenance=provenance,
            ),
        )

    def search(self, patient_id, specialty, *, as_of=None):
        start = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)
        provenance = SourceProvenance(
            source_system="VISTA_ISS",
            source_record_id="PC-SLOT-001",
            retrieved_at=as_of,
            synthetic=True,
            environment="synthetic-test",
            freshness="fixture-current",
        )
        option = AccessOption(
            option_id="OPT-PC-SLOT-001",
            source_system="VISTA_ISS",
            source_record_id="PC-SLOT-001",
            specialty="PRIMARY_CARE",
            facility_name="Synthetic Primary Care Clinic",
            facility_id="PC-VA-001",
            slot_start=start,
            slot_end=start + timedelta(minutes=30),
            availability_status="AVAILABLE",
            readiness=OptionReadiness.AVAILABLE,
            provenance=provenance,
            provider="Synthetic PCP",
            duration_minutes=30,
        )
        return SourceSearchResult(
            source_system="VISTA_ISS",
            status=SourceSearchStatus.SUCCESS,
            retrieved_at=as_of,
            options=(option,),
        )


class _NoFederalSlots:
    def search_scheduling_slots(self, patient_id, specialty, *, as_of=None):
        return ()

    def search(self, patient_id, specialty, *, as_of=None):
        return SourceSearchResult(
            source_system="FEDERAL_EHR_FHIR",
            status=SourceSearchStatus.NO_SLOTS,
            retrieved_at=as_of,
        )


class TestM63aSchedulingEncounter(unittest.TestCase):
    def test_cardiology_encounter_composes_m61_and_m62(self):
        encounter = assemble_scheduling_encounter(
            request=cardiology_request(),
            patient=cardiology_patient(),
            consult=cardiology_consult(),
            relationship=cardiology_relationship(),
            as_of=AS_OF,
        )

        self.assertEqual(encounter.workflow_state, WorkflowState.READY_TO_SEARCH)
        self.assertEqual(
            encounter.encounter_state,
            SchedulingEncounterState.OPTIONS_ASSEMBLED,
        )
        self.assertEqual(
            encounter.patient_classification,
            PatientClinicClassification.NEW,
        )
        self.assertEqual(len(encounter.slots), 5)
        self.assertEqual(len(encounter.slot_eligibility), 5)
        self.assertEqual(len(encounter.eligible_options), 4)
        self.assertTrue(
            any(
                SlotEligibilityReason.STALE in result.reasons
                for result in encounter.slot_eligibility
            )
        )
        self.assertTrue(encounter.preferences_applied)
        self.assertEqual(len(encounter.ranked_options), len(encounter.eligible_options))
        self.assertEqual(encounter.request.canonical_pid, date(2026, 10, 1))

        assessment = encounter.access_standard
        self.assertIsNotNone(assessment)
        self.assertEqual(assessment.standard_days, 28)
        self.assertEqual(assessment.earliest_eligible_va_wait_days, 35)
        self.assertEqual(
            assessment.comparator_source_system,
            "FEDERAL_EHR_FHIR",
        )
        self.assertEqual(
            assessment.earliest_eligible_va_option_id,
            "OPT-FEHR-SLOT-CARD-5000335-001",
        )
        self.assertEqual(
            encounter.ranked_options[0].option.option_id,
            "OPT-VISTA-SLOT-CARD-5000335-001",
        )
        self.assertTrue(assessment.wait_standard_exceeded)
        self.assertTrue(assessment.community_care_review_recommended)
        self.assertEqual(
            assessment.community_care_authorization_status,
            "NOT_EVALUATED",
        )
        self.assertNotIn(
            "COMMUNITY_CARE_EPS",
            {option.source_system for option in encounter.eligible_options},
        )

    def test_primary_care_encounter_does_not_require_specialty_consult(self):
        patient = PatientContext(
            patient_id="5000999",
            display_name="Synthetic Primary Care Veteran",
            birth_date="1980-01-01",
            gender="F",
            city="Denver",
            state="CO",
            postal_code="80200",
        )
        request = SchedulingRequest(
            request_id="REQ-PC-M63A-001",
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
            required_duration_minutes=30,
            required_resource_types=(ResourceType.PHYSICIAN,),
            required_template_types=(SlotTemplateType.ESTABLISHED,),
            required_modality="IN_PERSON",
            preferred_days_of_week=("MONDAY", "TUESDAY"),
        )
        relationship = PatientClinicRelationship(
            patient_id="5000999",
            facility_id="PC-VA-001",
            stop_code="323",
            stop_code_group="PRIMARY_CARE",
            last_completed_visit=datetime(
                2025, 7, 1, 15, 0, tzinfo=timezone.utc
            ),
            as_of=AS_OF,
        )

        encounter = assemble_scheduling_encounter(
            request=request,
            patient=patient,
            relationship=relationship,
            as_of=AS_OF,
            _vista=_PrimaryCareVista(),
            _federal_ehr=_NoFederalSlots(),
        )

        self.assertEqual(encounter.workflow_state, WorkflowState.READY_TO_SEARCH)
        self.assertEqual(
            encounter.patient_classification,
            PatientClinicClassification.ESTABLISHED,
        )
        self.assertEqual(len(encounter.eligible_options), 1)
        self.assertTrue(encounter.preferences_applied)
        self.assertEqual(len(encounter.ranked_options), len(encounter.eligible_options))

        assessment = encounter.access_standard
        self.assertIsNotNone(assessment)
        self.assertEqual(assessment.care_category, "PRIMARY")
        self.assertEqual(assessment.standard_days, 20)
        self.assertEqual(assessment.earliest_eligible_va_wait_days, 14)
        self.assertFalse(assessment.wait_standard_exceeded)
        self.assertFalse(assessment.community_care_review_recommended)

    def test_unknown_clinic_classification_fails_closed_before_search(self):
        encounter = assemble_scheduling_encounter(
            request=cardiology_request(),
            patient=cardiology_patient(),
            consult=cardiology_consult(),
            relationship=cardiology_relationship(
                stop_code=None,
                stop_code_group=None,
            ),
            as_of=AS_OF,
        )

        self.assertEqual(
            encounter.encounter_state,
            SchedulingEncounterState.BLOCKED,
        )
        self.assertEqual(
            encounter.patient_classification,
            PatientClinicClassification.UNKNOWN,
        )
        self.assertIn(
            "PATIENT_CLINIC_CLASSIFICATION_UNKNOWN",
            encounter.blockers,
        )
        self.assertEqual(encounter.slots, ())
        self.assertEqual(encounter.eligible_options, ())
        self.assertIsNone(encounter.access_standard)

    def test_persisted_lifecycle_projects_ready_for_approval_without_writes(self):
        events = CaseEventStore()
        case_id = "DEMO-PC-001"
        steps = (
            (
                CaseLifecycleState.REQUEST_RECEIVED,
                CaseLifecycleState.READY_TO_SEARCH,
                CaseEventType.WORKFLOW_GATE_EVALUATED,
            ),
            (
                CaseLifecycleState.READY_TO_SEARCH,
                CaseLifecycleState.VA_OPTIONS_AVAILABLE,
                CaseEventType.SEARCH_EXECUTED,
            ),
            (
                CaseLifecycleState.VA_OPTIONS_AVAILABLE,
                CaseLifecycleState.READY_FOR_HANDOFF,
                CaseEventType.OPTIONS_ASSESSED,
            ),
            (
                CaseLifecycleState.READY_FOR_HANDOFF,
                CaseLifecycleState.HUMAN_REVIEW,
                CaseEventType.HANDOFF_PREPARED,
            ),
            (
                CaseLifecycleState.HUMAN_REVIEW,
                CaseLifecycleState.OPTION_SELECTED,
                CaseEventType.OPTION_SELECTED,
            ),
            (
                CaseLifecycleState.OPTION_SELECTED,
                CaseLifecycleState.VERIFIED_BOOKABLE,
                CaseEventType.VERIFICATION_PASSED,
            ),
            (
                CaseLifecycleState.VERIFIED_BOOKABLE,
                CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
                CaseEventType.VETERAN_CONFIRMATION_REQUESTED,
            ),
            (
                CaseLifecycleState.PENDING_VETERAN_CONFIRMATION,
                CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
                CaseEventType.VETERAN_CONFIRMED,
            ),
        )
        for index, (from_state, to_state, event_type) in enumerate(steps):
            events.append(
                CaseEvent(
                    event_id=f"m63c-{index}",
                    case_id=case_id,
                    event_type=event_type,
                    from_state=from_state,
                    to_state=to_state,
                    actor_role=(
                        ActorRole.VETERAN
                        if event_type is CaseEventType.VETERAN_CONFIRMED
                        else ActorRole.SYSTEM
                    ),
                    actor_id="synthetic",
                    occurred_at=AS_OF,
                    idempotency_key=f"m63c-key-{index}",
                    payload={},
                )
            )

        patient = PatientContext(
            patient_id="5000999",
            display_name="Synthetic Primary Care Veteran",
            birth_date="1980-01-01",
            gender="F",
            city="Denver",
            state="CO",
            postal_code="80200",
        )
        request = SchedulingRequest(
            request_id="REQ-PC-M63A-001",
            case_id=case_id,
            patient_id="5000999",
            request_source=RequestSource.VETERAN_REQUEST,
            care_category=CareCategory.PRIMARY_CARE,
            service="PRIMARY_CARE",
            canonical_pid=date(2026, 11, 1),
            facility_id="PC-VA-001",
            clinic_id="PC-CLINIC-1",
            stop_code="323",
            stop_code_group="PRIMARY_CARE",
            required_duration_minutes=30,
            required_resource_types=(ResourceType.PHYSICIAN,),
            required_template_types=(SlotTemplateType.ESTABLISHED,),
            required_modality="IN_PERSON",
        )
        relationship = PatientClinicRelationship(
            patient_id="5000999",
            facility_id="PC-VA-001",
            stop_code="323",
            stop_code_group="PRIMARY_CARE",
            last_completed_visit=datetime(
                2025, 7, 1, 15, 0, tzinfo=timezone.utc
            ),
            as_of=AS_OF,
        )
        before = events.get_events(case_id)

        encounter = assemble_scheduling_encounter(
            request=request,
            patient=patient,
            relationship=relationship,
            as_of=AS_OF,
            event_store=events,
            _vista=_PrimaryCareVista(),
            _federal_ehr=_NoFederalSlots(),
        )

        self.assertEqual(events.get_events(case_id), before)
        self.assertEqual(
            encounter.encounter_state,
            SchedulingEncounterState.READY_FOR_APPROVAL,
        )
        self.assertIsNotNone(encounter.decision)
        self.assertEqual(
            encounter.decision.lifecycle_state,
            CaseLifecycleState.PENDING_SCHEDULER_APPROVAL,
        )

    def test_repeated_assembly_is_deterministic_and_side_effect_free(self):
        kwargs = dict(
            request=cardiology_request(),
            patient=cardiology_patient(),
            consult=cardiology_consult(),
            relationship=cardiology_relationship(),
            as_of=AS_OF,
        )
        first = assemble_scheduling_encounter(**kwargs)
        second = assemble_scheduling_encounter(**kwargs)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
