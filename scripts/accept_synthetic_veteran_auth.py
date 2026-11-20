"""Opt-in real Supabase Auth acceptance for the synthetic session boundary.

Run only against the dedicated synthetic Supabase Auth account and vab_test.
Credentials are prompted without echo unless supplied through a restricted
secret environment. This runner never invokes a booking or consent operation.
"""

from __future__ import annotations

import getpass
import os
import sys
import time
from dataclasses import replace
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    SUPABASE_PROJECT_REF,
)
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling_readonly,
)
from veteran_access_bridge.app.synthetic_veteran_session import (
    COOKIE_NAME,
    CaseBinding,
    SessionDenied,
    SessionUnavailable,
    SyntheticVeteranSessions,
    _origin,
    build_synthetic_veteran_sessions,
    case_binding_exists,
    create_synthetic_veteran_session_router,
)

EXPECTED_SUBJECT = UUID("c9de2570-9ebc-45dd-9447-e0a9bdae9660")
EXPECTED_PATIENT = UUID("fe0defc2-1ead-0eb7-2156-7eb36606e742")
EXPECTED_IDENTITY_ID = 29
EXPECTED_CASE = "VAB-DEMO-20261113-CASE-031"


class AcceptanceBlocked(RuntimeError):
    """A required opt-in, config value, or interactive credential is missing."""


def _resolve_origin(environ: dict[str, str]) -> str:
    configured = environ.get("VAB_SYNTHETIC_SESSION_ORIGIN", "").strip()
    if configured and "<" not in configured and ">" not in configured:
        return _checked_origin(configured)
    name = environ.get("CODESPACE_NAME", "").strip()
    domain = environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "").strip()
    if not name or not domain:
        raise AcceptanceBlocked(
            "Set VAB_SYNTHETIC_SESSION_ORIGIN to an exact HTTPS origin"
        )
    return _checked_origin(f"https://{name}-4317.{domain}")


def _checked_origin(value: str) -> str:
    if any(character.isspace() for character in value):
        raise PermissionError("An exact HTTPS browser origin is required")
    parsed = urlsplit(value)
    if parsed.hostname is None or "<" in parsed.hostname or ">" in parsed.hostname:
        raise PermissionError("An exact HTTPS browser origin is required")
    return _origin(value)


def _binding_from_environment(environ: dict[str, str]) -> CaseBinding:
    try:
        binding = CaseBinding(
            subject=UUID(environ["VAB_SYNTHETIC_AUTH_SUBJECT"]),
            patient_id=UUID(environ["VAB_SYNTHETIC_SESSION_PATIENT_ID"]),
            identity_id=int(environ["VAB_SYNTHETIC_SESSION_IDENTITY_ID"]),
            case_id=environ["VAB_SYNTHETIC_SESSION_CASE_ID"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AcceptanceBlocked("Approved session binding is incomplete") from exc
    if binding != CaseBinding(
        EXPECTED_SUBJECT,
        EXPECTED_PATIENT,
        EXPECTED_IDENTITY_ID,
        EXPECTED_CASE,
    ):
        raise AcceptanceBlocked("Configured session binding differs from approval")
    return binding


def _validate_opt_ins(environ: dict[str, str]) -> None:
    if environ.get("VAB_RUN_SYNTHETIC_AUTH_ACCEPTANCE") != "true":
        raise AcceptanceBlocked("Explicit acceptance opt-in is required")
    if environ.get("VAB_ENABLE_SYNTHETIC_VETERAN_SESSIONS") != "true":
        raise AcceptanceBlocked("Synthetic session opt-in is required")
    if environ.get("VAB_SUPABASE_PROJECT_REF") != SUPABASE_PROJECT_REF:
        raise AcceptanceBlocked("Approved Supabase project setting is required")
    if environ.get("VAB_SUPABASE_TEST_MODE") != "true":
        raise AcceptanceBlocked("Supabase test mode is required")
    if environ.get("VAB_ENABLE_SUPABASE_TEST_WRITES") == "true":
        raise AcceptanceBlocked("Database write opt-in must remain disabled")
    if environ.get("VAB_ENABLE_SUPABASE_SCHEDULING_WRITES") == "true":
        raise AcceptanceBlocked("Operational database writes must remain disabled")
    if environ.get("VAB_ENABLE_PRIVATE_PC_BOOKING_ENDPOINT") == "true":
        raise AcceptanceBlocked("Booking endpoint must remain disabled")
    if environ.get("VAB_ENABLE_SYNTHETIC_SESSION_HOST_ISSUER") == "true":
        raise AcceptanceBlocked("Host issuer is outside this acceptance scope")
    for name in (
        "VAB_SUPABASE_TEST_DATABASE_URL",
        "VAB_SUPABASE_PUBLISHABLE_KEY",
    ):
        if not environ.get(name, "").strip():
            raise AcceptanceBlocked(f"{name} is required")


def _credentials(environ: dict[str, str]) -> tuple[str, str]:
    email = environ.get("VAB_SYNTHETIC_TEST_EMAIL", "").strip()
    password = environ.get("VAB_SYNTHETIC_TEST_PASSWORD", "")
    if not email or not password:
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise AcceptanceBlocked(
                "Run in an interactive terminal or configure restricted "
                "VAB_SYNTHETIC_TEST_EMAIL and VAB_SYNTHETIC_TEST_PASSWORD secrets"
            )
        if not email:
            email = getpass.getpass("Synthetic account email (input hidden): ").strip()
        if not password:
            password = getpass.getpass("Synthetic account password (input hidden): ")
    if not email or not password:
        raise AcceptanceBlocked("Synthetic account credentials are required")
    return email, password


def _record(
    outcomes: list[tuple[str, str, str]], name: str, status: str, detail: str
) -> None:
    outcomes.append((name, status, detail))


def _sign_in(client: TestClient, email: str, password: str, origin: str):
    return client.post(
        "/api/synthetic-veteran/session",
        headers={"Origin": origin},
        json={"email": email, "password": password},
    )


def _revoke_trial_session(
    sessions: SyntheticVeteranSessions,
    session,
    outcomes: list[tuple[str, str, str]],
    label: str,
) -> None:
    try:
        access_rejected = sessions._auth.revoke(session.tokens)
    except (SessionDenied, SessionUnavailable, OSError):
        _record(outcomes, label, "WARN", "Supabase cleanup/revocation unverified")
        return
    _record(
        outcomes,
        label,
        "PASS" if access_rejected else "WARN",
        "refresh revoked; old access token rejected"
        if access_rejected
        else "refresh revoked; old access token remains accepted",
    )


def _run_live(
    sessions: SyntheticVeteranSessions,
    binding: CaseBinding,
    origin: str,
    email: str,
    password: str,
) -> list[tuple[str, str, str]]:
    outcomes: list[tuple[str, str, str]] = []
    app = FastAPI()
    app.include_router(create_synthetic_veteran_session_router(sessions, origin=origin))
    with TestClient(app, base_url=origin, follow_redirects=False) as client:
        anonymous = client.get("/api/synthetic-veteran/session")
        _record(
            outcomes,
            "Unauthenticated session access",
            "PASS" if anonymous.status_code == 401 else "FAIL",
            f"HTTP {anonymous.status_code}, expected 401",
        )

        response = _sign_in(client, email, password, origin)
        if response.status_code != 200:
            _record(
                outcomes,
                "Real Supabase Auth sign-in",
                "FAIL",
                f"Backend returned HTTP {response.status_code}",
            )
            return outcomes

        cookie = client.cookies.get(COOKIE_NAME)
        session = sessions._sessions.get(cookie or "")
        subject_matches = (
            session is not None and session.tokens.subject == binding.subject
        )
        _record(
            outcomes,
            "Real Auth subject and backend session",
            "PASS" if subject_matches else "FAIL",
            "Auth /user subject matches approved subject"
            if subject_matches
            else "Auth subject did not match approved subject",
        )
        if not subject_matches or session is None:
            return outcomes

        current = client.get("/api/synthetic-veteran/session")
        _record(
            outcomes,
            "Real Auth session and approved case binding",
            "PASS"
            if current.status_code == 200
            and current.json().get("case_id") == binding.case_id
            else "FAIL",
            f"Backend returned HTTP {current.status_code}",
        )

        wrong_case = client.get(
            "/api/synthetic-veteran/session",
            params={"case_id": "VAB-DEMO-UNAUTHORIZED"},
        )
        wrong_patient = client.get(
            "/api/synthetic-veteran/session",
            params={"patient_id": str(uuid4())},
        )
        _record(
            outcomes,
            "Cross-case access denial",
            "PASS" if wrong_case.status_code == 401 else "FAIL",
            f"Backend returned HTTP {wrong_case.status_code}, expected 401",
        )
        _record(
            outcomes,
            "Cross-patient access denial",
            "PASS" if wrong_patient.status_code == 401 else "FAIL",
            f"Backend returned HTTP {wrong_patient.status_code}, expected 401",
        )

        wrong_subject_session = sessions._sessions.get(cookie)
        if wrong_subject_session is None:
            _record(outcomes, "Wrong-subject access denial", "FAIL", "Session missing")
        else:
            sessions._binding = replace(binding, subject=uuid4())
            wrong_subject = client.get("/api/synthetic-veteran/session")
            sessions._binding = binding
            _record(
                outcomes,
                "Wrong-subject access denial",
                "PASS" if wrong_subject.status_code == 401 else "FAIL",
                f"Live Auth session with induced mismatched server binding returned "
                f"HTTP {wrong_subject.status_code}, expected 401; "
                "not a second Auth subject",
            )
            _revoke_trial_session(
                sessions,
                wrong_subject_session,
                outcomes,
                "Wrong-subject trial cleanup",
            )

        expiration_login = _sign_in(client, email, password, origin)
        if expiration_login.status_code == 200:
            expiration_cookie = client.cookies.get(COOKIE_NAME)
            expiring = sessions._sessions.get(expiration_cookie or "")
            if expiring is not None:
                expiring.expires_at = time.monotonic() - 1
                expired = client.get("/api/synthetic-veteran/session")
                _record(
                    outcomes,
                    "Expired local session denial",
                    "PASS" if expired.status_code == 401 else "FAIL",
                    f"Artificially expired local session returned HTTP "
                    f"{expired.status_code}, expected 401; not natural Auth expiry",
                )
                _revoke_trial_session(
                    sessions, expiring, outcomes, "Expired-session trial cleanup"
                )
            else:
                _record(
                    outcomes, "Expired local session denial", "FAIL", "Session missing"
                )
        else:
            _record(
                outcomes,
                "Expired local session denial",
                "FAIL",
                f"Could not create trial session (HTTP {expiration_login.status_code})",
            )

        logout_login = _sign_in(client, email, password, origin)
        if logout_login.status_code != 200:
            _record(
                outcomes,
                "Logout and application session invalidation",
                "FAIL",
                f"Could not create logout session (HTTP {logout_login.status_code})",
            )
            return outcomes
        logout = client.post(
            "/api/synthetic-veteran/session/sign-out",
            headers={"Origin": origin},
        )
        try:
            logout_body = logout.json()
        except ValueError:
            logout_body = {}
        after_logout = client.get("/api/synthetic-veteran/session")
        logout_ok = logout.status_code == 200 and after_logout.status_code == 401
        _record(
            outcomes,
            "Logout invalidates backend session",
            "PASS" if logout_ok else "FAIL",
            f"logout HTTP {logout.status_code}; following session check "
            f"HTTP {after_logout.status_code}",
        )
        refresh_revoked = logout_body.get("refresh_token_revocation_verified") is True
        _record(
            outcomes,
            "Supabase refresh-token revocation",
            "PASS" if refresh_revoked else "FAIL",
            "Auth rejected the refresh token after logout"
            if refresh_revoked
            else "Refresh-token revocation was not confirmed",
        )
        access_rejected = logout_body.get("access_token_rejected_by_auth") is True
        _record(
            outcomes,
            "Supabase old access-token rejection",
            "PASS" if access_rejected else "WARN",
            "Auth /user rejected the old access token"
            if access_rejected
            else "Auth /user still accepted the old access token; strict revocation "
            "is not established",
        )
    return outcomes


def _print_report(outcomes: list[tuple[str, str, str]]) -> None:
    print("Synthetic Veteran Auth acceptance")
    print(
        "Scope: real Supabase Auth + HTTPS ASGI routes; read-only vab_test; "
        "no booking or consent writes"
    )
    for name, status, detail in outcomes:
        print(f"{status}: {name} — {detail}")


def main() -> int:
    outcomes: list[tuple[str, str, str]] = []
    try:
        _validate_opt_ins(os.environ)
        binding = _binding_from_environment(os.environ)
        origin = _resolve_origin(os.environ)
        os.environ["VAB_SYNTHETIC_SESSION_ORIGIN"] = origin
        sessions, configured_origin = build_synthetic_veteran_sessions()
        if configured_origin != origin:
            raise AcceptanceBlocked("Session origin configuration mismatch")
        if not case_binding_exists(
            connect_private_supabase_test_scheduling_readonly, binding
        ):
            raise AcceptanceBlocked("Approved patient/case identity link is absent")
    except (AcceptanceBlocked, PermissionError, ValueError, SessionUnavailable) as exc:
        print(f"BLOCKED: {type(exc).__name__}: {exc}")
        return 2
    except Exception as exc:
        print(f"FAIL: setup or read-only case check failed ({type(exc).__name__})")
        return 1

    _record(
        outcomes,
        "Restricted read-only vab_test binding",
        "PASS",
        "approved synthetic patient, identity row, and open Primary Care case match",
    )
    try:
        email, password = _credentials(os.environ)
    except AcceptanceBlocked as exc:
        _record(outcomes, "Real Supabase Auth", "BLOCKED", str(exc))
        _print_report(outcomes)
        return 2

    try:
        outcomes.extend(_run_live(sessions, binding, origin, email, password))
    except Exception as exc:
        _record(
            outcomes,
            "Real Supabase Auth integration",
            "FAIL",
            f"Unexpected failure ({type(exc).__name__}); details suppressed",
        )
    finally:
        for cookie in list(sessions._sessions):
            try:
                revoked = sessions.sign_out(cookie)
                if revoked is True:
                    cleanup_status = "PASS"
                    cleanup_detail = "refresh and access-token revocation verified"
                elif revoked is False:
                    cleanup_status = "WARN"
                    cleanup_detail = (
                        "refresh token revoked; old access token remains accepted"
                    )
                else:
                    cleanup_status = "WARN"
                    cleanup_detail = "Auth cleanup was not confirmed"
                _record(
                    outcomes,
                    "Unfinished Auth session cleanup",
                    cleanup_status,
                    cleanup_detail,
                )
            except (SessionDenied, SessionUnavailable, OSError) as exc:
                _record(
                    outcomes,
                    "Unfinished Auth session cleanup",
                    "WARN",
                    f"Auth cleanup unverified ({type(exc).__name__})",
                )
        email = ""
        password = ""

    _print_report(outcomes)
    if any(status in {"FAIL", "WARN"} for _, status, _ in outcomes):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
