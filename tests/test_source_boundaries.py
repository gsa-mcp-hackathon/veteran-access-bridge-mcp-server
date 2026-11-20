"""Regression tests for source identity, clock propagation, and synthetic-only gates."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from veteran_access_bridge.adapters.community import CommunityAdapter
from veteran_access_bridge.adapters.federal_ehr import FederalEHRAdapter
from veteran_access_bridge.adapters.vista import VistAAdapter
from veteran_access_bridge.domain.models import (
    ClinicalConsult,
    OptionReadiness,
    PatientContext,
    SourceProvenance,
    SourceSearchStatus,
    WorkflowState,
)
from veteran_access_bridge.domain.workflow import determine_workflow_state
from veteran_access_bridge.services.search import search_availability


_EARLY = datetime(2026, 10, 16, tzinfo=timezone.utc)
_LATE = datetime(2026, 12, 1, tzinfo=timezone.utc)


def _patient(*, provenance: tuple[SourceProvenance, ...] = ()) -> PatientContext:
    return PatientContext(
        patient_id="5000335",
        display_name="Synthetic Veteran",
        birth_date="1970-01-01",
        gender="male",
        city="Colorado Springs",
        state="CO",
        postal_code="80809",
        active_conditions=("Atrial Fibrillation",),
        provenance=provenance,
    )


def _consult(
    *,
    source: str = "SYNTHETIC_DEMO_FIXTURE",
    provenance: tuple[SourceProvenance, ...] = (),
) -> ClinicalConsult:
    return ClinicalConsult(
        consult_id="CONSULT-CARD-5000335-001",
        patient_id="5000335",
        specialty="Cardiology",
        status="ACTIVE",
        requested_at=_EARLY,
        valid=True,
        source=source,
        provenance=provenance,
    )


def _fixture_payload(source_system: str) -> dict:
    slot = {
        "slot_id": "CROSSWIRED-SLOT-001",
        "patient_id": "5000335",
        "specialty": "Cardiology",
        "facility_id": "FAC-001",
        "facility_name": "Synthetic Test Facility",
        "provider": "Dr. Synthetic",
        "slot_start": "2026-11-10T09:00:00Z",
        "slot_end": "2026-11-10T09:30:00Z",
        "availability_status": "AVAILABLE",
        "wait_days": 10,
        "drive_minutes": 15,
        "synthetic": True,
        "environment": "test",
        "source_system": source_system,
        "freshness": "test-fixture",
    }
    if source_system == "COMMUNITY_CARE_EPS":
        slot["authorization_id"] = None
        slot["referral_id"] = None
    return {
        "_fixture_meta": {
            "synthetic": True,
            "case_id": "TEST",
            "generated_for": "test",
            "source_system": source_system,
        },
        "slots": [slot],
    }


class TestFixtureSourceIdentity(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name: str, source_system: str) -> Path:
        path = Path(self.tmpdir) / name
        path.write_text(json.dumps(_fixture_payload(source_system)), encoding="utf-8")
        return path

    def test_vista_rejects_community_fixture(self) -> None:
        path = self._write("crosswired-community.json", "COMMUNITY_CARE_EPS")
        result = VistAAdapter(fixture_path=path, as_of=_EARLY).search(
            "5000335", "Cardiology"
        )
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(result.options, ())

    def test_federal_ehr_rejects_vista_fixture(self) -> None:
        path = self._write("crosswired-vista.json", "VISTA_ISS")
        result = FederalEHRAdapter(fixture_path=path, as_of=_EARLY).search(
            "5000335", "Cardiology"
        )
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(result.options, ())

    def test_community_rejects_federal_ehr_fixture(self) -> None:
        path = self._write("crosswired-fehr.json", "FEDERAL_EHR_FHIR")
        result = CommunityAdapter(fixture_path=path, as_of=_EARLY).search(
            "5000335", "Cardiology"
        )
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(result.options, ())


class TestSearchClockOverride(unittest.TestCase):
    def test_explicit_search_clock_overrides_adapter_constructor_clock(self) -> None:
        adapter = VistAAdapter(as_of=_EARLY)
        result = search_availability(
            _patient(),
            _consult(),
            _vista=adapter,
            _as_of=_LATE,
        )
        vista_options = [
            option for option in result.options if option.source_system == "VISTA_ISS"
        ]
        self.assertGreater(len(vista_options), 0)
        self.assertTrue(
            all(option.readiness == OptionReadiness.STALE for option in vista_options)
        )
        self.assertEqual(result.searched_at, _LATE)
        self.assertTrue(
            all(option.provenance.retrieved_at == _LATE for option in vista_options)
        )


class TestSyntheticOnlyWorkflowGate(unittest.TestCase):
    def _provenance(self, *, synthetic: bool) -> SourceProvenance:
        return SourceProvenance(
            source_system="TEST_SOURCE",
            source_record_id="TEST-001",
            retrieved_at=_EARLY,
            synthetic=synthetic,
            environment="test",
            freshness="test",
        )

    def test_unapproved_consult_source_requires_clinical_review(self) -> None:
        state = determine_workflow_state(
            _patient(),
            _consult(source="VA_PRODUCTION"),
        )
        self.assertEqual(state, WorkflowState.CLINICAL_REVIEW_REQUIRED)

    def test_non_synthetic_patient_provenance_requires_clinical_review(self) -> None:
        state = determine_workflow_state(
            _patient(provenance=(self._provenance(synthetic=False),)),
            _consult(),
        )
        self.assertEqual(state, WorkflowState.CLINICAL_REVIEW_REQUIRED)

    def test_non_synthetic_consult_provenance_requires_clinical_review(self) -> None:
        state = determine_workflow_state(
            _patient(),
            _consult(provenance=(self._provenance(synthetic=False),)),
        )
        self.assertEqual(state, WorkflowState.CLINICAL_REVIEW_REQUIRED)


class TestFinalCodexBoundaries(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_blank_community_authorization_is_treated_as_missing(self) -> None:
        payload = _fixture_payload("COMMUNITY_CARE_EPS")
        payload["slots"][0]["authorization_id"] = "   "
        path = Path(self.tmpdir) / "community-blank-auth.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

        result = CommunityAdapter(fixture_path=path, as_of=_EARLY).search(
            "5000335", "Cardiology"
        )

        self.assertEqual(result.status, SourceSearchStatus.SUCCESS)
        self.assertEqual(
            result.options[0].readiness,
            OptionReadiness.AVAILABLE_NOT_AUTHORIZED,
        )

    def test_naive_search_clock_is_rejected_before_adapter_calls(self) -> None:
        with self.assertRaises(ValueError):
            search_availability(
                _patient(),
                _consult(),
                _as_of=datetime(2026, 10, 16, 0, 0, 0),
            )

    def test_aware_non_utc_search_clock_is_normalized_to_utc(self) -> None:
        from datetime import timedelta

        local_clock = datetime(
            2026, 10, 16, 5, 0, 0, tzinfo=timezone(timedelta(hours=5))
        )
        result = search_availability(
            _patient(),
            _consult(),
            _as_of=local_clock,
        )
        self.assertEqual(
            result.searched_at,
            datetime(2026, 10, 16, 0, 0, 0, tzinfo=timezone.utc),
        )

    def test_community_care_script_contains_synthetic_patient_guard(self) -> None:
        script = (
            Path(__file__).parent.parent
            / "scripts"
            / "data-sources"
            / "06-community-care-eligibility-template.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("$AllowedSyntheticPatientIcns", script)
        self.assertIn("5000335", script)
        self.assertIn("Refusing request", script)


if __name__ == "__main__":
    unittest.main()
