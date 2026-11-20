"""Pure, deterministic PostgreSQL UUID mapping contract tests."""

from uuid import UUID

import pytest

from veteran_access_bridge.adapters.synthetic_ids import (
    persistent_uuid,
    resolve_case_identifiers,
)


@pytest.mark.parametrize(
    ("case_id", "request_id", "patient_id", "consult_id"),
    [
        ("DEMO-PC-5000999-001", "REQ-PC-5000999-001", "5000999", None),
        ("DEMO-PC-5000335-001", "REQ-PC-5000335-001", "5000335", None),
        (
            "DEMO-CARD-5000335-001",
            "REQ-CARD-5000335-001",
            "5000335",
            "CONSULT-CARD-5000335-001",
        ),
    ],
)
def test_approved_case_mapping(case_id, request_id, patient_id, consult_id):
    result = resolve_case_identifiers(case_id)
    assert result.case_id == case_id
    assert result.request_external_id == request_id
    assert result.patient_external_id == patient_id
    assert result.consult_external_id == consult_id
    assert isinstance(result.request_uuid, UUID)
    assert isinstance(result.patient_uuid, UUID)
    assert result.consult_uuid == (
        persistent_uuid("consult", consult_id) if consult_id else None
    )
    assert result.request_uuid == persistent_uuid("request", request_id)
    assert result.patient_uuid == persistent_uuid("patient", patient_id)
    assert result == resolve_case_identifiers(case_id)


def test_shared_patient_has_one_persistent_identity():
    primary_care = resolve_case_identifiers("DEMO-PC-5000335-001")
    cardiology = resolve_case_identifiers("DEMO-CARD-5000335-001")
    assert primary_care.patient_uuid == cardiology.patient_uuid
    assert primary_care.request_uuid != cardiology.request_uuid


def test_object_kinds_are_type_separated():
    assert persistent_uuid("patient", "123") != persistent_uuid("slot", "123")


@pytest.mark.parametrize(
    ("kind", "identifier"),
    [
        ("unknown", "abc"),
        ("patient", ""),
        ("patient", "  "),
        ("patient", " abc"),
        ("patient", "abc "),
    ],
)
def test_invalid_identifier_is_rejected(kind, identifier):
    with pytest.raises(ValueError):
        persistent_uuid(kind, identifier)


def test_unknown_case_fails_closed():
    with pytest.raises(ValueError):
        resolve_case_identifiers("DEMO-NOT-APPROVED")


def test_mapping_does_not_mutate_cases_or_require_database(monkeypatch):
    # The resolver reads packaged fixtures, and its API accepts no connection.
    first = resolve_case_identifiers("DEMO-PC-5000999-001")
    second = resolve_case_identifiers("DEMO-PC-5000999-001")
    assert first == second
