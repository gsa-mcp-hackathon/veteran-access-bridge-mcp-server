"""Opt-in, server-side Supabase Auth sessions for one approved synthetic case."""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    SUPABASE_PROJECT_REF,
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling_readonly,
)

logger = logging.getLogger(__name__)
COOKIE_NAME = "__Host-vab-synthetic-session"
SESSION_SECONDS = 300
MAX_SESSIONS = 100
AUTH_URL = f"https://{SUPABASE_PROJECT_REF}.supabase.co/auth/v1"


class SessionDenied(PermissionError):
    """The supplied credentials or session cannot authorize this case."""


class SessionUnavailable(RuntimeError):
    """A required authentication or authorization dependency is unavailable."""


@dataclass(frozen=True)
class CaseBinding:
    subject: UUID
    patient_id: UUID
    identity_id: int
    case_id: str


@dataclass(frozen=True)
class AuthTokens:
    subject: UUID
    session_id: UUID
    expires_at: int
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)


def _publishable_key(value: str) -> str:
    if value.startswith("sb_publishable_") and len(value) > len("sb_publishable_"):
        return value
    try:
        claims = jwt.decode(value, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise PermissionError(
            "Supabase publishable or legacy anon key required"
        ) from exc
    if claims.get("role") != "anon":
        raise PermissionError("Supabase publishable or legacy anon key required")
    return value


def _origin(value: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path
        or parts.query
        or parts.fragment
    ):
        raise PermissionError("An exact HTTPS browser origin is required")
    return value


class SupabaseAuth:
    """Authenticate and refresh against the fixed, TLS-verified test project."""

    def __init__(self, *, key: str, client: httpx.Client | None = None) -> None:
        self._key = _publishable_key(key)
        self._client = client or httpx.Client(timeout=8, follow_redirects=False)

    def _request(
        self, method: str, path: str, *, payload: dict | None = None, token: str = ""
    ) -> dict:
        headers = {"apikey": self._key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = self._client.request(
                method, AUTH_URL + path, headers=headers, json=payload
            )
        except httpx.RequestError as exc:
            raise SessionUnavailable("Supabase Auth unavailable") from exc
        if response.status_code in {400, 401, 403}:
            raise SessionDenied("Supabase authentication rejected")
        if response.status_code >= 300:
            raise SessionUnavailable("Supabase Auth unavailable")
        if response.status_code == 204:
            return {}
        try:
            body = response.json()
        except ValueError as exc:
            raise SessionUnavailable("Invalid Supabase Auth response") from exc
        if not isinstance(body, dict):
            raise SessionUnavailable("Invalid Supabase Auth response")
        return body

    def _validate_tokens(self, body: dict) -> AuthTokens:
        access = body.get("access_token")
        refresh = body.get("refresh_token")
        if (
            not isinstance(access, str)
            or not access
            or not isinstance(refresh, str)
            or not refresh
        ):
            raise SessionUnavailable("Incomplete Supabase Auth response")
        user = self._request("GET", "/user", token=access)
        try:
            # /user validates the token; the claims are inspected only afterward.
            claims = jwt.decode(access, options={"verify_signature": False})
            subject = UUID(claims["sub"])
            session_id = UUID(claims["session_id"])
            user_id = UUID(user["id"])
            expires_at = claims["exp"]
            audience = claims["aud"]
            banned_until = user.get("banned_until")
            if banned_until:
                banned_at = datetime.fromisoformat(banned_until.replace("Z", "+00:00"))
                if banned_at.tzinfo is None or banned_at > datetime.now(timezone.utc):
                    raise SessionDenied("Supabase account unavailable")
        except (jwt.PyJWTError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise SessionDenied("Invalid Supabase session") from exc
        if (
            subject != user_id
            or claims.get("iss") != AUTH_URL
            or audience != "authenticated"
            or claims.get("role") != "authenticated"
            or type(expires_at) is not int
            or expires_at <= time.time()
            or user.get("is_anonymous") is True
            or user.get("deleted_at")
        ):
            raise SessionDenied("Invalid Supabase session")
        return AuthTokens(subject, session_id, expires_at, access, refresh)

    def sign_in(self, email: str, password: str) -> AuthTokens:
        return self._validate_tokens(
            self._request(
                "POST",
                "/token?grant_type=password",
                payload={"email": email, "password": password},
            )
        )

    def refresh(self, tokens: AuthTokens) -> AuthTokens:
        refreshed = self._validate_tokens(
            self._request(
                "POST",
                "/token?grant_type=refresh_token",
                payload={"refresh_token": tokens.refresh_token},
            )
        )
        if (
            refreshed.subject != tokens.subject
            or refreshed.session_id != tokens.session_id
        ):
            raise SessionDenied("Supabase session changed")
        return refreshed

    def revoke(self, tokens: AuthTokens) -> bool:
        self._request("POST", "/logout?scope=local", token=tokens.access_token)
        try:
            response = self._request(
                "POST",
                "/token?grant_type=refresh_token",
                payload={"refresh_token": tokens.refresh_token},
            )
        except SessionDenied:
            pass
        else:
            access_token = response.get("access_token")
            if isinstance(access_token, str) and access_token:
                self._request("POST", "/logout?scope=local", token=access_token)
            raise SessionUnavailable(
                "Supabase refresh-token revocation was not confirmed"
            )
        try:
            self._request("GET", "/user", token=tokens.access_token)
        except SessionDenied:
            return True
        return False


def case_binding_exists(connect: Callable, binding: CaseBinding) -> bool:
    """Read the exact server-configured patient identity and case, never raw IDs."""
    with connect() as conn:
        with conn.cursor() as cur:
            if (
                assert_synthetic_scheduling_database(cur, conn, write=False)
                != "vab_test"
            ):
                raise PermissionError("Isolated test schema required")
            cur.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM vab_test.patient_identity i "
                "JOIN vab_test.patient p ON p.patient_id=i.patient_id "
                "JOIN vab_test.appointment_request r ON r.patient_id=p.patient_id "
                "JOIN vab_test.scheduling_case_link l ON l.request_id=r.request_id "
                "WHERE i.identity_id=%s AND p.patient_id=%s AND l.case_id=%s "
                "AND p.synthetic=true AND l.synthetic=true "
                "AND r.request_kind='PRIMARY_CARE' "
                "AND r.requested_service='PRIMARY_CARE' "
                "AND r.status IN ('OPEN','OPTIONS'))",
                (binding.identity_id, binding.patient_id, binding.case_id),
            )
            return cur.fetchone()[0] is True


@dataclass
class _Session:
    tokens: AuthTokens
    expires_at: float
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class SyntheticVeteranSessions:
    """Process-local sessions; no Supabase token is returned to the browser."""

    def __init__(
        self, *, auth: SupabaseAuth, binding: CaseBinding, connect: Callable
    ) -> None:
        self._auth = auth
        self._binding = binding
        self._connect = connect
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def _check_binding(self, subject: UUID) -> None:
        if subject != self._binding.subject:
            raise SessionDenied("Subject is not approved")
        try:
            import psycopg
        except ImportError:
            database_errors = (ImportError,)
        else:
            database_errors = (psycopg.Error,)
        try:
            exists = case_binding_exists(self._connect, self._binding)
        except (PermissionError, ValueError, OSError, *database_errors) as exc:
            logger.error("Synthetic case binding unavailable: %s", type(exc).__name__)
            raise SessionUnavailable("Synthetic case binding unavailable") from exc
        if not exists:
            raise SessionDenied("Synthetic case binding is not valid")

    def sign_in(self, email: str, password: str) -> str:
        tokens = self._auth.sign_in(email, password)
        try:
            self._check_binding(tokens.subject)
            session_id = secrets.token_urlsafe(32)
            with self._lock:
                now = time.monotonic()
                remaining = min(SESSION_SECONDS, tokens.expires_at - time.time())
                if remaining <= 0:
                    raise SessionDenied("Synthetic session expired")
                self._sessions = {
                    key: session
                    for key, session in self._sessions.items()
                    if session.expires_at > now
                }
                if len(self._sessions) >= MAX_SESSIONS:
                    raise SessionUnavailable("Synthetic session capacity reached")
                self._sessions[session_id] = _Session(tokens, now + remaining)
            return session_id
        except (SessionDenied, SessionUnavailable, PermissionError, ValueError):
            self._auth.revoke(tokens)
            raise

    def authorize(
        self,
        cookie: str | None,
        case_id: str | None = None,
        patient_id: UUID | None = None,
    ) -> CaseBinding:
        if not cookie:
            raise SessionDenied("Synthetic session required")
        with self._lock:
            session = self._sessions.get(cookie)
        if session is None:
            raise SessionDenied("Synthetic session required")
        with session.lock:
            with self._lock:
                if self._sessions.get(cookie) is not session:
                    raise SessionDenied("Synthetic session ended")
                if session.expires_at <= time.monotonic():
                    del self._sessions[cookie]
                    raise SessionDenied("Synthetic session expired")
            if case_id is not None and case_id != self._binding.case_id:
                raise SessionDenied("Synthetic case not authorized")
            if patient_id is not None and patient_id != self._binding.patient_id:
                raise SessionDenied("Synthetic patient not authorized")
            try:
                session.tokens = self._auth.refresh(session.tokens)
                self._check_binding(session.tokens.subject)
                if (
                    session.expires_at <= time.monotonic()
                    or session.tokens.expires_at <= time.time()
                ):
                    raise SessionDenied("Synthetic session expired")
            except (SessionDenied, SessionUnavailable, PermissionError, ValueError):
                with self._lock:
                    self._sessions.pop(cookie, None)
                raise
            return self._binding

    def sign_out(self, cookie: str | None) -> bool | None:
        if not cookie:
            return None
        with self._lock:
            session = self._sessions.get(cookie)
        if session is None:
            return None
        with session.lock:
            with self._lock:
                if self._sessions.pop(cookie, None) is not session:
                    return None
            return self._auth.revoke(session.tokens)


def build_synthetic_veteran_sessions() -> tuple[SyntheticVeteranSessions, str]:
    try:
        origin = _origin(os.environ["VAB_SYNTHETIC_SESSION_ORIGIN"])
        subject = UUID(os.environ["VAB_SYNTHETIC_AUTH_SUBJECT"])
        patient_id = UUID(os.environ["VAB_SYNTHETIC_SESSION_PATIENT_ID"])
        identity_id = int(os.environ["VAB_SYNTHETIC_SESSION_IDENTITY_ID"])
        case_id = os.environ["VAB_SYNTHETIC_SESSION_CASE_ID"]
        key = os.environ["VAB_SUPABASE_PUBLISHABLE_KEY"]
        if identity_id <= 0 or not case_id.strip() or case_id != case_id.strip():
            raise ValueError("Invalid synthetic case binding")
        if os.getenv("VAB_SUPABASE_TEST_MODE") != "true":
            raise ValueError("Synthetic test mode required")
    except (KeyError, ValueError) as exc:
        raise PermissionError("Synthetic session configuration is incomplete") from exc
    binding = CaseBinding(subject, patient_id, identity_id, case_id)
    return (
        SyntheticVeteranSessions(
            auth=SupabaseAuth(key=key),
            binding=binding,
            connect=connect_private_supabase_test_scheduling_readonly,
        ),
        origin,
    )


class SignInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024, repr=False)


def create_synthetic_veteran_session_router(
    sessions: SyntheticVeteranSessions, *, origin: str
) -> APIRouter:
    router = APIRouter(prefix="/api/synthetic-veteran/session")
    origin = _origin(origin)

    def require_origin(request: Request) -> None:
        if request.headers.get("origin") != origin:
            raise HTTPException(
                status_code=403,
                detail="Invalid request origin",
                headers={"Cache-Control": "no-store"},
            )

    def failure(exc: Exception) -> HTTPException:
        if isinstance(exc, SessionUnavailable):
            return HTTPException(
                status_code=503,
                detail="Session service unavailable",
                headers={"Cache-Control": "no-store"},
            )
        return HTTPException(
            status_code=401,
            detail="Synthetic session not authorized",
            headers={"Cache-Control": "no-store"},
        )

    @router.post("", include_in_schema=False)
    async def sign_in(request: Request, response: Response):
        require_origin(request)
        if (
            request.headers.get("content-type", "").split(";", 1)[0]
            != "application/json"
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid sign-in request",
                headers={"Cache-Control": "no-store"},
            )
        chunks = bytearray()
        async for chunk in request.stream():
            if len(chunks) + len(chunk) > 8192:
                raise HTTPException(
                    status_code=413,
                    detail="Sign-in request too large",
                    headers={"Cache-Control": "no-store"},
                )
            chunks.extend(chunk)
        try:
            body = SignInRequest.model_validate(json.loads(chunks))
        except (json.JSONDecodeError, UnicodeDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid sign-in request",
                headers={"Cache-Control": "no-store"},
            ) from exc
        try:
            cookie = await run_in_threadpool(
                sessions.sign_in, body.email, body.password
            )
        except (SessionDenied, SessionUnavailable, PermissionError, ValueError) as exc:
            raise failure(exc) from exc
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie(
            COOKIE_NAME,
            cookie,
            max_age=SESSION_SECONDS,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return {"authenticated": True, "synthetic": True}

    @router.get("", include_in_schema=False)
    def current(
        request: Request,
        response: Response,
        case_id: str | None = Query(default=None, min_length=1, max_length=128),
        patient_id: UUID | None = None,
    ):
        try:
            binding = sessions.authorize(
                request.cookies.get(COOKIE_NAME), case_id, patient_id
            )
        except (SessionDenied, SessionUnavailable, PermissionError, ValueError) as exc:
            raise failure(exc) from exc
        response.headers["Cache-Control"] = "no-store"
        return {"authenticated": True, "synthetic": True, "case_id": binding.case_id}

    @router.post("/sign-out", include_in_schema=False)
    def sign_out(request: Request, response: Response):
        require_origin(request)
        try:
            access_token_rejected = sessions.sign_out(request.cookies.get(COOKIE_NAME))
        except (SessionDenied, SessionUnavailable) as exc:
            raise failure(exc) from exc
        response.headers["Cache-Control"] = "no-store"
        response.delete_cookie(
            COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict"
        )
        return {
            "authenticated": False,
            "refresh_token_revocation_verified": access_token_rejected is not None,
            "access_token_rejected_by_auth": access_token_rejected is True,
        }

    return router
