"""Offline tests of the opt-in synthetic session and trusted identity boundary."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veteran_access_bridge.app import synthetic_veteran_session as session_module
from veteran_access_bridge.app.private_primary_care_booking import (
    create_private_booking_router,
)
from veteran_access_bridge.app.synthetic_veteran_host_issuer import (
    SyntheticVeteranHostIssuer,
    build_synthetic_veteran_host_issuer,
)
from veteran_access_bridge.app.synthetic_veteran_session import (
    AUTH_URL,
    COOKIE_NAME,
    CaseBinding,
    SessionDenied,
    SupabaseAuth,
    SyntheticVeteranSessions,
    create_synthetic_veteran_session_router,
)
from veteran_access_bridge.services.trusted_primary_care import (
    IDENTITY_SCOPE,
    PostgresHostAssertionReplayGuard,
    TrustedHostAuthenticator,
)

ORIGIN = "https://vab.example"
JWT_KEY = "test-only-signing-key-not-a-real-supabase-key"
CASE = "VAB-DEMO-20261113-CASE-031"


@pytest.fixture
def harness(monkeypatch):
    subject, patient_id = uuid4(), uuid4()
    binding = CaseBinding(subject, patient_id, 41, CASE)
    state = {
        "binding": binding,
        "queries": [],
        "revoked": set(),
        "refreshes": 0,
        "tamper": False,
        "refresh_rejected": False,
        "refresh_subject": subject,
        "different_session": False,
        "expired_token": False,
        "access_survives_logout": False,
    }

    def token(user_id, session_id):
        return jwt.encode(
            {
                "iss": AUTH_URL,
                "aud": "authenticated",
                "role": "authenticated",
                "sub": str(user_id),
                "session_id": str(session_id),
                "exp": int(time.time()) + (-1 if state["expired_token"] else 600),
            },
            JWT_KEY,
            algorithm="HS256",
        )

    def auth_request(request):
        path = request.url.path
        if path.endswith("/token"):
            body = json.loads(request.content)
            if request.url.params["grant_type"] == "password":
                if body != {"email": "synthetic@example.test", "password": "test-pass"}:
                    return httpx.Response(400, json={"error": "invalid"})
                sid = uuid4()
                access = token(subject, sid)
                if state["tamper"]:
                    prefix, signature = access.rsplit(".", 1)
                    signature = ("A" if signature[0] != "A" else "B") + signature[1:]
                    access = prefix + "." + signature
                return httpx.Response(
                    200,
                    json={"access_token": access, "refresh_token": str(sid)},
                )
            state["refreshes"] += 1
            sid = body["refresh_token"]
            if state["refresh_rejected"] or sid in state["revoked"]:
                return httpx.Response(400, json={"error": "revoked"})
            refreshed_sid = uuid4() if state["different_session"] else sid
            return httpx.Response(
                200,
                json={
                    "access_token": token(state["refresh_subject"], refreshed_sid),
                    "refresh_token": str(refreshed_sid),
                },
            )
        if path.endswith("/user"):
            access = request.headers.get("authorization", "").removeprefix("Bearer ")
            try:
                claims = jwt.decode(
                    access,
                    JWT_KEY,
                    algorithms=["HS256"],
                    audience="authenticated",
                    issuer=AUTH_URL,
                )
            except jwt.PyJWTError:
                return httpx.Response(401, json={"error": "invalid"})
            if (
                claims["session_id"] in state["revoked"]
                and not state["access_survives_logout"]
            ):
                return httpx.Response(401, json={"error": "revoked"})
            return httpx.Response(200, json={"id": claims["sub"]})
        if path.endswith("/logout"):
            claims = jwt.decode(
                request.headers["authorization"].removeprefix("Bearer "),
                JWT_KEY,
                algorithms=["HS256"],
                audience="authenticated",
                issuer=AUTH_URL,
            )
            state["revoked"].add(claims["session_id"])
            return httpx.Response(204)
        raise AssertionError("Unexpected Auth request")

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            state["queries"].append((query, params))
            self.result = params == (
                state["binding"].identity_id,
                state["binding"].patient_id,
                state["binding"].case_id,
            )

        def fetchone(self):
            return (self.result,)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    @contextmanager
    def connect():
        yield Connection()

    monkeypatch.setattr(
        session_module,
        "assert_synthetic_scheduling_database",
        lambda *_a, **_kw: "vab_test",
    )
    auth_client = httpx.Client(transport=httpx.MockTransport(auth_request))
    auth = SupabaseAuth(key="sb_publishable_test_key", client=auth_client)
    sessions = SyntheticVeteranSessions(auth=auth, binding=binding, connect=connect)
    app = FastAPI()
    app.include_router(create_synthetic_veteran_session_router(sessions, origin=ORIGIN))
    app.include_router(create_private_booking_router(object()))
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, sessions, state, binding
    auth_client.close()


def _sign_in(client):
    return client.post(
        "/api/synthetic-veteran/session",
        headers={"Origin": ORIGIN},
        json={"email": "synthetic@example.test", "password": "test-pass"},
    )


def test_valid_session_uses_server_credentials_and_readonly_case_binding(harness):
    client, _, state, binding = harness
    response = _sign_in(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert "test-pass" not in cookie and "refresh" not in cookie
    assert response.json() == {"authenticated": True, "synthetic": True}
    current = client.get("/api/synthetic-veteran/session")
    assert current.json() == {
        "authenticated": True,
        "synthetic": True,
        "case_id": binding.case_id,
    }
    assert current.headers["cache-control"] == "no-store"
    assert state["refreshes"] == 1
    assert all(
        "FROM vab_test.patient_identity" in query
        and "vab_test.scheduling_case_link" in query
        and query.startswith("SELECT")
        for query, _ in state["queries"]
    )


def test_expired_local_session_and_revoked_auth_session_fail_closed(harness):
    client, sessions, state, _ = harness
    assert _sign_in(client).status_code == 200
    cookie = client.cookies.get(COOKIE_NAME)
    sessions._sessions[cookie].expires_at = time.monotonic() - 1
    assert client.get("/api/synthetic-veteran/session").status_code == 401
    assert _sign_in(client).status_code == 200
    state["refresh_rejected"] = True
    assert client.get("/api/synthetic-veteran/session").status_code == 401
    assert client.get("/api/synthetic-veteran/session").status_code == 401


def test_session_expiring_during_refresh_is_not_authorized(harness, monkeypatch):
    client, sessions, _, _ = harness
    assert _sign_in(client).status_code == 200
    cookie = client.cookies.get(COOKIE_NAME)
    refresh = sessions._auth.refresh

    def expiring_refresh(tokens):
        result = refresh(tokens)
        sessions._sessions[cookie].expires_at = time.monotonic() - 1
        return result

    monkeypatch.setattr(sessions._auth, "refresh", expiring_refresh)
    assert client.get("/api/synthetic-veteran/session").status_code == 401


def test_token_expiring_before_session_creation_is_rejected(harness, monkeypatch):
    client, sessions, _, _ = harness
    sign_in = sessions._auth.sign_in

    def expired_sign_in(email, password):
        return replace(sign_in(email, password), expires_at=int(time.time()) - 1)

    monkeypatch.setattr(sessions._auth, "sign_in", expired_sign_in)
    assert _sign_in(client).status_code == 401
    assert not client.cookies.get(COOKIE_NAME)


def test_altered_supabase_token_is_rejected_by_provider(harness):
    client, _, state, _ = harness
    state["tamper"] = True
    assert _sign_in(client).status_code == 401
    assert not client.cookies.get(COOKIE_NAME)


def test_expired_supabase_token_cannot_create_session(harness):
    client, _, state, _ = harness
    state["expired_token"] = True
    assert _sign_in(client).status_code == 401
    assert not client.cookies.get(COOKIE_NAME)


def test_invalid_signin_does_not_echo_password(harness):
    client, _, _, _ = harness
    password = "test-secret-that-must-not-be-echoed"
    response = client.post(
        "/api/synthetic-veteran/session",
        headers={"Origin": ORIGIN},
        json={"email": "synthetic@example.test", "password": password, "case": "x"},
    )
    assert response.status_code == 400
    assert password not in response.text


def test_database_unavailability_is_not_reported_as_bad_credentials(harness):
    client, sessions, _, _ = harness

    def unavailable():
        raise OSError("database unavailable")

    sessions._connect = unavailable
    assert _sign_in(client).status_code == 503


@pytest.mark.parametrize("mismatch", ["subject", "patient", "identity", "case"])
def test_unapproved_subject_or_database_binding_cannot_sign_in(harness, mismatch):
    client, _, state, binding = harness
    values = {
        "subject": binding.subject,
        "patient_id": binding.patient_id,
        "identity_id": binding.identity_id,
        "case_id": binding.case_id,
    }
    if mismatch == "subject":
        values["subject"] = uuid4()
    elif mismatch == "patient":
        values["patient_id"] = uuid4()
    elif mismatch == "identity":
        values["identity_id"] = 42
    else:
        values["case_id"] = "another-case"
    if mismatch == "subject":
        harness[1]._binding = CaseBinding(**values)
    else:
        state["binding"] = CaseBinding(**values)
    assert _sign_in(client).status_code == 401
    assert len(state["revoked"]) == 1
    assert not client.cookies.get(COOKIE_NAME)


def test_cross_session_case_scope_and_signout_are_isolated(harness):
    client, sessions, state, binding = harness
    assert _sign_in(client).status_code == 200
    first = client.cookies.get(COOKIE_NAME)
    assert _sign_in(client).status_code == 200
    second = client.cookies.get(COOKIE_NAME)
    assert first != second
    with pytest.raises(SessionDenied):
        sessions.authorize(first, "different-case")
    sessions.sign_out(first)
    with pytest.raises(SessionDenied):
        sessions.authorize(first, binding.case_id)
    assert sessions.authorize(second, binding.case_id) == binding
    assert len(state["revoked"]) == 1


def test_http_signout_does_not_end_another_browser_session(harness):
    client, _, _, _ = harness
    with TestClient(client.app, base_url=ORIGIN) as other:
        assert _sign_in(client).status_code == 200
        assert _sign_in(other).status_code == 200
        response = client.post(
            "/api/synthetic-veteran/session/sign-out", headers={"Origin": ORIGIN}
        )
        assert response.status_code == 200
        assert response.json() == {
            "authenticated": False,
            "refresh_token_revocation_verified": True,
            "access_token_rejected_by_auth": True,
        }
        assert client.get("/api/synthetic-veteran/session").status_code == 401
        assert other.get("/api/synthetic-veteran/session").status_code == 200


def test_logout_does_not_claim_access_token_revocation_without_auth_rejection(harness):
    client, _, state, _ = harness
    assert _sign_in(client).status_code == 200
    state["access_survives_logout"] = True
    response = client.post(
        "/api/synthetic-veteran/session/sign-out", headers={"Origin": ORIGIN}
    )
    assert response.status_code == 200
    assert response.json() == {
        "authenticated": False,
        "refresh_token_revocation_verified": True,
        "access_token_rejected_by_auth": False,
    }


@pytest.mark.parametrize("field", ["refresh_subject", "different_session"])
def test_refreshed_token_must_preserve_subject_and_session(harness, field):
    client, _, state, _ = harness
    assert _sign_in(client).status_code == 200
    state[field] = uuid4() if field == "refresh_subject" else True
    assert client.get("/api/synthetic-veteran/session").status_code == 401


def test_origin_and_booking_authorization_are_not_derived_from_session(harness):
    client, _, _, binding = harness
    assert (
        client.post(
            "/api/synthetic-veteran/session",
            headers={"Origin": "https://attacker.example"},
            json={"email": "synthetic@example.test", "password": "test-pass"},
        ).status_code
        == 403
    )
    assert _sign_in(client).status_code == 200
    response = client.post(
        "/internal/synthetic-primary-care/booking",
        json={
            "case_id": binding.case_id,
            "option_id": "option",
            "slot_id": str(uuid4()),
            "idempotency_key": "test",
        },
    )
    assert response.status_code == 401


def test_identity_issuer_is_session_bound_and_cannot_issue_booking(
    harness, monkeypatch
):
    client, sessions, _, binding = harness
    assert _sign_in(client).status_code == 200
    cookie = client.cookies.get(COOKIE_NAME)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = SyntheticVeteranHostIssuer(
        sessions=sessions,
        issuer="test-host",
        audience="test-service",
        subject="test-host-subject",
        private_key=key,
        public_key=key.public_key(),
    )
    guard = PostgresHostAssertionReplayGuard(lambda: None)
    seen = []
    monkeypatch.setattr(guard, "consume", lambda **kwargs: seen.append(kwargs))
    verifier = TrustedHostAuthenticator(
        issuer="test-host",
        audience="test-service",
        subject="test-host-subject",
        public_key_pem=key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode(),
        replay_guard=guard,
    )
    assertion = issuer.issue_identity_assertion(session_cookie=cookie, case_id=CASE)
    claims = jwt.decode(
        assertion,
        key.public_key(),
        algorithms=["RS256"],
        audience="test-service",
        issuer="test-host",
    )
    assert claims["scope"] == IDENTITY_SCOPE
    assert claims["case_ids"] == [binding.case_id]
    assert claims["exp"] - claims["iat"] == 60
    assert verifier.authenticate_identity(assertion).case_ids == frozenset({CASE})
    assert len(seen) == 1
    with pytest.raises(PermissionError):
        verifier.authenticate_booking(assertion)
    with pytest.raises(SessionDenied):
        issuer.issue_identity_assertion(session_cookie=cookie, case_id="wrong-case")
    with pytest.raises(SessionDenied):
        issuer.issue_identity_assertion(session_cookie="another-session", case_id=CASE)
    sessions.sign_out(cookie)
    with pytest.raises(SessionDenied):
        issuer.issue_identity_assertion(session_cookie=cookie, case_id=CASE)


def test_host_key_configuration_requires_matching_owner_only_private_key(
    harness, monkeypatch, tmp_path
):
    _, sessions, _, _ = harness
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = tmp_path / "host-private.pem"
    public_path = tmp_path / "host-public.pem"
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    monkeypatch.setenv("VAB_TRUSTED_HOST_ISSUER", "test-host")
    monkeypatch.setenv("VAB_TRUSTED_HOST_AUDIENCE", "test-service")
    monkeypatch.setenv("VAB_TRUSTED_HOST_SUBJECT", "test-host")
    monkeypatch.setenv("VAB_TRUSTED_HOST_PRIVATE_KEY_PATH", str(private_path))
    monkeypatch.setenv("VAB_TRUSTED_HOST_PUBLIC_KEY_PATH", str(public_path))
    private_path.chmod(0o644)
    with pytest.raises(PermissionError, match="owner-only"):
        build_synthetic_veteran_host_issuer(sessions)
    private_path.chmod(0o600)
    assert isinstance(
        build_synthetic_veteran_host_issuer(sessions), SyntheticVeteranHostIssuer
    )
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_path.write_bytes(
        other.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    with pytest.raises(PermissionError, match="do not match"):
        build_synthetic_veteran_host_issuer(sessions)


@pytest.mark.parametrize(
    "flag",
    [
        "VAB_ENABLE_SYNTHETIC_VETERAN_SESSIONS",
        "VAB_ENABLE_SYNTHETIC_VETERAN_CONSENT",
        "VAB_ENABLE_SYNTHETIC_SESSION_HOST_ISSUER",
    ],
)
def test_retired_browser_routes_remain_unavailable_with_old_flags(monkeypatch, flag):
    from veteran_access_bridge.app import asgi

    for name in (
        "VAB_ENABLE_SYNTHETIC_VETERAN_SESSIONS",
        "VAB_ENABLE_SYNTHETIC_VETERAN_CONSENT",
        "VAB_ENABLE_SYNTHETIC_SESSION_HOST_ISSUER",
        "VAB_ENABLE_PRIVATE_PC_BOOKING_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(flag, "true")
    app = asgi._build_app()
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/api/synthetic-veteran/session").status_code == 404
        assert client.post("/api/synthetic-veteran/session").status_code == 404
        assert client.post("/api/synthetic-veteran/session/sign-out").status_code == 404
        assert client.get("/api/synthetic-veteran/consent/offers").status_code == 404
        assert client.post("/api/synthetic-veteran/consent").status_code == 404


def test_service_role_key_is_rejected():
    key = jwt.encode({"role": "service_role"}, JWT_KEY, algorithm="HS256")
    with pytest.raises(PermissionError, match="anon key required"):
        SupabaseAuth(key=key)
