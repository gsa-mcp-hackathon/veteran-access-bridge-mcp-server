"""Protected HTTP boundary tests; all host credentials and state are synthetic."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from starlette.testclient import TestClient

from veteran_access_bridge.app import private_primary_care_booking as boundary
from veteran_access_bridge.services import pg_governed_va_commit
from veteran_access_bridge.services.pg_governed_va_commit import (
    POLICY_VERSION,
    SCOPE,
    VABookingReceipt,
    VABookingRequest,
    _ids,
)
from veteran_access_bridge.services.private_va_booking_grant_issuer import (
    EvaluatedBookingPolicy,
)
from veteran_access_bridge.services.signed_scheduling_lifecycle import (
    TrustedSchedulingServices,
)
from veteran_access_bridge.services.trusted_primary_care import (
    RECOVERY_SCOPE,
    PostgresHostAssertionReplayGuard,
    TrustedHostAuthenticator,
)

SECRET = "test-only-private-booking-secret-" + "x" * 40
CASE = boundary.APPROVED_CASE


class ReplayGuard(PostgresHostAssertionReplayGuard):
    def __init__(self):
        self.used = set()

    def consume(self, *, issuer, subject, token_id, expires_at):
        key = (issuer, subject, token_id)
        if key in self.used:
            raise PermissionError("Replay")
        self.used.add(key)


class Connection:
    def __init__(self, now, state):
        self.now = now
        self.state = state
        self.statement = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self

    def fetchone(self):
        if self.statement.startswith("SELECT i.correlation_id"):
            return self.state.get("voice_evidence_correlations")
        if self.statement.startswith("SELECT EXISTS (SELECT 1 FROM vab.audit_event"):
            return (self.state["voice_correlations_match"],)
        if self.statement.startswith("SELECT actor,details"):
            return self.state.get("recovery_audit")
        if self.statement.startswith("SELECT a.appointment_id"):
            return self.state.get("recovery_appointment")
        if self.statement.startswith("SELECT evidence,actor_id"):
            return self.state.get("recovery_transition")
        if self.statement.startswith("SELECT details,actor"):
            return self.state.get("recovery_audit_details")
        if self.state["missing_consent"]:
            return None
        return self.now - self.state["consent_age"], self.now

    def fetchall(self):
        return self.state.get("recovery_decisions", [])


@pytest.fixture
def harness(monkeypatch):
    now = datetime.now(timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    auth = TrustedHostAuthenticator(
        issuer="test-issuer",
        audience="test-audience",
        subject="test-host",
        public_key_pem=public_key,
        replay_guard=ReplayGuard(),
    )
    state = {
        "identity": str(uuid4()),
        "confirmation": uuid4(),
        "decision": "ALLOW",
        "commits": 0,
        "readback": True,
        "appointment": str(uuid4()),
        "missing_consent": False,
        "consent_age": timedelta(seconds=5),
        "voice_correlations_match": True,
    }
    services = TrustedSchedulingServices(
        connect=lambda: Connection(now, state),
        verifier_secret=SECRET,
        va_booking_verifier_secret=SECRET,
    )

    def evaluate(_self, request, _actor):
        return EvaluatedBookingPolicy(
            case_id=request.case_id,
            option_id=request.option_id,
            slot_id=request.slot_id,
            identity_verification_id=state["identity"],
            identity_verification_expires_at=now + timedelta(minutes=5),
            veteran_confirmation_id=state["confirmation"],
            policy_evidence_reference="test-evidence",
            decision=state["decision"],
            human_review_required=False,
            synthetic=True,
            care_pathway="INTERNAL_VA",
        )

    def commit(_self, *, assertion, request):
        state["grant_claims"] = pg_governed_va_commit._verified_booking_claims(
            assertion, SECRET, request
        )
        state["commits"] += 1
        return VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            state["appointment"],
            now,
            now + timedelta(minutes=30),
            True,
        )

    def inspect(_self, *, assertion, request):
        if not state["readback"]:
            raise RuntimeError("test database unavailable")
        return VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            state["appointment"],
            now,
            now + timedelta(minutes=30),
            True,
        )

    monkeypatch.setattr(
        boundary.PostgresPrimaryCarePolicyEvaluator, "__call__", evaluate
    )
    monkeypatch.setattr(
        boundary, "assert_synthetic_scheduling_database", lambda *_a, **_kw: "vab_test"
    )

    def execute(cur, _schema, statement, params=None):
        cur.statement = statement
        if statement.startswith("SELECT EXISTS (SELECT 1 FROM vab.audit_event"):
            state["voice_binding_params"] = params

    monkeypatch.setattr(boundary, "execute_scheduling_sql", execute)
    monkeypatch.setattr(
        pg_governed_va_commit,
        "assert_synthetic_scheduling_database",
        lambda *_a, **_kw: "vab_test",
    )
    monkeypatch.setattr(pg_governed_va_commit, "execute_scheduling_sql", execute)
    monkeypatch.setattr(TrustedSchedulingServices, "commit_internal_va_booking", commit)
    monkeypatch.setattr(
        TrustedSchedulingServices, "inspect_internal_va_booking", inspect
    )
    app = FastAPI()
    app.include_router(
        boundary.create_private_booking_router(
            boundary.ProtectedPrimaryCareBooking(
                services=services, authenticator=auth, signing_secret=SECRET
            )
        )
    )
    body = {
        "case_id": CASE,
        "option_id": "test-option",
        "slot_id": str(uuid4()),
        "idempotency_key": "test-idempotency",
    }

    def token(**overrides):
        claims = {
            "iss": "test-issuer",
            "aud": "test-audience",
            "sub": "test-host",
            "scope": SCOPE,
            "case_ids": [CASE],
            **body,
            "identity_verification_id": state["identity"],
            "veteran_confirmation_id": str(state["confirmation"]),
            "consent_response": "CONFIRMED",
            "consent_expires_at": int((now + timedelta(minutes=2)).timestamp()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=2)).timestamp()),
            "jti": uuid4().hex,
        }
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256")

    return TestClient(app), body, token, state


def _call(client, body, token):
    return client.post(
        "/internal/synthetic-primary-care/booking",
        json=body,
        headers={"Authorization": "Bearer " + token},
    )


def test_booking_requires_auth_and_returns_only_verified_receipt(harness):
    client, body, token, state = harness
    assert (
        client.post("/internal/synthetic-primary-care/booking", json=body).status_code
        == 401
    )
    response = _call(client, body, token())
    assert response.status_code == 200
    assert response.json()["appointment_id"] == state["appointment"]
    assert "assertion" not in response.json()
    assert state["commits"] == 1


def test_replayed_host_assertion_never_submits_twice(harness):
    client, body, token, state = harness
    assertion = token()
    assert _call(client, body, assertion).status_code == 200
    assert _call(client, body, assertion).status_code == 403
    assert state["commits"] == 1


def test_voice_booking_requires_persisted_identity_and_consent_from_same_call(harness):
    client, body, token, state = harness
    state["voice_correlations_match"] = False
    assert (
        _call(client, body, token(voice_session_id="vs-test-call")).status_code == 403
    )
    assert state["commits"] == 0

    state["voice_correlations_match"] = True
    assert (
        _call(client, body, token(voice_session_id="vs-test-call")).status_code == 200
    )
    assert state["voice_binding_params"] == (
        state["identity"],
        "SYNTHETIC_IDENTITY_VERIFICATION",
        body["case_id"],
        "vs-test-call",
        state["confirmation"],
        body["case_id"],
    )
    assert state["commits"] == 1


@pytest.mark.parametrize("voice_session_id", [None, "", " ", " vs-test", 42, "a" * 129])
def test_rejects_invalid_voice_session_binding(harness, voice_session_id):
    client, body, token, state = harness
    assert (
        _call(client, body, token(voice_session_id=voice_session_id)).status_code == 403
    )
    assert state["commits"] == 0


def test_booking_grant_expires_no_later_than_consent(harness, monkeypatch):
    client, body, token, _state = harness
    captured = []
    original = TrustedSchedulingServices.commit_internal_va_booking

    def commit(self, *, assertion, request):
        captured.append(jwt.decode(assertion, options={"verify_signature": False}))
        return original(self, assertion=assertion, request=request)

    monkeypatch.setattr(TrustedSchedulingServices, "commit_internal_va_booking", commit)
    expiry = int((datetime.now(timezone.utc) + timedelta(seconds=20)).timestamp())
    assert _call(client, body, token(consent_expires_at=expiry)).status_code == 200
    assert captured[0]["exp"] <= expiry


@pytest.mark.parametrize(
    "overrides",
    [
        {"option_id": "wrong-option"},
        {"slot_id": str(uuid4())},
        {"case_ids": ["other-case"]},
        {"identity_verification_id": "wrong-identity"},
        {"veteran_confirmation_id": str(uuid4())},
        {"consent_response": "DECLINED"},
        {"consent_expires_at": 1},
        {"exp": 1},
    ],
)
def test_rejects_mismatched_or_expired_host_evidence(harness, overrides):
    client, body, token, state = harness
    assert _call(client, body, token(**overrides)).status_code == 403
    assert state["commits"] == 0


def test_rejects_forged_assertion_and_policy_denial(harness):
    client, body, token, state = harness
    assertion = token()
    assert _call(client, body, assertion[:-5] + "abcde").status_code == 403
    state["decision"] = "REVIEW"
    assert _call(client, body, token()).status_code == 403
    assert state["commits"] == 0


def test_readback_failure_never_returns_success(harness):
    client, body, token, state = harness
    state["readback"] = False
    response = _call(client, body, token())
    assert response.status_code == 409
    assert "recovery" in response.json()["detail"].lower()
    assert state["commits"] == 1


@pytest.mark.parametrize("condition", ["missing", "stale"])
def test_missing_or_stale_persisted_consent_never_commits(harness, condition):
    client, body, token, state = harness
    if condition == "missing":
        state["missing_consent"] = True
    else:
        state["consent_age"] = timedelta(minutes=10)
    assert _call(client, body, token()).status_code == 403
    assert state["commits"] == 0


def test_database_failure_never_returns_booking(harness, monkeypatch):
    client, body, token, state = harness

    def fail(*_args, **_kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(boundary, "execute_scheduling_sql", fail)
    response = _call(client, body, token())
    assert response.status_code == 503
    assert state["commits"] == 0


def test_fresh_assertion_cannot_override_policy_denial_after_booking(harness):
    client, body, token, state = harness
    assert _call(client, body, token()).status_code == 200
    state["decision"] = "DENY"
    assert _call(client, body, token()).status_code == 403
    assert state["commits"] == 1


def _recovery_fixture(body, state):
    request = VABookingRequest(
        body["case_id"],
        body["option_id"],
        UUID(body["slot_id"]),
        body["idempotency_key"],
    )
    appointment_id, transition_id, _ = _ids(request)
    state["appointment"] = str(appointment_id)
    now = datetime.now(timezone.utc)
    patient_id = uuid4()
    details = {
        "synthetic": True,
        "care_pathway": "INTERNAL_VA",
        "appointment_id": str(appointment_id),
        "case_id": body["case_id"],
        "option_id": body["option_id"],
        "slot_id": body["slot_id"],
        "idempotency_key": body["idempotency_key"],
        "service_actor": "test-host",
        "identity_verified": True,
        "identity_case_id": body["case_id"],
        "identity_verification_id": state["identity"],
        "identity_verification_expires_at": int(
            (now + timedelta(minutes=5)).timestamp()
        ),
        "policy_version": POLICY_VERSION,
        "scheduler_approval_required": False,
        "authorization_mode": "TRUSTED_SERVICE_POLICY_GRANT",
        "policy_decision": "ALLOW",
        "policy_evidence_reference": "policy-evidence",
        "human_review_required": False,
        "veteran_confirmation_id": str(state["confirmation"]),
        "channel": "VISTA",
        "service_assertion_id": "original-grant-id",
    }
    state["recovery_audit"] = ("test-host", details)
    state["recovery_audit_details"] = (details, "test-host")
    state["recovery_transition"] = (details, "test-host")
    state["recovery_appointment"] = (
        appointment_id,
        "BOOKED_SIMULATED",
        "test-host",
        request.slot_id,
        "VISTA",
        "BOOKED",
        now + timedelta(days=1),
        now + timedelta(days=1, minutes=30),
        request.case_id,
        "PRIMARY_CARE",
        patient_id,
        patient_id,
        "Demo Primary Care",
        "Dr. Example",
    )
    evidence = {"service_evidence_reference": "synthetic-source"}
    state["recovery_decisions"] = [
        (
            state["confirmation"],
            "ACCEPTED",
            request.option_id,
            "VETERAN_CONFIRMED",
            "VETERAN",
            "test-veteran",
            1,
            evidence,
            transition_id,
            "VETERAN_CONFIRMATION_RECORDED",
            "VETERAN",
            "test-veteran",
            evidence,
        )
    ]


def test_recovery_verifies_original_persisted_receipt_without_resubmitting(harness):
    client, body, token, state = harness
    _recovery_fixture(body, state)
    assertion = token(scope=RECOVERY_SCOPE)
    path = "/internal/synthetic-primary-care/recovery"
    response = client.post(
        path, json=body, headers={"Authorization": "Bearer " + assertion}
    )
    assert response.status_code == 200
    assert response.json()["appointment_id"] == state["appointment"]
    assert state["commits"] == 0
    assert (
        client.post(
            path, json=body, headers={"Authorization": "Bearer " + assertion}
        ).status_code
        == 403
    )
    recovered_again = client.post(
        path,
        json=body,
        headers={"Authorization": "Bearer " + token(scope=RECOVERY_SCOPE)},
    )
    assert recovered_again.status_code == 200
    assert recovered_again.json()["appointment_id"] == state["appointment"]
    assert recovered_again.json()["clinic_name"] == "Demo Primary Care"
    assert recovered_again.json()["provider_name"] == "Dr. Example"
    assert state["commits"] == 0


@pytest.mark.parametrize("damage", ["missing", "audit", "decision", "slot", "actor"])
def test_recovery_never_confirms_missing_or_conflicting_evidence(harness, damage):
    client, body, token, state = harness
    _recovery_fixture(body, state)
    if damage == "missing":
        state["recovery_audit"] = None
    elif damage == "audit":
        state["recovery_audit_details"] = ({"synthetic": True}, "test-host")
    elif damage == "decision":
        state["recovery_decisions"] = []
    elif damage == "slot":
        row = list(state["recovery_appointment"])
        row[5] = "AVAILABLE"
        state["recovery_appointment"] = tuple(row)
    else:
        state["recovery_audit"] = ("other-host", state["recovery_audit"][1])
    response = client.post(
        "/internal/synthetic-primary-care/recovery",
        json=body,
        headers={"Authorization": "Bearer " + token(scope=RECOVERY_SCOPE)},
    )
    assert response.status_code in {403, 409}
    assert state["commits"] == 0


def test_recovery_rejects_booking_scope_and_mismatched_identity(harness):
    client, body, token, state = harness
    _recovery_fixture(body, state)
    path = "/internal/synthetic-primary-care/recovery"
    for assertion in (
        token(),
        token(scope=RECOVERY_SCOPE, option_id="wrong"),
        token(scope=RECOVERY_SCOPE, idempotency_key="different"),
        token(scope=RECOVERY_SCOPE, exp=1),
    ):
        assert (
            client.post(
                path, json=body, headers={"Authorization": "Bearer " + assertion}
            ).status_code
            == 403
        )
    assert state["commits"] == 0


def test_protected_route_disabled_by_default(monkeypatch):
    from veteran_access_bridge.app import asgi

    monkeypatch.delenv("VAB_ENABLE_PRIVATE_PC_BOOKING_ENDPOINT", raising=False)
    app = asgi._build_app()
    assert not any(
        getattr(route, "path", "") == "/internal/synthetic-primary-care/booking"
        for route in app.routes
    )


def test_protected_route_cannot_enable_without_private_configuration(monkeypatch):
    from veteran_access_bridge.app import asgi

    monkeypatch.setenv("VAB_ENABLE_PRIVATE_PC_BOOKING_ENDPOINT", "true")
    monkeypatch.delenv("VAB_SIGNED_DECISION_VERIFIER_SECRET", raising=False)
    with pytest.raises(PermissionError, match="verifier"):
        asgi._build_app()


def test_private_booking_requires_exactly_one_reviewed_case():
    class Services:
        def _va_booking_secret(self):
            return SECRET

    for invalid in ("", " ", " case-with-space ", "x" * 129):
        with pytest.raises(PermissionError, match="approved synthetic case"):
            boundary.ProtectedPrimaryCareBooking(
                services=Services(),
                authenticator=object(),
                signing_secret=SECRET,
                approved_case=invalid,
            )

    assert CASE == "VAB-DEMO-20261113-CASE-031"
    configured = boundary.ProtectedPrimaryCareBooking(
        services=Services(),
        authenticator=object(),
        signing_secret=SECRET,
        approved_case=CASE,
    )
    request = VABookingRequest(
        case_id=CASE,
        option_id="test-option",
        slot_id=uuid4(),
        idempotency_key="test-idempotency",
    )
    other_request = VABookingRequest(
        case_id="VAB-DEMO-20261113-CASE-033",
        option_id=request.option_id,
        slot_id=request.slot_id,
        idempotency_key=request.idempotency_key,
    )
    with pytest.raises(PermissionError, match="not approved"):
        configured.book(assertion="unused", request=other_request)
    with pytest.raises(PermissionError, match="not approved"):
        configured.recover(assertion="unused", request=other_request)


def test_signed_voice_binding_reaches_private_booking_grant(harness):
    client, body, token, state = harness
    assert _call(client, body, token(voice_session_id="vs-call")).status_code == 200
    assert state["grant_claims"]["voice_session_id"] == "vs-call"


@pytest.mark.parametrize("call_id", [None, "other", "", " vs-call", "vs\ncall"])
def test_recovery_cannot_drop_or_change_original_voice_binding(harness, call_id):
    client, body, token, state = harness
    _recovery_fixture(body, state)
    state["recovery_audit"][1]["voice_session_id"] = "vs-call"
    overrides = {} if call_id is None else {"voice_session_id": call_id}
    response = client.post(
        "/internal/synthetic-primary-care/recovery",
        json=body,
        headers={"Authorization": "Bearer " + token(scope=RECOVERY_SCOPE, **overrides)},
    )
    assert response.status_code == 403
    assert state["commits"] == 0


def test_voice_recovery_verifies_same_call_without_resubmission(harness):
    client, body, token, state = harness
    _recovery_fixture(body, state)
    state["recovery_audit"][1]["voice_session_id"] = "vs-call"
    state["voice_evidence_correlations"] = ("vs-call",) * 3
    response = client.post(
        "/internal/synthetic-primary-care/recovery",
        json=body,
        headers={
            "Authorization": "Bearer "
            + token(scope=RECOVERY_SCOPE, voice_session_id="vs-call")
        },
    )
    assert response.status_code == 200
    assert response.json()["voice_session_id"] == "vs-call"
    assert state["commits"] == 0
