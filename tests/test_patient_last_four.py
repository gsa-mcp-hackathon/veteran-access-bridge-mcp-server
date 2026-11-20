"""Invented unit-test values only; never a test patient's actual identifier."""

import pytest

from veteran_access_bridge.services.patient_last_four import (
    IDENTIFIER_TYPES,
    SSN_SYSTEM,
    matches_patient_last_four,
)


def patient(value="123-45-0067", **extra):
    return {
        "resourceType": "Patient",
        "identifier": [{"system": SSN_SYSTEM, "value": value, **extra}],
    }


@pytest.mark.parametrize("value", ["123-45-0067", "123450067"])
def test_exact_match_preserves_leading_zeroes(value):
    assert matches_patient_last_four(patient(value), "0067") is True
    assert matches_patient_last_four(patient(value), "0068") is False


@pytest.mark.parametrize(
    "supplied",
    [None, 67, "67", " 0067", "0067 ", "１２３４", "123450067", "zero zero six seven"],
)
def test_only_four_ascii_digits_are_accepted(supplied):
    assert matches_patient_last_four(patient(), supplied) is False


@pytest.mark.parametrize(
    "value", [None, 123450067, "***-**-0067", "0067", "123 45 0067", "123-45-00678"]
)
def test_missing_masked_or_malformed_source_fails(value):
    assert matches_patient_last_four(patient(value), "0067") is False


def test_icn_is_never_a_substitute_even_with_matching_suffix():
    row = patient()
    row["identifier"][0]["system"] = "urn:va:icn"
    assert not matches_patient_last_four(row, "0067")
    row["identifier"][0]["type"] = {
        "coding": [{"system": IDENTIFIER_TYPES, "code": "SS"}]
    }
    assert not matches_patient_last_four(row, "0067")


def test_duplicate_or_conflicting_identifiers_fail_closed():
    row = patient()
    row["identifier"] *= 2
    assert not matches_patient_last_four(row, "0067")
    row["identifier"][1] = {"system": SSN_SYSTEM, "value": "123-45-0068"}
    assert not matches_patient_last_four(row, "0067")


@pytest.mark.parametrize(
    "row",
    [
        None,
        {},
        {"resourceType": "Observation"},
        {"resourceType": "Patient", "identifier": None},
        {"resourceType": "Patient", "identifier": [None]},
    ],
)
def test_wrong_or_missing_resource_shape_fails(row):
    assert matches_patient_last_four(row, "0067") is False


@pytest.mark.parametrize("use", ["old", "temp"])
def test_obsolete_or_temporary_identifiers_fail(use):
    assert not matches_patient_last_four(patient(use=use), "0067")


def test_no_patient_mutation_or_identifier_output():
    row = patient()
    before = repr(row)
    result = matches_patient_last_four(row, "0067")
    assert result is True
    assert repr(row) == before
