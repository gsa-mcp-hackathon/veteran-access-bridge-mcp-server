"""Fail-closed synthetic consent tests; no live databases or patient data."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veteran_access_bridge.app import synthetic_veteran_consent as consent
from veteran_access_bridge.app.synthetic_veteran_session import (
    COOKIE_NAME,
    CaseBinding,
    SessionDenied,
)

BINDING = CaseBinding(
    subject=UUID("c9de2570-9ebc-45dd-9447-e0a9bdae9660"),
    patient_id=UUID("fe0defc2-1ead-0eb7-2156-7eb36606e742"),
    identity_id=29,
    case_id="VAB-DEMO-20261113-CASE-031",
)
SECRET = "only-for-tests-" + "x" * 40
ORIGIN = "https://private-preview.example"


def _body(**overrides):
    data = {
        "case_id": BINDING.case_id,
        "option_id": "test-option",
        "slot_id": str(uuid4()),
        "idempotency_key": "decision-1",
        "correlation_id": "conversation-1",
        "confirmed": True,
    }
    return data | overrides


class Session:
    def authorize(self, cookie, case_id):
        if cookie != "approved-session" or case_id != BINDING.case_id:
            raise SessionDenied("Not authorized")
        return BINDING


class Gateway:
    def __init__(self):
        self.calls = []

    def record_internal_va_veteran_response_from_trusted_service(self, **kwargs):
        self.calls.append(kwargs)
        claims = jwt.decode(
            kwargs["assertion"],
            SECRET,
            algorithms=["HS256"],
            issuer=consent.ISSUER,
            audience=consent.AUDIENCE,
        )
        assert claims["sub"] == "synthetic-auth:" + str(BINDING.subject)
        assert claims["role"] == "VETERAN"
        assert claims["case_id"] == BINDING.case_id
        return SimpleNamespace(
            case_id=kwargs["case_id"],
            option_id=kwargs["option_id"],
            status="ACCEPTED" if kwargs["accepted"] else "REJECTED",
            decision_id=str(uuid4()),
            transition_id=str(uuid4()),
        )


@pytest.fixture
def client(monkeypatch):
    gateway = Gateway()
    capture = consent.ProtectedConsentCapture(
        sessions=Session(),
        read_connect=lambda: None,
        gateway=gateway,
        signing_secret=SECRET,
        host_subject="test-trusted-host",
        approved_case=BINDING.case_id,
    )
    app = FastAPI()
    app.include_router(consent.create_protected_consent_router(capture, origin=ORIGIN))
    browser = TestClient(app)
    browser.cookies.set(COOKIE_NAME, "approved-session")
    return browser, gateway


def test_consent_requires_origin_and_valid_session(client):
    browser, gateway = client
    assert (
        browser.post("/api/synthetic-veteran/consent", json=_body()).status_code == 403
    )
    browser.cookies.clear()
    assert (
        browser.post(
            "/api/synthetic-veteran/consent",
            json=_body(),
            headers={"Origin": ORIGIN},
        ).status_code
        == 403
    )
    assert not gateway.calls


def test_wrong_case_denied_without_persistence(client):
    browser, gateway = client
    result = browser.post(
        "/api/synthetic-veteran/consent",
        json=_body(case_id="OTHER-CASE"),
        headers={"Origin": ORIGIN},
    )
    assert result.status_code == 403
    assert gateway.calls == []


@pytest.mark.parametrize("confirmed", [True, False])
def test_authenticated_consent_uses_only_verified_source(
    client,
    monkeypatch,
    confirmed,
):
    browser, gateway = client
    monkeypatch.setattr(
        consent,
        "verified_consent_evidence",
        lambda *args, **kwargs: "approved-source",
    )
    result = browser.post(
        "/api/synthetic-veteran/consent",
        json=_body(confirmed=confirmed),
        headers={"Origin": ORIGIN},
    )
    assert result.status_code == 200
    body = result.json()
    assert body["confirmed"] is confirmed
    assert body["booking_created"] is False
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["verified_evidence_reference"] == "approved-source"
    assert gateway.calls[0]["accepted"] is confirmed
    assert "assertion" not in body


def test_missing_verified_evidence_cannot_record_consent(client, monkeypatch):
    browser, gateway = client

    def deny(*args, **kwargs):
        raise consent.ConsentNotReady("No independently verified slot")

    monkeypatch.setattr(consent, "verified_consent_evidence", deny)
    result = browser.post(
        "/api/synthetic-veteran/consent",
        json=_body(),
        headers={"Origin": ORIGIN},
    )
    assert result.status_code == 403
    assert not gateway.calls


class ReadOnlyConnection:
    def __init__(self, rows):
        self.rows = list(rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self

    def execute(self, _sql, _parameters):
        pass

    def fetchone(self):
        return self.rows.pop(0)


def test_unverified_identity_blocks_before_slot_lookup(monkeypatch):
    monkeypatch.setattr(
        consent,
        "assert_synthetic_scheduling_database",
        lambda *args, **kwargs: "vab_test",
    )
    rows = [
        (BINDING.patient_id, "PRIMARY_CARE", "OPEN", True),
        None,
    ]
    with pytest.raises(consent.ConsentNotReady, match="identity"):
        consent.verified_consent_evidence(
            lambda: ReadOnlyConnection(rows),
            binding=BINDING,
            option_id="test-option",
            slot_id=uuid4(),
            host_subject="test-trusted-host",
        )


def test_stale_or_unbound_slot_cannot_authorize_consent(monkeypatch):
    monkeypatch.setattr(
        consent,
        "assert_synthetic_scheduling_database",
        lambda *args, **kwargs: "vab_test",
    )
    now = datetime.now(timezone.utc)
    evidence_id = uuid4()
    slot_id = uuid4()
    identity = {
        "identity_verification_id": str(evidence_id),
        "case_id": BINDING.case_id,
        "patient_id": str(BINDING.patient_id),
        "synthetic": True,
        "verified": True,
        "outcome": "VERIFIED",
        "verification_method": consent.IDENTITY_METHOD,
        "verification_source": "PERSISTED_SYNTHETIC_CASE",
        "verifying_principal": "test-trusted-host",
        "verified_at": now.isoformat(),
        "expires_at": (now + consent.IDENTITY_TTL).isoformat(),
    }
    rows = [
        (BINDING.patient_id, "PRIMARY_CARE", "OPEN", True),
        (evidence_id, "corr", "test-trusted-host", now, identity),
        (
            "AVAILABLE",
            "VISTA",
            now + timedelta(days=1),
            now + timedelta(days=1, minutes=30),
            now - timedelta(minutes=16),
            "source-1",
            "PRIMARY_CARE",
            True,
            "synthetic_fixture",
            {
                "slot_bindings": {
                    str(slot_id): {
                        "case_id": BINDING.case_id,
                        "option_id": "test-option",
                    }
                }
            },
        ),
    ]
    with pytest.raises(consent.ConsentNotReady, match="slot"):
        consent.verified_consent_evidence(
            lambda: ReadOnlyConnection(rows),
            binding=BINDING,
            option_id="test-option",
            slot_id=slot_id,
            host_subject="test-trusted-host",
        )


def test_offer_listing_returns_empty_when_no_verified_slots(monkeypatch):
    monkeypatch.setattr(
        consent,
        "assert_synthetic_scheduling_database",
        lambda *args, **kwargs: "vab_test",
    )

    class EmptyOffers(ReadOnlyConnection):
        def fetchall(self):
            return []

    capture = consent.ProtectedConsentCapture(
        sessions=Session(),
        read_connect=lambda: EmptyOffers([]),
        gateway=Gateway(),
        signing_secret=SECRET,
        host_subject="test-trusted-host",
        approved_case=BINDING.case_id,
    )
    app = FastAPI()
    app.include_router(consent.create_protected_consent_router(capture, origin=ORIGIN))
    browser = TestClient(app)
    assert browser.get("/api/synthetic-veteran/consent/offers").status_code == 403
    browser.cookies.set(COOKIE_NAME, "approved-session")
    response = browser.get("/api/synthetic-veteran/consent/offers")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["offers"] == []


def test_rejects_consent_builder_if_session_case_disagrees(monkeypatch):
    monkeypatch.setenv("VAB_SUPABASE_TEST_MODE", "true")
    monkeypatch.setenv("VAB_SIGNED_DECISION_VERIFIER_SECRET", SECRET)
    monkeypatch.setenv("VAB_TRUSTED_HOST_SUBJECT", "test-trusted-host")
    monkeypatch.setenv("VAB_PRIVATE_PC_APPROVED_CASE", "different-case")

    class ConfiguredSession:
        _binding = BINDING

    with pytest.raises(PermissionError, match="approvals differ"):
        consent.build_protected_consent(ConfiguredSession())


@pytest.mark.parametrize(
    "correlation,evidence", [("other-call", "same"), ("this-call", "other")]
)
def test_voice_consent_rejects_other_call_identity(monkeypatch, correlation, evidence):
    monkeypatch.setattr(
        consent, "assert_synthetic_scheduling_database", lambda *a, **k: "vab_test"
    )
    event_id = uuid4()
    rows = [
        (BINDING.patient_id, "PRIMARY_CARE", "OPEN", True),
        (event_id, correlation, "test-trusted-host", datetime.now(timezone.utc), {}),
    ]
    with pytest.raises(consent.ConsentNotReady, match="exact voice call"):
        consent.verified_consent_evidence(
            lambda: ReadOnlyConnection(rows),
            binding=BINDING,
            option_id="test-option",
            slot_id=uuid4(),
            host_subject="test-trusted-host",
            voice_session_id="this-call",
            identity_verification_id=str(event_id)
            if evidence == "same"
            else str(uuid4()),
        )
