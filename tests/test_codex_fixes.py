"""Tests for Codex PR-15 findings.

Covers:
1. Package resource fixture resolution — default adapters load without repo root.
2. Adapter exception isolation — one adapter raises RuntimeError; others still run.
3. synthetic=false fixture records are rejected for all three adapters.
4. Unknown availability_status values cannot become AVAILABLE for all three adapters.
5. Synthea script refuses to overwrite an existing run directory without -Overwrite.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
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
    SourceSearchStatus,
)
from veteran_access_bridge.services.search import search_availability

# Fixed reference clock used in all fixture-exercising calls.
_TEST_AS_OF = datetime(2026, 10, 16, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _valid_patient() -> PatientContext:
    return PatientContext(
        patient_id="5000335",
        display_name="Mr. Mariano761 Ruelas156",
        birth_date="1907-11-20",
        gender="male",
        city="Colorado Springs",
        state="CO",
        postal_code="80809",
        active_conditions=("Atrial Fibrillation",),
    )


def _valid_consult() -> ClinicalConsult:
    return ClinicalConsult(
        consult_id="CONSULT-CARD-5000335-001",
        patient_id="5000335",
        specialty="Cardiology",
        status="ACTIVE",
        requested_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
        valid=True,
    )


def _source_system_for_fixture(path: Path) -> str:
    name = path.name.lower()
    if name.startswith("vista"):
        return "VISTA_ISS"
    if name.startswith("fehr"):
        return "FEDERAL_EHR_FHIR"
    if name.startswith("cc"):
        return "COMMUNITY_CARE_EPS"
    raise ValueError(f"Test fixture name must identify its source: {path.name!r}")


def _write_fixture(path: Path, slots: list[dict]) -> None:
    """Write a minimal source-identified fixture JSON to a path."""
    source_system = _source_system_for_fixture(path)
    normalized_slots = [
        {**slot, "source_system": source_system}
        for slot in slots
    ]
    payload = {
        "_fixture_meta": {
            "synthetic": True,
            "case_id": "TEST",
            "generated_for": "test",
            "source_system": source_system,
        },
        "slots": normalized_slots,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


_BASE_SLOT: dict = {
    "slot_id": "TEST-SLOT-001",
    "patient_id": "5000335",
    "specialty": "Cardiology",
    "facility_id": "FAC-001",
    "facility_name": "Test Facility",
    "provider": "Dr. Test",
    "slot_start": "2026-11-10T09:00:00Z",
    "slot_end": "2026-11-10T09:30:00Z",
    "availability_status": "AVAILABLE",
    "wait_days": 10,
    "drive_minutes": 15,
    "synthetic": True,
    "environment": "test",
    "source_system": "TEST",
    "freshness": "test-fixture",
}


# ---------------------------------------------------------------------------
# Fix 1: Package resource fixture resolution
# ---------------------------------------------------------------------------


class TestPackageResourceFixtureResolution(unittest.TestCase):
    """Default adapters resolve fixtures via importlib.resources, not repo paths."""

    def test_vista_loads_default_fixture_via_package_resource(self) -> None:
        adapter = VistAAdapter()  # no fixture_path — must use package resource
        result = adapter.search("5000335", "Cardiology")
        self.assertIn(
            result.status,
            {SourceSearchStatus.SUCCESS, SourceSearchStatus.NO_SLOTS},
            "VistA default fixture must load via package resource.",
        )

    def test_federal_ehr_loads_default_fixture_via_package_resource(self) -> None:
        adapter = FederalEHRAdapter()
        result = adapter.search("5000335", "Cardiology")
        self.assertIn(
            result.status,
            {SourceSearchStatus.SUCCESS, SourceSearchStatus.NO_SLOTS},
            "Federal EHR default fixture must load via package resource.",
        )

    def test_community_loads_default_fixture_via_package_resource(self) -> None:
        adapter = CommunityAdapter()
        result = adapter.search("5000335", "Cardiology")
        self.assertIn(
            result.status,
            {SourceSearchStatus.SUCCESS, SourceSearchStatus.NO_SLOTS},
            "Community Care default fixture must load via package resource.",
        )

    def test_default_search_returns_options(self) -> None:
        """End-to-end: package resource fixtures produce at least one AccessOption."""
        result = search_availability(
            _valid_patient(), _valid_consult(), _as_of=_TEST_AS_OF
        )
        self.assertGreater(
            len(result.options),
            0,
            "At least one AccessOption must come from package resource fixtures.",
        )


# ---------------------------------------------------------------------------
# Fix 2: Adapter exception isolation
# ---------------------------------------------------------------------------


class _ExplodingAdapter:
    """Test double whose search() always raises RuntimeError."""

    def search(self, patient_id: str, specialty: str) -> None:  # type: ignore[return]
        raise RuntimeError("Simulated unexpected adapter failure")


class TestAdapterExceptionIsolation(unittest.TestCase):
    def test_exploding_vista_adapter_leaves_other_sources_intact(self) -> None:
        result = search_availability(
            _valid_patient(),
            _valid_consult(),
            _vista=_ExplodingAdapter(),  # type: ignore[arg-type]
            _as_of=_TEST_AS_OF,
        )

        # All three source_results must be present.
        self.assertEqual(len(result.source_results), 3)

        vista_result = next(
            sr for sr in result.source_results if sr.source_system == "VISTA_ISS"
        )
        self.assertEqual(vista_result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertIn("RuntimeError", vista_result.error_message or "")

        # Other adapters must have run.
        fehr_result = next(
            sr for sr in result.source_results if sr.source_system == "FEDERAL_EHR_FHIR"
        )
        cc_result = next(
            sr for sr in result.source_results if sr.source_system == "COMMUNITY_CARE_EPS"
        )
        self.assertIn(
            fehr_result.status,
            {SourceSearchStatus.SUCCESS, SourceSearchStatus.NO_SLOTS},
        )
        self.assertIn(
            cc_result.status,
            {SourceSearchStatus.SUCCESS, SourceSearchStatus.NO_SLOTS},
        )

    def test_exploding_adapter_options_excluded_others_included(self) -> None:
        result = search_availability(
            _valid_patient(),
            _valid_consult(),
            _federal_ehr=_ExplodingAdapter(),  # type: ignore[arg-type]
            _as_of=_TEST_AS_OF,
        )
        option_sources = {opt.source_system for opt in result.options}
        self.assertNotIn("FEDERAL_EHR_FHIR", option_sources)
        # At least VistA or Community Care options should be present.
        self.assertGreater(len(result.options), 0)

    def test_exploding_adapter_error_message_does_not_leak_stack_trace(
        self,
    ) -> None:
        result = search_availability(
            _valid_patient(),
            _valid_consult(),
            _vista=_ExplodingAdapter(),  # type: ignore[arg-type]
            _as_of=_TEST_AS_OF,
        )
        vista_result = next(
            sr for sr in result.source_results if sr.source_system == "VISTA_ISS"
        )
        msg = vista_result.error_message or ""
        # Must not contain file paths or traceback keywords.
        self.assertNotIn("Traceback", msg)
        self.assertNotIn("File ", msg)
        self.assertNotIn("line ", msg)


# ---------------------------------------------------------------------------
# Fix 3: synthetic=false records rejected
# ---------------------------------------------------------------------------


class TestSyntheticFalseRejected(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _bad_slot(self) -> dict:
        slot = dict(_BASE_SLOT)
        slot["synthetic"] = False  # must be rejected
        return slot

    def test_vista_rejects_synthetic_false_record(self) -> None:
        path = Path(self._tmpdir) / "vista-bad.json"
        _write_fixture(path, [self._bad_slot()])
        result = VistAAdapter(fixture_path=path).search("5000335", "Cardiology")
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(len(result.options), 0)

    def test_federal_ehr_rejects_synthetic_false_record(self) -> None:
        path = Path(self._tmpdir) / "fehr-bad.json"
        _write_fixture(path, [self._bad_slot()])
        result = FederalEHRAdapter(fixture_path=path).search("5000335", "Cardiology")
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(len(result.options), 0)

    def test_community_rejects_synthetic_false_record(self) -> None:
        slot = self._bad_slot()
        slot["authorization_id"] = None
        path = Path(self._tmpdir) / "cc-bad.json"
        _write_fixture(path, [slot])
        result = CommunityAdapter(fixture_path=path).search("5000335", "Cardiology")
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(len(result.options), 0)

    def test_synthetic_false_record_never_becomes_access_option(self) -> None:
        """A record with synthetic=false from any source must never reach options."""
        path = Path(self._tmpdir) / "vista-bad2.json"
        _write_fixture(path, [self._bad_slot()])
        result = search_availability(
            _valid_patient(),
            _valid_consult(),
            _vista=VistAAdapter(fixture_path=path),
            _as_of=_TEST_AS_OF,
        )
        vista_options = [
            opt for opt in result.options if opt.source_system == "VISTA_ISS"
        ]
        self.assertEqual(len(vista_options), 0)
        for opt in result.options:
            self.assertTrue(
                opt.provenance.synthetic,
                f"Option {opt.option_id!r} must have synthetic=True.",
            )


# ---------------------------------------------------------------------------
# Fix 4: Unknown availability_status values rejected
# ---------------------------------------------------------------------------


class TestUnknownStatusRejected(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _bad_status_slot(self, status: str) -> dict:
        slot = dict(_BASE_SLOT)
        slot["availability_status"] = status
        return slot

    def _assert_unavailable_or_no_slots(
        self, result: object, source: str, status: str
    ) -> None:
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        self.assertIn(
            result.status,
            {SourceSearchStatus.SOURCE_UNAVAILABLE, SourceSearchStatus.NO_SLOTS},
            f"{source} with status={status!r} should not return SUCCESS.",
        )

    def test_vista_rejects_booked_status(self) -> None:
        path = Path(self._tmpdir) / "vista-booked.json"
        _write_fixture(path, [self._bad_status_slot("BOOKED")])
        result = VistAAdapter(fixture_path=path).search("5000335", "Cardiology")
        self._assert_unavailable_or_no_slots(result, "VISTA_ISS", "BOOKED")

    def test_vista_rejects_cancelled_status(self) -> None:
        path = Path(self._tmpdir) / "vista-cancelled.json"
        _write_fixture(path, [self._bad_status_slot("CANCELLED")])
        result = VistAAdapter(fixture_path=path).search("5000335", "Cardiology")
        self._assert_unavailable_or_no_slots(result, "VISTA_ISS", "CANCELLED")

    def test_federal_ehr_rejects_held_status(self) -> None:
        path = Path(self._tmpdir) / "fehr-held.json"
        _write_fixture(path, [self._bad_status_slot("HELD")])
        result = FederalEHRAdapter(fixture_path=path).search("5000335", "Cardiology")
        self._assert_unavailable_or_no_slots(result, "FEDERAL_EHR_FHIR", "HELD")

    def test_federal_ehr_rejects_unknown_status(self) -> None:
        path = Path(self._tmpdir) / "fehr-unknown.json"
        _write_fixture(path, [self._bad_status_slot("PENDING_APPROVAL")])
        result = FederalEHRAdapter(fixture_path=path).search("5000335", "Cardiology")
        self._assert_unavailable_or_no_slots(result, "FEDERAL_EHR_FHIR", "PENDING_APPROVAL")

    def test_community_rejects_booked_status(self) -> None:
        slot = self._bad_status_slot("BOOKED")
        slot["authorization_id"] = None
        path = Path(self._tmpdir) / "cc-booked.json"
        _write_fixture(path, [slot])
        result = CommunityAdapter(fixture_path=path).search("5000335", "Cardiology")
        self._assert_unavailable_or_no_slots(result, "COMMUNITY_CARE_EPS", "BOOKED")

    def test_unknown_status_never_becomes_available(self) -> None:
        """Unknown statuses from any adapter must not produce AVAILABLE options."""
        path = Path(self._tmpdir) / "vista-cancelled2.json"
        _write_fixture(path, [self._bad_status_slot("CANCELLED")])
        result = search_availability(
            _valid_patient(),
            _valid_consult(),
            _vista=VistAAdapter(fixture_path=path),
            _as_of=_TEST_AS_OF,
        )
        for opt in result.options:
            if opt.source_system == "VISTA_ISS":
                self.assertNotEqual(
                    opt.readiness,
                    OptionReadiness.AVAILABLE,
                    "A CANCELLED slot must not produce an AVAILABLE AccessOption.",
                )


# ---------------------------------------------------------------------------
# Fix 5: Synthea script -Overwrite guard
# ---------------------------------------------------------------------------


@unittest.skipUnless(shutil.which("powershell"), "powershell.exe not available on PATH")
class TestSyntheaOverwriteGuard(unittest.TestCase):
    """Synthea script must refuse to delete an existing run dir without -Overwrite."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_script_fails_when_run_dir_exists_without_overwrite_flag(self) -> None:
        script = Path(__file__).parent.parent / "scripts" / "synthea" / "01-setup-and-generate-synthea.ps1"
        # Simulate what the script would compute as $runName for State=CO, Pop=1, Seed=20261010
        run_name = "veterans-CO-1-seed-20261010"
        existing_run = Path(self._tmpdir) / run_name
        existing_run.mkdir()
        (existing_run / "provenance.json").write_text('{"synthetic":true}', encoding="utf-8")

        result = subprocess.run(
            [
                "powershell",
                "-NonInteractive",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", str(script),
                "-State", "CO",
                "-Population", "1",
                "-Seed", "20261010",
                "-OutputRoot", self._tmpdir,
                # -Overwrite NOT passed
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertNotEqual(
            result.returncode,
            0,
            "Script must exit non-zero when run dir exists and -Overwrite is absent.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}",
        )
        # Provenance file must still exist — not deleted.
        self.assertTrue(
            (existing_run / "provenance.json").exists(),
            "Existing provenance.json must not be deleted when -Overwrite is absent.",
        )


if __name__ == "__main__":
    unittest.main()
