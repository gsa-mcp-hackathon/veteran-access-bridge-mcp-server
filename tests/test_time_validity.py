"""Tests for slot time-validity findings (Codex dc8e8a0).

Covers:
1. Past VistA slot (slot_end <= as_of) becomes STALE.
2. Past Federal EHR slot becomes STALE.
3. Past Community Care slot becomes STALE regardless of authorization presence.
4. Future slot retains its normal readiness.
5. slot_end == slot_start rejected for all three adapters.
6. slot_end < slot_start rejected for all three adapters.
7. Injected clock makes results deterministic.
8. Expiry takes precedence over authorization status in Community Care.

All adapter and search_availability calls use explicit as_of values — never
wall-clock time.
"""

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
    SourceSearchStatus,
)
from veteran_access_bridge.services.search import search_availability

# ---------------------------------------------------------------------------
# Shared fixture-writing helpers
# ---------------------------------------------------------------------------

# A slot time well in the past relative to any reasonable as_of in tests.
_PAST_START = "2020-01-01T09:00:00Z"
_PAST_END = "2020-01-01T09:30:00Z"

# A slot time well in the future relative to any reasonable as_of in tests.
_FUTURE_START = "2099-01-01T09:00:00Z"
_FUTURE_END = "2099-01-01T09:30:00Z"

# as_of for "past slot" tests: after PAST_END, before FUTURE_START.
_AS_OF_PAST = datetime(2026, 10, 16, 0, 0, 0, tzinfo=timezone.utc)

# as_of for "future slot" tests: before FUTURE_START.
_AS_OF_FUTURE = datetime(2026, 10, 16, 0, 0, 0, tzinfo=timezone.utc)


def _make_slot(
    *,
    slot_id: str = "TEST-SLOT-001",
    slot_start: str = _FUTURE_START,
    slot_end: str = _FUTURE_END,
    availability_status: str = "AVAILABLE",
    synthetic: bool = True,
    authorization_id: str | None = None,
    extra: dict | None = None,
) -> dict:
    slot: dict = {
        "slot_id": slot_id,
        "patient_id": "5000335",
        "specialty": "Cardiology",
        "facility_id": "FAC-001",
        "facility_name": "Test Facility",
        "provider": "Dr. Test",
        "slot_start": slot_start,
        "slot_end": slot_end,
        "availability_status": availability_status,
        "wait_days": 10,
        "drive_minutes": 15,
        "synthetic": synthetic,
        "environment": "test",
        "source_system": "TEST",
        "freshness": "test-fixture",
    }
    if authorization_id is not None:
        slot["authorization_id"] = authorization_id
    if extra:
        slot.update(extra)
    return slot


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


# ---------------------------------------------------------------------------
# Finding 1: Past slots become STALE
# ---------------------------------------------------------------------------


class TestPastSlotsBecomeStaleMixin:
    """Mixin for testing expiry behaviour; shared across three adapters."""

    adapter_class: type  # set in concrete subclasses
    tmpdir: str

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_past_fixture(self, name: str, **slot_kwargs: object) -> Path:
        path = Path(self.tmpdir) / name
        _write_fixture(path, [_make_slot(slot_start=_PAST_START, slot_end=_PAST_END, **slot_kwargs)])  # type: ignore[arg-type]
        return path

    def _search_past(self, path: Path, **adapter_kwargs: object) -> object:
        adapter = self.adapter_class(fixture_path=path, as_of=_AS_OF_PAST, **adapter_kwargs)  # type: ignore[call-arg]
        return adapter.search("5000335", "Cardiology")


class TestPastVistaSlotBecomesStale(TestPastSlotsBecomeStaleMixin, unittest.TestCase):
    adapter_class = VistAAdapter

    def test_past_vista_slot_becomes_stale(self) -> None:
        path = self._make_past_fixture("vista-past.json")
        result = self._search_past(path)
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        self.assertEqual(result.status, SourceSearchStatus.SUCCESS)
        self.assertEqual(len(result.options), 1)
        self.assertEqual(result.options[0].readiness, OptionReadiness.STALE)

    def test_past_vista_slot_availability_status_preserved(self) -> None:
        """availability_status remains AVAILABLE; only readiness changes to STALE."""
        path = self._make_past_fixture("vista-past2.json")
        result = self._search_past(path)
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        opt = result.options[0]
        self.assertEqual(opt.readiness, OptionReadiness.STALE)
        self.assertEqual(opt.availability_status.upper(), "AVAILABLE")


class TestPastFederalEHRSlotBecomesStale(
    TestPastSlotsBecomeStaleMixin, unittest.TestCase
):
    adapter_class = FederalEHRAdapter

    def test_past_federal_ehr_slot_becomes_stale(self) -> None:
        path = self._make_past_fixture("fehr-past.json")
        result = self._search_past(path)
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        self.assertEqual(result.status, SourceSearchStatus.SUCCESS)
        self.assertEqual(len(result.options), 1)
        self.assertEqual(result.options[0].readiness, OptionReadiness.STALE)


class TestPastCommunitySlotBecomesStale(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _search_community_past(self, path: Path) -> object:
        return CommunityAdapter(
            fixture_path=path, as_of=_AS_OF_PAST
        ).search("5000335", "Cardiology")

    def test_past_community_slot_without_auth_becomes_stale(self) -> None:
        """Expired slot with no auth → STALE (not AVAILABLE_NOT_AUTHORIZED)."""
        path = Path(self.tmpdir) / "cc-past-noauth.json"
        _write_fixture(
            path,
            [_make_slot(slot_start=_PAST_START, slot_end=_PAST_END, authorization_id=None)],
        )
        result = self._search_community_past(path)
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        self.assertEqual(result.options[0].readiness, OptionReadiness.STALE)

    def test_past_community_slot_with_auth_becomes_stale(self) -> None:
        """Expired slot with auth → STALE (not AUTHORIZED_NOT_VERIFIED)."""
        path = Path(self.tmpdir) / "cc-past-auth.json"
        _write_fixture(
            path,
            [
                _make_slot(
                    slot_start=_PAST_START,
                    slot_end=_PAST_END,
                    authorization_id="AUTH-001",
                )
            ],
        )
        result = self._search_community_past(path)
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        self.assertEqual(result.options[0].readiness, OptionReadiness.STALE)

    def test_expiry_takes_precedence_over_auth_status(self) -> None:
        """Explicit test: an authorized-but-expired community slot is STALE."""
        path = Path(self.tmpdir) / "cc-expired-auth.json"
        _write_fixture(
            path,
            [
                _make_slot(
                    slot_id="CC-EXPIRED-AUTH",
                    slot_start=_PAST_START,
                    slot_end=_PAST_END,
                    authorization_id="AUTH-CARD-001",
                )
            ],
        )
        result = CommunityAdapter(
            fixture_path=path, as_of=_AS_OF_PAST
        ).search("5000335", "Cardiology")
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        opt = result.options[0]
        self.assertEqual(opt.readiness, OptionReadiness.STALE)
        self.assertNotEqual(opt.readiness, OptionReadiness.AUTHORIZED_NOT_VERIFIED)


# ---------------------------------------------------------------------------
# Finding 1 (continued): Future slots retain normal readiness
# ---------------------------------------------------------------------------


class TestFutureSlotRetainsNormalReadiness(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_future_vista_slot_remains_available(self) -> None:
        path = Path(self.tmpdir) / "vista-future.json"
        _write_fixture(path, [_make_slot(slot_start=_FUTURE_START, slot_end=_FUTURE_END)])
        result = VistAAdapter(fixture_path=path, as_of=_AS_OF_FUTURE).search(
            "5000335", "Cardiology"
        )
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        self.assertEqual(result.options[0].readiness, OptionReadiness.AVAILABLE)

    def test_future_federal_ehr_slot_remains_available(self) -> None:
        path = Path(self.tmpdir) / "fehr-future.json"
        _write_fixture(path, [_make_slot(slot_start=_FUTURE_START, slot_end=_FUTURE_END)])
        result = FederalEHRAdapter(fixture_path=path, as_of=_AS_OF_FUTURE).search(
            "5000335", "Cardiology"
        )
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        self.assertEqual(result.options[0].readiness, OptionReadiness.AVAILABLE)

    def test_future_community_slot_without_auth_remains_available_not_authorized(
        self,
    ) -> None:
        path = Path(self.tmpdir) / "cc-future-noauth.json"
        _write_fixture(
            path, [_make_slot(slot_start=_FUTURE_START, slot_end=_FUTURE_END)]
        )
        result = CommunityAdapter(fixture_path=path, as_of=_AS_OF_FUTURE).search(
            "5000335", "Cardiology"
        )
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result, SourceSearchResult)
        self.assertEqual(
            result.options[0].readiness, OptionReadiness.AVAILABLE_NOT_AUTHORIZED
        )


# ---------------------------------------------------------------------------
# Finding 2: Invalid intervals rejected
# ---------------------------------------------------------------------------


class TestInvalidIntervalRejected(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _path(self, name: str) -> Path:
        return Path(self.tmpdir) / name

    # slot_end == slot_start

    def test_vista_rejects_equal_start_end(self) -> None:
        path = self._path("vista-equal.json")
        _write_fixture(
            path,
            [_make_slot(slot_start="2026-11-10T09:00:00Z", slot_end="2026-11-10T09:00:00Z")],
        )
        result = VistAAdapter(fixture_path=path, as_of=_AS_OF_PAST).search(
            "5000335", "Cardiology"
        )
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(len(result.options), 0)

    def test_federal_ehr_rejects_equal_start_end(self) -> None:
        path = self._path("fehr-equal.json")
        _write_fixture(
            path,
            [_make_slot(slot_start="2026-11-10T09:00:00Z", slot_end="2026-11-10T09:00:00Z")],
        )
        result = FederalEHRAdapter(fixture_path=path, as_of=_AS_OF_PAST).search(
            "5000335", "Cardiology"
        )
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(len(result.options), 0)

    def test_community_rejects_equal_start_end(self) -> None:
        path = self._path("cc-equal.json")
        _write_fixture(
            path,
            [_make_slot(slot_start="2026-11-10T09:00:00Z", slot_end="2026-11-10T09:00:00Z")],
        )
        result = CommunityAdapter(fixture_path=path, as_of=_AS_OF_PAST).search(
            "5000335", "Cardiology"
        )
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(len(result.options), 0)

    # slot_end < slot_start

    def test_vista_rejects_end_before_start(self) -> None:
        path = self._path("vista-inverted.json")
        _write_fixture(
            path,
            [_make_slot(slot_start="2026-11-10T09:30:00Z", slot_end="2026-11-10T09:00:00Z")],
        )
        result = VistAAdapter(fixture_path=path, as_of=_AS_OF_PAST).search(
            "5000335", "Cardiology"
        )
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(len(result.options), 0)

    def test_federal_ehr_rejects_end_before_start(self) -> None:
        path = self._path("fehr-inverted.json")
        _write_fixture(
            path,
            [_make_slot(slot_start="2026-11-10T09:30:00Z", slot_end="2026-11-10T09:00:00Z")],
        )
        result = FederalEHRAdapter(fixture_path=path, as_of=_AS_OF_PAST).search(
            "5000335", "Cardiology"
        )
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(len(result.options), 0)

    def test_community_rejects_end_before_start(self) -> None:
        path = self._path("cc-inverted.json")
        _write_fixture(
            path,
            [_make_slot(slot_start="2026-11-10T09:30:00Z", slot_end="2026-11-10T09:00:00Z")],
        )
        result = CommunityAdapter(fixture_path=path, as_of=_AS_OF_PAST).search(
            "5000335", "Cardiology"
        )
        self.assertEqual(result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertEqual(len(result.options), 0)


# ---------------------------------------------------------------------------
# Clock determinism: same as_of → same results
# ---------------------------------------------------------------------------


class TestInjectedClockDeterminism(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_injected_clock_makes_results_deterministic(self) -> None:
        """Same fixture + same as_of → same option IDs and readiness values."""
        fixed_as_of = datetime(2026, 10, 16, 0, 0, 0, tzinfo=timezone.utc)

        result_a = search_availability(
            _valid_patient(), _valid_consult(), _as_of=fixed_as_of
        )
        result_b = search_availability(
            _valid_patient(), _valid_consult(), _as_of=fixed_as_of
        )

        ids_a = sorted(opt.option_id for opt in result_a.options)
        ids_b = sorted(opt.option_id for opt in result_b.options)
        self.assertEqual(ids_a, ids_b)

        readiness_a = sorted(
            (opt.option_id, opt.readiness) for opt in result_a.options
        )
        readiness_b = sorted(
            (opt.option_id, opt.readiness) for opt in result_b.options
        )
        self.assertEqual(readiness_a, readiness_b)

    def test_different_as_of_changes_expiry_outcome(self) -> None:
        """A slot that is future at as_of_early becomes STALE at as_of_late."""
        path = Path(self.tmpdir) / "vista-boundary.json"
        slot_end = "2026-11-01T09:30:00Z"
        slot_start = "2026-11-01T09:00:00Z"
        _write_fixture(path, [_make_slot(slot_start=slot_start, slot_end=slot_end)])

        # as_of before slot_end: slot is future → AVAILABLE
        as_of_early = datetime(2026, 10, 16, 0, 0, 0, tzinfo=timezone.utc)
        result_early = VistAAdapter(
            fixture_path=path, as_of=as_of_early
        ).search("5000335", "Cardiology")
        from veteran_access_bridge.domain.models import SourceSearchResult
        assert isinstance(result_early, SourceSearchResult)
        self.assertEqual(result_early.options[0].readiness, OptionReadiness.AVAILABLE)

        # as_of equal to slot_end: slot_end <= as_of → STALE
        as_of_at_end = datetime(2026, 11, 1, 9, 30, 0, tzinfo=timezone.utc)
        result_at_end = VistAAdapter(
            fixture_path=path, as_of=as_of_at_end
        ).search("5000335", "Cardiology")
        assert isinstance(result_at_end, SourceSearchResult)
        self.assertEqual(result_at_end.options[0].readiness, OptionReadiness.STALE)

        # as_of after slot_end: expired → STALE
        as_of_after = datetime(2026, 11, 15, 0, 0, 0, tzinfo=timezone.utc)
        result_after = VistAAdapter(
            fixture_path=path, as_of=as_of_after
        ).search("5000335", "Cardiology")
        assert isinstance(result_after, SourceSearchResult)
        self.assertEqual(result_after.options[0].readiness, OptionReadiness.STALE)


if __name__ == "__main__":
    unittest.main()
