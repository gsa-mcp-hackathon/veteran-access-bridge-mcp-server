"""Private trusted-host identity evidence and Primary Care policy evaluation.

No HTTP or MCP routes live here. Hosted use requires an independently managed
RS256 issuer, protected database credentials, and explicit test-write gates.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from uuid import UUID, uuid4, uuid5

import jwt

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.pg_scheduling_sql import execute_scheduling_sql
from veteran_access_bridge.adapters.synthetic_ids import (
    VAB_SYNTHETIC_NAMESPACE,
    resolve_case_identifiers,
)
from veteran_access_bridge.services.pg_governed_va_commit import (
    POLICY_VERSION,
    SCOPE,
    VA_CHANNELS,
    VABookingRequest,
    _validate_voice_session_id,
    _verified_decision_row,
)
from veteran_access_bridge.services.private_va_booking_grant_issuer import (
    AuthenticatedService,
    EvaluatedBookingPolicy,
    PrivateVABookingGrantIssuer,
)

IDENTITY_SCOPE = "va_primary_care:verify_identity"
CASE_PROVISION_SCOPE = "va_primary_care:provision_case"
RECOVERY_SCOPE = "va_primary_care:recover"
IDENTITY_EVENT_TYPE = "SYNTHETIC_IDENTITY_VERIFICATION"
IDENTITY_METHOD = "SYNTHETIC_NAME_AND_DATE_OF_BIRTH"
IDENTITY_TTL = timedelta(minutes=5)
SLOT_FRESHNESS = timedelta(minutes=15)
HOST_ASSERTION_MAX_AGE = 300
HOST_ASSERTION_EVENT_TYPE = "TRUSTED_HOST_ASSERTION_CONSUMED"
_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr"}


@dataclass(frozen=True)
class IdentityVerificationReceipt:
    event_id: UUID
    case_id: str
    patient_id: UUID
    verified: bool
    verified_at: datetime
    expires_at: datetime
    correlation_id: str


class PostgresHostAssertionReplayGuard:
    """Consume each verified host assertion once in the isolated test database."""

    def __init__(self, connect: Callable) -> None:
        if not callable(connect):
            raise PermissionError("Protected test database connection required")
        self._connect = connect

    def consume(
        self, *, issuer: str, subject: str, token_id: str, expires_at: int | float
    ) -> None:
        key = json.dumps([issuer, subject, token_id], separators=(",", ":"))
        digest = hashlib.sha256(key.encode()).hexdigest()
        event_id = uuid5(VAB_SYNTHETIC_NAMESPACE, "trusted-host-assertion:" + digest)
        with self._connect() as conn:
            with conn.cursor() as cur:
                schema = assert_synthetic_scheduling_database(cur, conn, write=True)
                if schema != "vab_test":
                    raise PermissionError("Replay guard requires isolated test schema")
                execute_scheduling_sql(
                    cur,
                    schema,
                    "INSERT INTO vab.audit_event "
                    "(event_id,correlation_id,actor,event_type,details) "
                    "SELECT %s,%s,%s,%s,%s::jsonb "
                    "WHERE clock_timestamp() < to_timestamp(%s) "
                    "ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
                    (
                        event_id,
                        "trusted-host-assertion:" + digest,
                        subject,
                        HOST_ASSERTION_EVENT_TYPE,
                        json.dumps({"synthetic": True, "assertion_digest": digest}),
                        expires_at,
                    ),
                )
                if cur.fetchone() is None:
                    raise PermissionError("Host assertion expired or already consumed")
                cur.execute(
                    "SELECT clock_timestamp() < to_timestamp(%s)", (expires_at,)
                )
                if not cur.fetchone()[0]:
                    raise PermissionError("Host assertion expired while being consumed")


class TrustedHostAuthenticator:
    """Validate a host-issued RS256 assertion against pinned runtime config.

    The public key, issuer, audience, allowed subject, and private key that
    signs assertions belong to the protected deployment environment. This
    adapter never issues host credentials and fails closed when unconfigured.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        subject: str,
        public_key_pem: str,
        replay_guard: PostgresHostAssertionReplayGuard,
    ) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (issuer, audience, subject, public_key_pem)
        ):
            raise PermissionError("Trusted host identity configuration required")
        self._issuer = issuer
        self._audience = audience
        self._subject = subject
        self._public_key_pem = public_key_pem
        if not isinstance(replay_guard, PostgresHostAssertionReplayGuard):
            raise PermissionError("Persistent host assertion replay guard required")
        self._replay_guard = replay_guard

    @classmethod
    def from_environment(
        cls, connect: Callable | None = None
    ) -> TrustedHostAuthenticator:
        issuer = os.getenv("VAB_TRUSTED_HOST_ISSUER", "").strip()
        audience = os.getenv("VAB_TRUSTED_HOST_AUDIENCE", "").strip()
        subject = os.getenv("VAB_TRUSTED_HOST_SUBJECT", "").strip()
        from veteran_access_bridge.services.protected_host_keys import public_host_key

        if not all((issuer, audience, subject)):
            raise PermissionError("Trusted host identity configuration is incomplete")
        if not callable(connect):
            raise PermissionError("Protected replay guard connection required")
        public_key = public_host_key()
        return cls(
            issuer=issuer,
            audience=audience,
            subject=subject,
            public_key_pem=public_key,
            replay_guard=PostgresHostAssertionReplayGuard(connect),
        )

    def authenticate_booking(self, assertion: str) -> AuthenticatedService:
        return self.authenticate(assertion, required_scope=SCOPE)

    def authenticate_identity(self, assertion: str) -> AuthenticatedService:
        return self.authenticate(assertion, required_scope=IDENTITY_SCOPE)

    def authenticate_bound_booking(
        self, assertion: str, request: VABookingRequest
    ) -> tuple[AuthenticatedService, dict]:
        """Verify a host's exact booking and independently captured consent."""
        try:
            claims = jwt.decode(
                assertion,
                self._public_key_pem,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "iss",
                        "aud",
                        "sub",
                        "scope",
                        "case_ids",
                        "jti",
                        "case_id",
                        "option_id",
                        "slot_id",
                        "idempotency_key",
                        "identity_verification_id",
                        "veteran_confirmation_id",
                        "consent_response",
                        "consent_expires_at",
                    ]
                },
            )
        except jwt.PyJWTError as exc:
            raise PermissionError("Invalid or expired trusted host assertion") from exc
        confirmation = claims.get("veteran_confirmation_id")
        try:
            confirmation_id = UUID(confirmation)
        except (ValueError, TypeError, AttributeError) as exc:
            raise PermissionError("Bound Veteran consent required") from exc
        voice_session_id = claims.get("voice_session_id")
        if "voice_session_id" in claims:
            _validate_voice_session_id(voice_session_id)
        if (
            claims.get("case_ids") != [request.case_id]
            or claims.get("case_id") != request.case_id
            or claims.get("option_id") != request.option_id
            or claims.get("slot_id") != str(request.slot_id)
            or claims.get("idempotency_key") != request.idempotency_key
            or not isinstance(claims.get("identity_verification_id"), str)
            or not claims["identity_verification_id"].strip()
            or str(confirmation_id) != confirmation
            or claims.get("consent_response") != "CONFIRMED"
            or type(claims.get("consent_expires_at")) is not int
            or claims["consent_expires_at"] <= datetime.now(timezone.utc).timestamp()
            or (
                "voice_session_id" in claims
                and (
                    not isinstance(voice_session_id, str)
                    or not voice_session_id
                    or voice_session_id != voice_session_id.strip()
                    or len(voice_session_id) > 128
                )
            )
        ):
            raise PermissionError("Trusted host booking or consent binding mismatch")
        principal = self.authenticate_booking(assertion)
        return principal, claims

    def authenticate_bound_recovery(
        self, assertion: str, request: VABookingRequest
    ) -> AuthenticatedService:
        """Authorize a readback for the original booking identity only."""
        try:
            claims = jwt.decode(
                assertion,
                self._public_key_pem,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "iss",
                        "aud",
                        "sub",
                        "scope",
                        "case_ids",
                        "jti",
                        "case_id",
                        "option_id",
                        "slot_id",
                        "idempotency_key",
                    ]
                },
            )
        except jwt.PyJWTError as exc:
            raise PermissionError("Invalid or expired trusted host assertion") from exc
        if (
            claims.get("case_ids") != [request.case_id]
            or claims.get("case_id") != request.case_id
            or claims.get("option_id") != request.option_id
            or claims.get("slot_id") != str(request.slot_id)
            or claims.get("idempotency_key") != request.idempotency_key
        ):
            raise PermissionError("Trusted host recovery binding mismatch")
        voice_session_id = None
        if "voice_session_id" in claims:
            voice_session_id = _validate_voice_session_id(claims["voice_session_id"])
        principal = self.authenticate(assertion, required_scope=RECOVERY_SCOPE)
        return replace(principal, voice_session_id=voice_session_id)

    def authenticate(
        self, assertion: str, *, required_scope: str
    ) -> AuthenticatedService:
        if not isinstance(assertion, str) or not assertion.strip():
            raise PermissionError("Trusted host assertion required")
        if required_scope not in {
            SCOPE,
            IDENTITY_SCOPE,
            CASE_PROVISION_SCOPE,
            RECOVERY_SCOPE,
        }:
            raise PermissionError("Unsupported trusted host scope")
        try:
            claims = jwt.decode(
                assertion,
                self._public_key_pem,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "iss",
                        "aud",
                        "sub",
                        "scope",
                        "case_ids",
                        "jti",
                    ]
                },
                leeway=0,
            )
        except jwt.PyJWTError as exc:
            raise PermissionError("Invalid or expired trusted host assertion") from exc

        subject = claims.get("sub")
        case_ids = claims.get("case_ids")
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        token_id = claims.get("jti")
        if (
            subject != self._subject
            or claims.get("scope") != required_scope
            or not isinstance(case_ids, list)
            or not case_ids
            or any(
                not isinstance(case_id, str) or not case_id.strip()
                for case_id in case_ids
            )
            or isinstance(issued_at, bool)
            or isinstance(expires_at, bool)
            or not isinstance(issued_at, (int, float))
            or not isinstance(expires_at, (int, float))
            or not math.isfinite(issued_at)
            or not math.isfinite(expires_at)
            or expires_at <= issued_at
            or expires_at - issued_at > HOST_ASSERTION_MAX_AGE
            or not isinstance(token_id, str)
            or not token_id.strip()
            or len(token_id) > 256
        ):
            raise PermissionError("Trusted host assertion scope or subject mismatch")
        self._replay_guard.consume(
            issuer=self._issuer,
            subject=subject,
            token_id=token_id,
            expires_at=expires_at,
        )
        return AuthenticatedService(
            subject=subject,
            authenticated=True,
            scope=required_scope,
            case_ids=frozenset(case_ids),
        )


@dataclass(frozen=True)
class SyntheticCaseReceipt:
    case_id: str
    patient_id: UUID
    request_id: UUID
    audit_event_id: UUID
    created: bool


def ensure_existing_synthetic_primary_care_case(
    connect: Callable,
    authenticator: TrustedHostAuthenticator,
    *,
    assertion: str,
    case_id: str,
) -> SyntheticCaseReceipt:
    """Provision the approved case only for an already-persisted fixture patient."""
    from veteran_access_bridge.mcp.cases import (
        load_demo_encounter_case,
        load_demo_scheduling_context,
    )

    if not callable(connect):
        raise PermissionError("Protected test database connection required")
    if case_id != "DEMO-PC-5000335-001":
        raise PermissionError("Case is not approved for isolated provisioning")
    principal = authenticator.authenticate(
        assertion, required_scope=CASE_PROVISION_SCOPE
    )
    if case_id not in principal.case_ids:
        raise PermissionError("Trusted service is not scoped to this case")

    identifiers = resolve_case_identifiers(case_id)
    patient, consult = load_demo_encounter_case(case_id)
    request, _ = load_demo_scheduling_context(case_id)
    if (
        consult is not None
        or request.care_category.value != "PRIMARY_CARE"
        or request.synthetic is not True
        or patient.patient_id != identifiers.patient_external_id
    ):
        raise PermissionError("Approved Primary Care fixture required")
    event_id = uuid5(VAB_SYNTHETIC_NAMESPACE, "case-provision:" + case_id)
    correlation_id = "case-provision:" + case_id
    provenance = {
        "synthetic": True,
        "fixture_case_id": case_id,
        "fixture_request_id": identifiers.request_external_id,
    }
    details = {
        **provenance,
        "request_id": str(identifiers.request_uuid),
        "patient_id": str(identifiers.patient_uuid),
    }

    with connect() as conn:
        with conn.cursor() as cur:
            schema = assert_synthetic_scheduling_database(cur, conn, write=True)
            if schema != "vab_test":
                raise PermissionError("Case provisioning requires isolated test schema")
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT p.display_name,p.birth_date,p.synthetic,p.source_patient_id,"
                "d.source_kind FROM vab.patient p "
                "JOIN vab.data_source d ON d.source_id=p.source_id "
                "WHERE p.patient_id=%s FOR UPDATE OF p",
                (identifiers.patient_uuid,),
            )
            persisted_patient = cur.fetchone()
            if (
                persisted_patient is None
                or persisted_patient[2] is not True
                or persisted_patient[3] != patient.patient_id
                or persisted_patient[4] not in {"sandbox", "synthetic_fixture"}
                or not isinstance(persisted_patient[0], str)
                or _normalize_name(persisted_patient[0])
                != _normalize_name(patient.display_name)
                or persisted_patient[1] != date.fromisoformat(patient.birth_date)
            ):
                raise ValueError("Existing approved synthetic fixture patient required")
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT l.request_id,l.source_request_id,l.source_system,l.synthetic,"
                "r.patient_id,r.request_kind,r.requested_service,r.status,r.provenance "
                "FROM vab.scheduling_case_link l "
                "JOIN vab.appointment_request r ON r.request_id=l.request_id "
                "WHERE l.case_id=%s FOR UPDATE OF l",
                (case_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                if existing != (
                    identifiers.request_uuid,
                    identifiers.request_external_id,
                    "SYNTHETIC_MCP",
                    True,
                    identifiers.patient_uuid,
                    "PRIMARY_CARE",
                    "PRIMARY_CARE",
                    "OPEN",
                    provenance,
                ):
                    raise ValueError("Existing case does not match test-owned fixture")
                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT correlation_id,event_type,details FROM vab.audit_event "
                    "WHERE event_id=%s",
                    (event_id,),
                )
                if cur.fetchone() != (
                    correlation_id,
                    "SYNTHETIC_CASE_PROVISIONED",
                    details,
                ):
                    raise ValueError("Existing case lacks matching provenance")
                created = False
            else:
                execute_scheduling_sql(
                    cur,
                    schema,
                    "INSERT INTO vab.appointment_request "
                    "(request_id,patient_id,requested_service,request_kind,status,"
                    "provenance) VALUES (%s,%s,'PRIMARY_CARE','PRIMARY_CARE','OPEN',"
                    "%s::jsonb)",
                    (
                        identifiers.request_uuid,
                        identifiers.patient_uuid,
                        json.dumps(provenance),
                    ),
                )
                execute_scheduling_sql(
                    cur,
                    schema,
                    "INSERT INTO vab.scheduling_case_link "
                    "(case_id,request_id,source_request_id,source_system,synthetic) "
                    "VALUES (%s,%s,%s,'SYNTHETIC_MCP',true)",
                    (
                        case_id,
                        identifiers.request_uuid,
                        identifiers.request_external_id,
                    ),
                )
                execute_scheduling_sql(
                    cur,
                    schema,
                    "INSERT INTO vab.audit_event "
                    "(event_id,correlation_id,actor,event_type,details) "
                    "VALUES (%s,%s,%s,'SYNTHETIC_CASE_PROVISIONED',%s::jsonb)",
                    (event_id, correlation_id, principal.subject, json.dumps(details)),
                )
                created = True
    return SyntheticCaseReceipt(
        case_id, identifiers.patient_uuid, identifiers.request_uuid, event_id, created
    )


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = re.findall(r"[a-z0-9]+", ascii_text)
    while tokens and tokens[0] in _HONORIFICS:
        tokens.pop(0)
    return " ".join(tokens)


def _normalize_birth_date(value: str) -> date | None:
    raw = value.strip()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    for pattern in ("%m/%d/%Y", "%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    return None


def verify_and_record_synthetic_identity(
    connect: Callable,
    authenticator: TrustedHostAuthenticator,
    *,
    assertion: str,
    case_id: str,
    full_name: str,
    birth_date: str,
    correlation_id: str,
    now: datetime | None = None,
) -> IdentityVerificationReceipt:
    """Match and append a minimal identity event for an authorized synthetic case.

    Raw identity answers are used only for the comparison and are never
    persisted. The authenticated principal is the host service, not the
    Veteran, and the result is not production identity proof.
    """
    if not callable(connect):
        raise PermissionError("Protected test database connection required")
    values = (case_id, full_name, birth_date, correlation_id)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("Case, identity answers, and correlation are required")
    normalized_birth = _normalize_birth_date(birth_date)
    normalized_name = _normalize_name(full_name)
    if normalized_birth is None or not normalized_name:
        raise ValueError("Valid synthetic name and birth date are required")

    principal = authenticator.authenticate_identity(assertion)
    if case_id not in principal.case_ids:
        raise PermissionError("Trusted identity service is not scoped to this case")

    if now is not None and now.tzinfo is None:
        raise ValueError("Identity verification time must be timezone-aware")
    event_id = uuid4()
    with connect() as conn:
        with conn.cursor() as cur:
            schema = assert_synthetic_scheduling_database(cur, conn, write=True)
            if schema != "vab_test":
                raise PermissionError(
                    "Identity evidence requires the isolated test schema"
                )
            if now is None:
                execute_scheduling_sql(cur, schema, "SELECT clock_timestamp()")
                verified_at = cur.fetchone()[0]
            else:
                verified_at = now
            expires_at = verified_at + IDENTITY_TTL
            execute_scheduling_sql(
                cur,
                schema,
                "SELECT p.patient_id,p.display_name,p.birth_date,p.synthetic "
                "FROM vab.scheduling_case_link l "
                "JOIN vab.appointment_request r ON r.request_id=l.request_id "
                "JOIN vab.patient p ON p.patient_id=r.patient_id "
                "WHERE l.case_id=%s AND l.synthetic=true "
                "FOR UPDATE OF l",
                (case_id,),
            )
            patient = cur.fetchone()
            if patient is None or patient[3] is not True:
                raise ValueError("Approved synthetic scheduling case not found")
            patient_id, display_name, stored_birth, _ = patient
            matched = (
                isinstance(display_name, str)
                and _normalize_name(display_name) == normalized_name
                and stored_birth == normalized_birth
            )
            details = {
                "identity_verification_id": str(event_id),
                "case_id": case_id,
                "patient_id": str(patient_id),
                "synthetic": True,
                "verification_method": IDENTITY_METHOD,
                "verification_source": "PERSISTED_SYNTHETIC_CASE",
                "verified": matched,
                "outcome": "VERIFIED" if matched else "NO_MATCH",
                "verifying_principal": principal.subject,
                "verified_at": verified_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            }
            execute_scheduling_sql(
                cur,
                schema,
                "INSERT INTO vab.audit_event "
                "(event_id,correlation_id,actor,event_type,occurred_at,details) "
                "VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                (
                    event_id,
                    correlation_id,
                    principal.subject,
                    IDENTITY_EVENT_TYPE,
                    verified_at,
                    json.dumps(details),
                ),
            )
    return IdentityVerificationReceipt(
        event_id=event_id,
        case_id=case_id,
        patient_id=patient_id,
        verified=matched,
        verified_at=verified_at,
        expires_at=expires_at,
        correlation_id=correlation_id,
    )


def _policy_result(
    request: VABookingRequest,
    *,
    decision: str,
    identity_verification_id: str | None = None,
    identity_verification_expires_at: datetime | None = None,
    veteran_confirmation_id: UUID | None = None,
    synthetic: bool = True,
    human_review_required: bool | None = None,
    evidence: dict | None = None,
) -> EvaluatedBookingPolicy:
    evidence_payload = {
        "policy_version": POLICY_VERSION,
        "case_id": request.case_id,
        "option_id": request.option_id,
        "slot_id": str(request.slot_id),
        "decision": decision,
        "identity_verification_id": identity_verification_id,
        "identity_verification_expires_at": (
            identity_verification_expires_at.isoformat()
            if identity_verification_expires_at is not None
            else None
        ),
        "evidence": evidence or {},
    }
    reference = (
        "va-pc-policy:"
        + hashlib.sha256(
            json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    return EvaluatedBookingPolicy(
        case_id=request.case_id,
        option_id=request.option_id,
        slot_id=request.slot_id,
        identity_verification_id=identity_verification_id,
        identity_verification_expires_at=identity_verification_expires_at,
        veteran_confirmation_id=veteran_confirmation_id,
        policy_evidence_reference=reference,
        decision=decision,
        human_review_required=(
            decision == "REVIEW"
            if human_review_required is None
            else human_review_required
        ),
        synthetic=synthetic,
        care_pathway="INTERNAL_VA",
    )


class PostgresPrimaryCarePolicyEvaluator:
    """Read-only deterministic evaluator for persisted `vab_test` evidence."""

    def __init__(
        self,
        connect: Callable,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not callable(connect):
            raise PermissionError("Protected database connection required")
        self._connect = connect
        self._clock = clock

    def __call__(
        self, request: VABookingRequest, actor: AuthenticatedService
    ) -> EvaluatedBookingPolicy:
        if (
            not isinstance(request, VABookingRequest)
            or not isinstance(actor, AuthenticatedService)
            or actor.authenticated is not True
            or actor.scope != SCOPE
            or request.case_id not in actor.case_ids
        ):
            raise PermissionError("Independently authenticated case scope required")
        with self._connect() as conn:
            with conn.cursor() as cur:
                schema = assert_synthetic_scheduling_database(cur, conn, write=False)
                if schema != "vab_test":
                    raise PermissionError(
                        "Policy evaluation requires isolated test schema"
                    )
                if self._clock is None:
                    execute_scheduling_sql(cur, schema, "SELECT clock_timestamp()")
                    now = cur.fetchone()[0]
                else:
                    now = self._clock()
                if now.tzinfo is None:
                    raise ValueError("Policy evaluation time must be timezone-aware")
                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT l.request_id,r.patient_id,r.request_kind,r.status,"
                    "r.requested_service,p.synthetic "
                    "FROM vab.scheduling_case_link l "
                    "JOIN vab.appointment_request r ON r.request_id=l.request_id "
                    "JOIN vab.patient p ON p.patient_id=r.patient_id "
                    "WHERE l.case_id=%s AND l.synthetic=true",
                    (request.case_id,),
                )
                case = cur.fetchone()
                if case is None:
                    return _policy_result(request, decision="REVIEW")
                (
                    request_id,
                    patient_id,
                    request_kind,
                    request_status,
                    service,
                    synthetic,
                ) = case
                if synthetic is not True:
                    return _policy_result(request, decision="DENY", synthetic=False)
                if request_kind != "PRIMARY_CARE":
                    return _policy_result(
                        request,
                        decision="DENY",
                        evidence={"request_kind": request_kind},
                    )
                if request_status not in {"OPEN", "OPTIONS"}:
                    return _policy_result(
                        request,
                        decision="DENY",
                        evidence={"request_status": request_status},
                    )

                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT event_id,correlation_id,actor,occurred_at,details "
                    "FROM vab.audit_event WHERE event_type=%s "
                    "AND details->>'case_id'=%s AND details->>'patient_id'=%s "
                    "ORDER BY occurred_at DESC,event_id DESC LIMIT 1",
                    (IDENTITY_EVENT_TYPE, request.case_id, str(patient_id)),
                )
                identity = cur.fetchone()
                if identity is None:
                    return _policy_result(request, decision="REVIEW")
                (
                    identity_id,
                    identity_correlation,
                    identity_actor,
                    identity_at,
                    details,
                ) = identity
                identity_id = str(identity_id)
                try:
                    identity_expires = datetime.fromisoformat(details["expires_at"])
                    identity_verified_at = datetime.fromisoformat(
                        details["verified_at"]
                    )
                except (KeyError, TypeError, ValueError):
                    return _policy_result(request, decision="REVIEW")
                if (
                    details.get("identity_verification_id") != identity_id
                    or details.get("case_id") != request.case_id
                    or details.get("patient_id") != str(patient_id)
                    or details.get("synthetic") is not True
                    or details.get("verified") is not True
                    or details.get("outcome") != "VERIFIED"
                    or details.get("verification_method") != IDENTITY_METHOD
                    or details.get("verification_source") != "PERSISTED_SYNTHETIC_CASE"
                    or details.get("verifying_principal") != actor.subject
                    or identity_actor != actor.subject
                    or identity_expires <= now
                    or identity_verified_at > now
                    or identity_at != identity_verified_at
                    or identity_expires - identity_verified_at != IDENTITY_TTL
                    or not identity_correlation
                ):
                    return _policy_result(request, decision="REVIEW")

                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT d.decision_id,d.decision_status,d.option_id,"
                    "d.decision_kind,d.actor_role,d.actor_id,d.decision_order,"
                    "d.evidence,t.transition_id,t.event_type,t.actor_role,"
                    "t.actor_id,t.evidence "
                    "FROM vab.scheduling_decision d "
                    "LEFT JOIN vab.scheduling_transition t ON t.case_id=d.case_id "
                    "AND t.idempotency_key=d.idempotency_key "
                    "AND t.correlation_id=d.correlation_id "
                    "WHERE d.case_id=%s AND d.actor_role='VETERAN' "
                    "ORDER BY d.decision_order DESC LIMIT 1",
                    (request.case_id,),
                )
                decision = cur.fetchone()
                if decision is None:
                    return _policy_result(
                        request,
                        decision="REVIEW",
                        identity_verification_id=identity_id,
                        identity_verification_expires_at=identity_expires,
                    )
                if decision[3] != "VETERAN_CONFIRMED" or decision[1] != "ACCEPTED":
                    return _policy_result(
                        request,
                        decision="DENY" if decision[1] == "REJECTED" else "REVIEW",
                        identity_verification_id=identity_id,
                        identity_verification_expires_at=identity_expires,
                        evidence={"latest_veteran_decision": str(decision[0])},
                    )
                verified_decision = _verified_decision_row(
                    decision,
                    expected_kind="VETERAN_CONFIRMED",
                    expected_event="VETERAN_CONFIRMATION_RECORDED",
                    expected_role="VETERAN",
                    expected_option_id=request.option_id,
                )
                if verified_decision is None:
                    return _policy_result(
                        request,
                        decision="REVIEW",
                        identity_verification_id=identity_id,
                        identity_verification_expires_at=identity_expires,
                        evidence={"latest_veteran_decision": str(decision[0])},
                    )
                confirmation_id = verified_decision[0]

                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT s.channel,s.status,s.begins_at,s.ends_at,s.verified_at,"
                    "s.source_id,c.specialty,c.active,d.source_kind,d.provenance "
                    "FROM vab.slot s JOIN vab.clinic c ON c.clinic_id=s.clinic_id "
                    "JOIN vab.data_source d ON d.source_id=s.source_id "
                    "WHERE s.slot_id=%s",
                    (request.slot_id,),
                )
                slot = cur.fetchone()
                if slot is None:
                    return _policy_result(
                        request,
                        decision="REVIEW",
                        identity_verification_id=identity_id,
                        identity_verification_expires_at=identity_expires,
                        veteran_confirmation_id=confirmation_id,
                    )
                (
                    channel,
                    status,
                    begins_at,
                    ends_at,
                    verified_at,
                    source_id,
                    specialty,
                    active,
                    source_kind,
                    provenance,
                ) = slot
                if channel not in VA_CHANNELS or source_kind != "synthetic_fixture":
                    return _policy_result(
                        request,
                        decision="DENY",
                        identity_verification_id=identity_id,
                        identity_verification_expires_at=identity_expires,
                        veteran_confirmation_id=confirmation_id,
                        evidence={"channel": channel, "source_kind": source_kind},
                    )
                bindings = (
                    provenance.get("slot_bindings")
                    if isinstance(provenance, dict)
                    else None
                )
                binding = (
                    bindings.get(str(request.slot_id))
                    if isinstance(bindings, dict)
                    else None
                )
                if (
                    status != "AVAILABLE"
                    or active is not True
                    or not isinstance(specialty, str)
                    or specialty.strip().upper() != str(service).strip().upper()
                    or not isinstance(binding, dict)
                    or binding.get("case_id") != request.case_id
                    or binding.get("option_id") != request.option_id
                ):
                    return _policy_result(
                        request,
                        decision="DENY",
                        identity_verification_id=identity_id,
                        identity_verification_expires_at=identity_expires,
                        veteran_confirmation_id=confirmation_id,
                        evidence={"source_id": source_id},
                    )
                decision_evidence = decision[7]
                if (
                    not isinstance(decision_evidence, dict)
                    or decision_evidence.get("service_evidence_reference") != source_id
                ):
                    return _policy_result(
                        request,
                        decision="REVIEW",
                        identity_verification_id=identity_id,
                        identity_verification_expires_at=identity_expires,
                        veteran_confirmation_id=confirmation_id,
                        evidence={"source_id": source_id},
                    )
                if (
                    verified_at is None
                    or verified_at > now
                    or verified_at < now - SLOT_FRESHNESS
                    or begins_at <= now
                    or ends_at <= begins_at
                ):
                    return _policy_result(
                        request,
                        decision="REVIEW",
                        identity_verification_id=identity_id,
                        identity_verification_expires_at=identity_expires,
                        veteran_confirmation_id=confirmation_id,
                        evidence={"source_id": source_id},
                    )

                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT EXISTS (SELECT 1 FROM vab.appointment "
                    "WHERE idempotency_key=%s OR "
                    "(request_id=%s AND status='BOOKED_SIMULATED') OR "
                    "(slot_id=%s AND status='BOOKED_SIMULATED'))",
                    (request.idempotency_key, request_id, request.slot_id),
                )
                if cur.fetchone()[0]:
                    return _policy_result(
                        request,
                        decision="DENY",
                        identity_verification_id=identity_id,
                        identity_verification_expires_at=identity_expires,
                        veteran_confirmation_id=confirmation_id,
                        evidence={"existing_booking": True},
                    )

                evidence = {
                    "request_id": str(request_id),
                    "patient_id": str(patient_id),
                    "identity_verification_id": identity_id,
                    "identity_correlation": identity_correlation,
                    "veteran_confirmation_id": str(confirmation_id),
                    "veteran_decision_order": verified_decision[1],
                    "source_id": source_id,
                    "channel": channel,
                    "verified_at": verified_at.isoformat(),
                    "slot_id": str(request.slot_id),
                    "actor": actor.subject,
                }
                return _policy_result(
                    request,
                    decision="ALLOW",
                    identity_verification_id=identity_id,
                    identity_verification_expires_at=identity_expires,
                    veteran_confirmation_id=confirmation_id,
                    human_review_required=False,
                    evidence=evidence,
                )


def build_trusted_primary_care_coordinator(services):
    """Wire real configured adapters to the existing private coordinator.

    Construction fails before use if host identity or signing configuration is
    missing. No HTTP/MCP registration or database access occurs here.
    """
    from veteran_access_bridge.services.signed_scheduling_lifecycle import (
        TrustedPrimaryCareBookingCoordinator,
    )

    authenticator = TrustedHostAuthenticator.from_environment(
        getattr(services, "connect", None)
    )
    signing_secret = os.getenv("VAB_PRIVATE_VA_BOOKING_SIGNING_SECRET", "")
    if len(signing_secret.encode()) < 32:
        raise PermissionError("Protected internal VA booking grant key is required")
    if services._va_booking_secret() != signing_secret:
        raise PermissionError(
            "Grant issuer and booking verifier must use the same protected key"
        )
    issuer = PrivateVABookingGrantIssuer(
        signing_secret=signing_secret,
        authenticate_service=authenticator.authenticate_booking,
        evaluate_booking=PostgresPrimaryCarePolicyEvaluator(services.connect),
    )
    return TrustedPrimaryCareBookingCoordinator(
        services=services,
        grant_issuer=issuer,
    )
