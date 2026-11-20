"""Tests for the M1 availability search layer.

Covers:
1. Valid READY_TO_SEARCH case searches all three adapters.
2. Every AccessOption has required provenance fields.
3. Invalid/missing consult blocks all adapter calls (ValueError).
4. Stale slot maps to OptionReadiness.STALE.
5. Community open slot without authorization = AVAILABLE_NOT_AUTHORIZED.
6. Community slot without authorization is never VERIFIED_BOOKABLE.
7. Single source timeout preserves other source results and reports failure.
8. All-source failure produces no false success (empty options, three failures).
9. Deterministic fixture results are repeatable across two calls.

All calls to search_availability() that exercise fixture data use a fixed
_as_of value (2026-10-16T00:00:00Z) so the results never depend on wall-clock
time. Fixture slots are dated 2026-11-xx and are treated as future relative to
this clock.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

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

# Fixed reference clock: before all fixture slot dates (2026-11-xx).
# Always use this in tests that exercise fixture data. Never rely on wall-clock.
_TEST_AS_OF = datetime(2026, 10, 16, 0, 0, 0, tzinfo=timezone.utc)


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


class TestSearchAllThreeAdapters(unittest.TestCase):
    def test_valid_case_searches_all_three_adapters(self) -> None:
        result = search_availability(
            _valid_patient(), _valid_consult(), _as_of=_TEST_AS_OF
        )
        source_systems = {sr.source_system for sr in result.source_results}
        self.assertEqual(
            source_systems,
            {"VISTA_ISS", "FEDERAL_EHR_FHIR", "COMMUNITY_CARE_EPS"},
        )
        self.assertEqual(len(result.source_results), 3)

    def test_result_carries_patient_and_consult_ids(self) -> None:
        result = search_availability(
            _valid_patient(), _valid_consult(), _as_of=_TEST_AS_OF
        )
        self.assertEqual(result.patient_id, "5000335")
        self.assertEqual(result.consult_id, "CONSULT-CARD-5000335-001")

    def test_all_three_sources_succeed_with_fixture_data(self) -> None:
        result = search_availability(
            _valid_patient(), _valid_consult(), _as_of=_TEST_AS_OF
        )
        for sr in result.source_results:
            self.assertIn(
                sr.status,
                {SourceSearchStatus.SUCCESS, SourceSearchStatus.NO_SLOTS},
                msg=f"{sr.source_system} returned unexpected status {sr.status}",
            )


class TestAccessOptionProvenance(unittest.TestCase):
    def setUp(self) -> None:
        self.result = search_availability(
            _valid_patient(), _valid_consult(), _as_of=_TEST_AS_OF
        )

    def test_options_are_non_empty(self) -> None:
        self.assertGreater(len(self.result.options), 0)

    def test_access_option_has_required_provenance_fields(self) -> None:
        for opt in self.result.options:
            with self.subTest(option_id=opt.option_id):
                self.assertTrue(opt.option_id, "option_id must be non-empty")
                self.assertTrue(opt.source_system, "source_system must be non-empty")
                self.assertTrue(
                    opt.source_record_id, "source_record_id must be non-empty"
                )
                self.assertIsInstance(opt.provenance.retrieved_at, datetime)
                self.assertIsInstance(opt.provenance.synthetic, bool)
                self.assertTrue(
                    opt.provenance.freshness, "freshness must be non-empty"
                )
                self.assertTrue(
                    opt.provenance.source_system,
                    "provenance.source_system must be non-empty",
                )

    def test_access_option_source_matches_provenance_source(self) -> None:
        for opt in self.result.options:
            with self.subTest(option_id=opt.option_id):
                self.assertEqual(opt.source_system, opt.provenance.source_system)

    def test_all_options_are_synthetic(self) -> None:
        for opt in self.result.options:
            with self.subTest(option_id=opt.option_id):
                self.assertTrue(opt.provenance.synthetic)


class TestWorkflowGateBlocking(unittest.TestCase):
    def test_missing_consult_blocks_all_adapters(self) -> None:
        with self.assertRaises(ValueError):
            search_availability(_valid_patient(), None)

    def test_invalid_consult_blocks_all_adapters(self) -> None:
        invalid_consult = ClinicalConsult(
            consult_id="CONSULT-BAD",
            patient_id="5000335",
            specialty="Cardiology",
            status="ACTIVE",
            requested_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
            valid=False,  # explicitly invalid
        )
        with self.assertRaises(ValueError):
            search_availability(_valid_patient(), invalid_consult)

    def test_wrong_specialty_consult_blocks_all_adapters(self) -> None:
        wrong_consult = ClinicalConsult(
            consult_id="CONSULT-ORTHO",
            patient_id="5000335",
            specialty="Orthopedics",
            status="ACTIVE",
            requested_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
            valid=True,
        )
        with self.assertRaises(ValueError):
            search_availability(_valid_patient(), wrong_consult)

    def test_blocked_consult_blocks_all_adapters(self) -> None:
        blocked_consult = ClinicalConsult(
            consult_id="CONSULT-BLOCKED",
            patient_id="5000335",
            specialty="Cardiology",
            status="ACTIVE",
            requested_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
            valid=True,
            blockers=("clinical-review",),
        )
        with self.assertRaises(ValueError):
            search_availability(_valid_patient(), blocked_consult)


class TestStaleSlotReadiness(unittest.TestCase):
    def test_stale_slot_readiness(self) -> None:
        result = search_availability(
            _valid_patient(), _valid_consult(), _as_of=_TEST_AS_OF
        )
        stale_options = [
            opt
            for opt in result.options
            if opt.source_system == "VISTA_ISS"
            and opt.readiness == OptionReadiness.STALE
        ]
        self.assertGreater(
            len(stale_options),
            0,
            "Expected at least one STALE VistA option from the fixture.",
        )

    def test_stale_slot_declared_status_preserved(self) -> None:
        """availability_status on the AccessOption reflects the fixture declaration.

        A slot declared STALE in the fixture has availability_status='STALE'.
        A slot that becomes STALE via expiry retains its original
        availability_status (e.g. 'AVAILABLE') — only readiness changes.
        """
        result = search_availability(
            _valid_patient(), _valid_consult(), _as_of=_TEST_AS_OF
        )
        stale_options = [
            opt for opt in result.options if opt.readiness == OptionReadiness.STALE
        ]
        for opt in stale_options:
            # availability_status must be a known valid value from the fixture.
            self.assertIn(
                opt.availability_status.upper(),
                {"STALE", "AVAILABLE", "UNAVAILABLE"},
                f"Option {opt.option_id!r} has unexpected availability_status.",
            )


class TestCommunityAuthorizationReadiness(unittest.TestCase):
    def setUp(self) -> None:
        self.result = search_availability(
            _valid_patient(), _valid_consult(), _as_of=_TEST_AS_OF
        )
        self.community_options = [
            opt
            for opt in self.result.options
            if opt.source_system == "COMMUNITY_CARE_EPS"
        ]

    def test_community_options_present(self) -> None:
        self.assertGreater(len(self.community_options), 0)

    def test_community_open_slot_without_auth_is_available_not_authorized(
        self,
    ) -> None:
        # The community fixture has slots with null authorization_id.
        unauth_options = [
            opt
            for opt in self.community_options
            if opt.readiness == OptionReadiness.AVAILABLE_NOT_AUTHORIZED
        ]
        self.assertGreater(
            len(unauth_options),
            0,
            "Expected at least one AVAILABLE_NOT_AUTHORIZED community option.",
        )

    def test_community_slot_without_auth_is_not_verified_bookable(self) -> None:
        for opt in self.community_options:
            self.assertNotEqual(
                opt.readiness,
                OptionReadiness.VERIFIED_BOOKABLE,
                f"Community option {opt.option_id!r} must not be VERIFIED_BOOKABLE "
                f"without authorization verification.",
            )

    def test_community_unauth_option_has_warning(self) -> None:
        unauth_options = [
            opt
            for opt in self.community_options
            if opt.readiness == OptionReadiness.AVAILABLE_NOT_AUTHORIZED
        ]
        for opt in unauth_options:
            self.assertGreater(
                len(opt.warnings),
                0,
                f"Community option {opt.option_id!r} without authorization "
                f"should carry a warning.",
            )

    def test_community_authorized_slot_is_authorized_not_verified(self) -> None:
        auth_options = [
            opt
            for opt in self.community_options
            if opt.readiness == OptionReadiness.AUTHORIZED_NOT_VERIFIED
        ]
        self.assertGreater(
            len(auth_options),
            0,
            "Expected at least one AUTHORIZED_NOT_VERIFIED community option "
            "(slot with authorization_id in fixture).",
        )


class TestPartialSourceFailure(unittest.TestCase):
    def test_single_source_timeout_preserves_other_results(self) -> None:
        result = search_availability(
            _valid_patient(),
            _valid_consult(),
            _federal_ehr=FederalEHRAdapter(simulate_unavailable=True),
            _as_of=_TEST_AS_OF,
        )

        fehr_result = next(
            sr for sr in result.source_results if sr.source_system == "FEDERAL_EHR_FHIR"
        )
        self.assertEqual(fehr_result.status, SourceSearchStatus.SOURCE_UNAVAILABLE)
        self.assertTrue(
            fehr_result.error_message,
            "Failed source must carry a non-empty error_message.",
        )

        # Other sources must still be present and have results.
        vista_result = next(
            sr for sr in result.source_results if sr.source_system == "VISTA_ISS"
        )
        community_result = next(
            sr for sr in result.source_results if sr.source_system == "COMMUNITY_CARE_EPS"
        )
        self.assertEqual(vista_result.status, SourceSearchStatus.SUCCESS)
        self.assertEqual(community_result.status, SourceSearchStatus.SUCCESS)

        # Aggregated options must not include Federal EHR options.
        option_sources = {opt.source_system for opt in result.options}
        self.assertNotIn("FEDERAL_EHR_FHIR", option_sources)
        self.assertIn("VISTA_ISS", option_sources)

    def test_failed_source_is_never_silently_dropped(self) -> None:
        result = search_availability(
            _valid_patient(),
            _valid_consult(),
            _federal_ehr=FederalEHRAdapter(simulate_unavailable=True),
            _as_of=_TEST_AS_OF,
        )
        self.assertEqual(len(result.source_results), 3)

    def test_all_source_failure_no_false_success(self) -> None:
        result = search_availability(
            _valid_patient(),
            _valid_consult(),
            _vista=VistAAdapter(simulate_unavailable=True),
            _federal_ehr=FederalEHRAdapter(simulate_unavailable=True),
            _community=CommunityAdapter(simulate_unavailable=True),
            _as_of=_TEST_AS_OF,
        )

        self.assertEqual(len(result.options), 0, "No options when all sources fail.")
        self.assertEqual(len(result.source_results), 3)
        for sr in result.source_results:
            self.assertEqual(
                sr.status,
                SourceSearchStatus.SOURCE_UNAVAILABLE,
                f"{sr.source_system} should be SOURCE_UNAVAILABLE.",
            )
            self.assertTrue(
                sr.error_message,
                f"{sr.source_system} must carry error_message.",
            )


class TestDeterministicRepeatability(unittest.TestCase):
    def test_deterministic_fixture_results_are_repeatable(self) -> None:
        patient = _valid_patient()
        consult = _valid_consult()

        result_a = search_availability(patient, consult, _as_of=_TEST_AS_OF)
        result_b = search_availability(patient, consult, _as_of=_TEST_AS_OF)

        self.assertEqual(len(result_a.options), len(result_b.options))

        ids_a = sorted(opt.option_id for opt in result_a.options)
        ids_b = sorted(opt.option_id for opt in result_b.options)
        self.assertEqual(ids_a, ids_b)


if __name__ == "__main__":
    unittest.main()
