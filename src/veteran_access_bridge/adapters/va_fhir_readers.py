"""Disabled-by-default, local-only readers for documented VA FHIR resources."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from veteran_access_bridge.adapters.va_ccg import VaCcgClient, VaCcgConfig


@dataclass(frozen=True)
class _ApiContract:
    prefix: str
    token_url: str
    base_url: str
    read_gate: str


_CLINICAL = _ApiContract(
    prefix="VA_CLINICAL_HEALTH",
    token_url="https://sandbox-api.va.gov/oauth2/clinical-health/system/v1/token",
    base_url="https://sandbox-api.va.gov/services/clinical-fhir/v1/r4",
    read_gate="VA_CLINICAL_HEALTH_RESOURCE_READ_ENABLED",
)
_PATIENT = _ApiContract(
    prefix="VA_PATIENT_HEALTH",
    token_url="https://sandbox-api.va.gov/oauth2/health/system/v1/token",
    base_url="https://sandbox-api.va.gov/services/fhir/v0/r4",
    read_gate="VA_PATIENT_HEALTH_RESOURCE_READ_ENABLED",
)
_COSTS = _ApiContract(
    prefix="VA_HEALTH_CARE_COSTS",
    token_url="https://sandbox-api.va.gov/oauth2/health-care-costs-coverage/system/v1/token",
    base_url="https://sandbox-api.va.gov/services/health-care-costs-coverage/v0/r4",
    read_gate="VA_HEALTH_CARE_COSTS_RESOURCE_READ_ENABLED",
)


class VaResourceReadDisabled(PermissionError):
    """Raised when a sandbox resource reader has not been explicitly enabled."""


class VaSyntheticPatientDenied(PermissionError):
    """Raised when a synthetic patient is not explicitly allowlisted per API."""


class VaFhirResponseError(RuntimeError):
    """Raised for unexpected or mismatched FHIR response shapes."""


@dataclass(frozen=True)
class ClinicalObservation:
    resource_id: str
    status: str
    codes: tuple[str, ...]
    effective_at: str | None


@dataclass(frozen=True)
class PatientIdentity:
    resource_id: str
    identifier_confirmed: bool


@dataclass(frozen=True)
class AppointmentSummary:
    resource_id: str
    status: str
    start: str | None
    end: str | None


@dataclass(frozen=True)
class AccountSummary:
    resource_id: str
    status: str
    balance: Decimal | None
    currency: str | None


def _approved_icn(contract: _ApiContract, patient_icn: str) -> None:
    if os.getenv("VA_SANDBOX_ENABLED", "").lower() != "true" or (
        os.getenv(contract.read_gate, "").lower() != "true"
    ):
        raise VaResourceReadDisabled("VA resource read is disabled")
    allowed = {
        value.strip()
        for value in os.getenv(f"{contract.prefix}_ALLOWED_ICNS", "").split(",")
        if value.strip()
    }
    if not patient_icn or patient_icn not in allowed:
        raise VaSyntheticPatientDenied(
            "Synthetic patient is not allowlisted for this API"
        )


def _get_bundle(
    contract: _ApiContract,
    resource_type: str,
    patient_icn: str,
    *,
    scope: str,
    params: dict[str, str],
    launch: dict[str, str] | None,
    launch_sta3n_env: str | None = None,
    http: httpx.Client | None,
) -> dict[str, Any]:
    _approved_icn(contract, patient_icn)
    config = VaCcgConfig.from_environment(contract.prefix, name=contract.prefix)
    if config.token_url != contract.token_url:
        raise ValueError("Configured VA token endpoint does not match the API contract")
    launch_context = launch
    if launch_sta3n_env:
        sta3n = os.getenv(launch_sta3n_env, "").strip()
        if not sta3n:
            raise ValueError(f"Missing {launch_sta3n_env}")
        launch_context = {**(launch_context or {}), "sta3n": sta3n}
    required_scopes = {scope}
    if launch_context is not None:
        required_scopes.add("launch")
    with VaCcgClient(config, http=http) as client:
        return client.get_json(
            f"{contract.base_url}/{resource_type}",
            launch=launch_context,
            params=params,
            required_scopes=frozenset(required_scopes),
        )


def _search_resources(
    payload: dict[str, Any], expected_type: str
) -> tuple[dict[str, Any], ...]:
    if payload.get("resourceType") != "Bundle" or payload.get("type") != "searchset":
        raise VaFhirResponseError("VA response is not a FHIR search Bundle")
    entries = payload.get("entry", [])
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise VaFhirResponseError("FHIR Bundle entries are malformed")
    resources = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise VaFhirResponseError("FHIR Bundle entry is malformed")
        resource = entry.get("resource")
        if (
            not isinstance(resource, dict)
            or resource.get("resourceType") != expected_type
        ):
            raise VaFhirResponseError("FHIR Bundle contains an unexpected resource")
        resources.append(resource)
    return tuple(resources)


def _required_text(resource: dict[str, Any], name: str) -> str:
    value = resource.get(name)
    if not isinstance(value, str) or not value:
        raise VaFhirResponseError("FHIR resource is missing a required text field")
    return value


def _optional_text(resource: dict[str, Any], name: str) -> str | None:
    value = resource.get(name)
    if value is not None and not isinstance(value, str):
        raise VaFhirResponseError("FHIR resource contains an invalid text field")
    return value


def read_clinical_observations(
    patient_icn: str, *, http: httpx.Client | None = None
) -> tuple[ClinicalObservation, ...]:
    """Read minimized Clinical Health Observation metadata for an allowlisted ICN."""
    bundle = _get_bundle(
        _CLINICAL,
        "Observation",
        patient_icn,
        scope="system/Observation.read",
        params={"patient": patient_icn},
        launch={"patient": patient_icn},
        launch_sta3n_env="VA_CLINICAL_HEALTH_STA3N",
        http=http,
    )
    observations = []
    for resource in _search_resources(bundle, "Observation"):
        code = resource.get("code")
        if not isinstance(code, dict):
            raise VaFhirResponseError("FHIR Observation code is malformed")
        coding = code.get("coding", [])
        if not isinstance(coding, list):
            raise VaFhirResponseError("FHIR Observation coding is malformed")
        codes = []
        for item in coding:
            if not isinstance(item, dict):
                raise VaFhirResponseError("FHIR Observation coding is malformed")
            value = item.get("code")
            if value is not None and not isinstance(value, str):
                raise VaFhirResponseError("FHIR Observation code is malformed")
            if value:
                codes.append(value)
        effective = resource.get("effectiveDateTime")
        if effective is None and isinstance(resource.get("effectivePeriod"), dict):
            effective = resource["effectivePeriod"].get("start")
        if effective is not None and not isinstance(effective, str):
            raise VaFhirResponseError("FHIR Observation date is malformed")
        observations.append(
            ClinicalObservation(
                resource_id=_required_text(resource, "id"),
                status=_required_text(resource, "status"),
                codes=tuple(codes),
                effective_at=effective,
            )
        )
    return tuple(observations)


def read_patient_identity(
    patient_icn: str, *, http: httpx.Client | None = None
) -> tuple[PatientIdentity, ...]:
    """Confirm a Patient search match without returning demographics."""
    bundle = _get_bundle(
        _PATIENT,
        "Patient",
        patient_icn,
        scope="system/Patient.read",
        params={"identifier": patient_icn},
        launch={"patient": patient_icn},
        http=http,
    )
    patients = []
    for resource in _search_resources(bundle, "Patient"):
        identifiers = resource.get("identifier", [])
        if not isinstance(identifiers, list):
            raise VaFhirResponseError("FHIR Patient identifiers are malformed")
        matches = any(
            isinstance(identifier, dict) and identifier.get("value") == patient_icn
            for identifier in identifiers
        )
        if not matches:
            raise VaFhirResponseError(
                "FHIR Patient does not match the requested synthetic ICN"
            )
        patients.append(
            PatientIdentity(
                resource_id=_required_text(resource, "id"),
                identifier_confirmed=True,
            )
        )
    return tuple(patients)


def read_patient_appointments(
    patient_icn: str, *, http: httpx.Client | None = None
) -> tuple[AppointmentSummary, ...]:
    """Read status and timing only for allowlisted Patient Health appointments."""
    bundle = _get_bundle(
        _PATIENT,
        "Appointment",
        patient_icn,
        scope="system/Appointment.read",
        params={"patient": patient_icn},
        launch={"patient": patient_icn},
        http=http,
    )
    return tuple(
        AppointmentSummary(
            resource_id=_required_text(resource, "id"),
            status=_required_text(resource, "status"),
            start=_optional_text(resource, "start"),
            end=_optional_text(resource, "end"),
        )
        for resource in _search_resources(bundle, "Appointment")
    )


def read_health_care_accounts(
    patient_icn: str, *, http: httpx.Client | None = None
) -> tuple[AccountSummary, ...]:
    """Read minimal v0/r4 Account status and balance for an allowlisted ICN."""
    bundle = _get_bundle(
        _COSTS,
        "Account",
        patient_icn,
        scope="system/Account.read",
        params={"patient": patient_icn},
        launch={"patient": patient_icn},
        http=http,
    )
    accounts = []
    for resource in _search_resources(bundle, "Account"):
        amount = None
        currency = None
        balance = resource.get("balance")
        if balance is not None:
            if not isinstance(balance, dict):
                raise VaFhirResponseError("FHIR Account balance is malformed")
            raw_amount = balance.get("value")
            if raw_amount is not None:
                if isinstance(raw_amount, bool) or not isinstance(
                    raw_amount, (int, float, str)
                ):
                    raise VaFhirResponseError("FHIR Account balance is malformed")
                try:
                    amount = Decimal(str(raw_amount))
                except InvalidOperation as exc:
                    raise VaFhirResponseError(
                        "FHIR Account balance is malformed"
                    ) from exc
                if not amount.is_finite():
                    raise VaFhirResponseError("FHIR Account balance is malformed")
            currency = balance.get("currency")
            if currency is not None and not isinstance(currency, str):
                raise VaFhirResponseError("FHIR Account currency is malformed")
        accounts.append(
            AccountSummary(
                resource_id=_required_text(resource, "id"),
                status=_required_text(resource, "status"),
                balance=amount,
                currency=currency,
            )
        )
    return tuple(accounts)
