"""Offline tests for disabled, allowlisted VA FHIR resource readers."""
from __future__ import annotations

import base64
import json
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest

from veteran_access_bridge.adapters import va_ccg
from veteran_access_bridge.adapters.va_fhir_readers import (
    AccountSummary,
    AppointmentSummary,
    ClinicalObservation,
    PatientIdentity,
    VaFhirResponseError,
    VaResourceReadDisabled,
    VaSyntheticPatientDenied,
    read_clinical_observations,
    read_health_care_accounts,
    read_patient_appointments,
    read_patient_identity,
)

ICN = "TEST-SYNTHETIC-ICN"


def _configure(monkeypatch, prefix: str, *, token_url: str, scope: str) -> None:
    monkeypatch.setenv("VA_SANDBOX_ENABLED", "true")
    monkeypatch.setenv(f"{prefix}_RESOURCE_READ_ENABLED", "true")
    monkeypatch.setenv(f"{prefix}_ALLOWED_ICNS", ICN)
    monkeypatch.setenv(f"{prefix}_CLIENT_ID", "fixture-client")
    monkeypatch.setenv(f"{prefix}_TOKEN_URL", token_url)
    monkeypatch.setenv(f"{prefix}_TOKEN_AUDIENCE", "https://issuer.example/token")
    monkeypatch.setenv(f"{prefix}_SCOPE", scope)
    monkeypatch.setenv(f"{prefix}_PRIVATE_KEY_PATH", "/fixture/private-key.pem")
    monkeypatch.setattr(
        va_ccg.VaCcgClient, "client_assertion", lambda self: "fixture-assertion"
    )


def _bundle(resource_type: str, resource: dict) -> dict:
    return {
        "resourceType": "Bundle",
        "type": "searchset",
        "total": 1,
        "entry": [{"resource": {"resourceType": resource_type, **resource}}],
    }


def _http_client(*, token_url: str, resource_url: str, scope: str,
                 launch: dict[str, str] | None, params: dict[str, str],
                 response: dict) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            assert str(request.url) == token_url
            assert request.headers["Content-Type"].startswith(
                "application/x-www-form-urlencoded"
            )
            form = parse_qs(request.content.decode())
            assert form["scope"] == [scope]
            if launch is None:
                assert "launch" not in form
            else:
                decoded_launch = json.loads(base64.b64decode(form["launch"][0]))
                assert decoded_launch == launch
            return httpx.Response(
                200, json={"access_token": "fixture-resource-token", "expires_in": 300}
            )

        assert request.method == "GET"
        assert str(request.url).split("?", 1)[0] == resource_url
        assert dict(request.url.params) == params
        assert request.headers["Authorization"] == "Bearer fixture-resource-token"
        assert "application/fhir+json" in request.headers["Accept"]
        assert "application/json+fhir" in request.headers["Accept"]
        return httpx.Response(200, json=response)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return client, seen


def test_clinical_observation_uses_patient_launch_and_minimal_projection(monkeypatch):
    prefix = "VA_CLINICAL_HEALTH"
    token_url = "https://sandbox-api.va.gov/oauth2/clinical-health/system/v1/token"
    resource_url = "https://sandbox-api.va.gov/services/clinical-fhir/v1/r4/Observation"
    scope = "launch system/Observation.read"
    _configure(monkeypatch, prefix, token_url=token_url, scope=scope)
    monkeypatch.setenv("VA_CLINICAL_HEALTH_STA3N", "528")
    http, seen = _http_client(
        token_url=token_url,
        resource_url=resource_url,
        scope=scope,
        launch={"patient": ICN, "sta3n": "528"},
        params={"patient": ICN},
        response=_bundle("Observation", {
            "id": "obs-1",
            "status": "final",
            "code": {"coding": [{"system": "urn:fixture", "code": "X1"}]},
            "effectiveDateTime": "2026-01-02T03:04:05Z",
            "valueQuantity": {"value": 999, "unit": "not-returned"},
        }),
    )
    try:
        result = read_clinical_observations(ICN, http=http)
        assert result == (
            ClinicalObservation("obs-1", "final", ("X1",), "2026-01-02T03:04:05Z"),
        )
        assert not hasattr(result[0], "value")
        assert [request.method for request in seen] == ["POST", "GET"]
    finally:
        http.close()


def test_patient_health_identity_requires_and_confirms_identifier(monkeypatch):
    prefix = "VA_PATIENT_HEALTH"
    token_url = "https://sandbox-api.va.gov/oauth2/health/system/v1/token"
    resource_url = "https://sandbox-api.va.gov/services/fhir/v0/r4/Patient"
    scope = "launch system/Patient.read system/Appointment.read"
    _configure(monkeypatch, prefix, token_url=token_url, scope=scope)
    http, _ = _http_client(
        token_url=token_url,
        resource_url=resource_url,
        scope=scope,
        launch={"patient": ICN},
        params={"identifier": ICN},
        response=_bundle("Patient", {
            "id": "patient-1",
            "identifier": [{"system": "urn:fixture", "value": ICN}],
            "name": [{"text": "never projected"}],
            "birthDate": "2000-01-01",
        }),
    )
    try:
        result = read_patient_identity(ICN, http=http)
        assert result == (PatientIdentity("patient-1", True),)
        assert "never projected" not in str(result)
    finally:
        http.close()


def test_clinical_reader_requires_station_context_before_token_request(monkeypatch):
    prefix = "VA_CLINICAL_HEALTH"
    token_url = "https://sandbox-api.va.gov/oauth2/clinical-health/system/v1/token"
    _configure(
        monkeypatch,
        prefix,
        token_url=token_url,
        scope="launch system/Observation.read",
    )
    monkeypatch.delenv("VA_CLINICAL_HEALTH_STA3N", raising=False)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: pytest.fail("missing station context must not call network")
        )
    ) as http:
        with pytest.raises(ValueError, match="VA_CLINICAL_HEALTH_STA3N"):
            read_clinical_observations(ICN, http=http)


def test_patient_health_appointment_uses_patient_search_and_minimal_projection(
    monkeypatch,
):
    prefix = "VA_PATIENT_HEALTH"
    token_url = "https://sandbox-api.va.gov/oauth2/health/system/v1/token"
    resource_url = "https://sandbox-api.va.gov/services/fhir/v0/r4/Appointment"
    scope = "launch system/Appointment.read"
    _configure(monkeypatch, prefix, token_url=token_url, scope=scope)
    http, _ = _http_client(
        token_url=token_url,
        resource_url=resource_url,
        scope=scope,
        launch={"patient": ICN},
        params={"patient": ICN},
        response=_bundle("Appointment", {
            "id": "appointment-1",
            "status": "booked",
            "start": "2026-02-01T10:00:00Z",
            "end": "2026-02-01T10:30:00Z",
            "description": "not projected",
        }),
    )
    try:
        result = read_patient_appointments(ICN, http=http)
        assert result == (
            AppointmentSummary(
                "appointment-1", "booked",
                "2026-02-01T10:00:00Z", "2026-02-01T10:30:00Z",
            ),
        )
        assert "not projected" not in str(result)
    finally:
        http.close()


def test_costs_account_uses_system_scope_v0_patient_query_without_launch(monkeypatch):
    prefix = "VA_HEALTH_CARE_COSTS"
    token_url = "https://sandbox-api.va.gov/oauth2/health-care-costs-coverage/system/v1/token"
    resource_url = (
        "https://sandbox-api.va.gov/services/health-care-costs-coverage/v0/r4/Account"
    )
    scope = "launch system/Account.read"
    _configure(monkeypatch, prefix, token_url=token_url, scope=scope)
    http, _ = _http_client(
        token_url=token_url,
        resource_url=resource_url,
        scope=scope,
        launch={"patient": ICN},
        params={"patient": ICN},
        response=_bundle("Account", {
            "id": "account-1",
            "status": "active",
            "balance": {"value": "12.34", "currency": "USD"},
            "name": "not projected",
        }),
    )
    try:
        result = read_health_care_accounts(ICN, http=http)
        assert result == (
            AccountSummary("account-1", "active", Decimal("12.34"), "USD"),
        )
        assert "not projected" not in str(result)
    finally:
        http.close()


def test_readers_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("VA_SANDBOX_ENABLED", raising=False)
    with httpx.Client(transport=httpx.MockTransport(
            lambda _: pytest.fail("disabled reader must not call network"))) as http:
        with pytest.raises(VaResourceReadDisabled):
            read_patient_identity(ICN, http=http)


def test_api_specific_allowlist_denies_before_token_request(monkeypatch):
    prefix = "VA_PATIENT_HEALTH"
    token_url = "https://sandbox-api.va.gov/oauth2/health/system/v1/token"
    _configure(
        monkeypatch, prefix, token_url=token_url,
        scope="launch system/Patient.read",
    )
    monkeypatch.setenv(f"{prefix}_ALLOWED_ICNS", "DIFFERENT-SYNTHETIC-ICN")
    with httpx.Client(transport=httpx.MockTransport(
            lambda _: pytest.fail("denied patient must not call network"))) as http:
        with pytest.raises(VaSyntheticPatientDenied):
            read_patient_identity(ICN, http=http)


def test_patient_response_context_mismatch_is_rejected(monkeypatch):
    prefix = "VA_PATIENT_HEALTH"
    token_url = "https://sandbox-api.va.gov/oauth2/health/system/v1/token"
    resource_url = "https://sandbox-api.va.gov/services/fhir/v0/r4/Patient"
    scope = "launch system/Patient.read"
    _configure(monkeypatch, prefix, token_url=token_url, scope=scope)
    http, _ = _http_client(
        token_url=token_url,
        resource_url=resource_url,
        scope=scope,
        launch={"patient": ICN},
        params={"identifier": ICN},
        response=_bundle("Patient", {
            "id": "patient-2",
            "identifier": [{"value": "OTHER-SYNTHETIC-ICN"}],
        }),
    )
    try:
        with pytest.raises(VaFhirResponseError, match="does not match"):
            read_patient_identity(ICN, http=http)
    finally:
        http.close()


def test_costs_adapter_rejects_nonmatching_configured_token_endpoint(monkeypatch):
    prefix = "VA_HEALTH_CARE_COSTS"
    _configure(
        monkeypatch,
        prefix,
        token_url="https://sandbox-api.va.gov/oauth2/clinical-health/system/v1/token",
        scope="system/Account.read",
    )
    with httpx.Client(transport=httpx.MockTransport(
            lambda _: pytest.fail("misconfigured API must not call network"))) as http:
        with pytest.raises(ValueError, match="does not match the API contract"):
            read_health_care_accounts(ICN, http=http)
