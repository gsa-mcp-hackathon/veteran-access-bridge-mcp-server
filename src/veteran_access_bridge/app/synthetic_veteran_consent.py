"""Disabled-by-default, session-bound synthetic Veteran consent capture.

Never accept a browser-supplied actor, evidence source, signing token, or case binding.
No booking or slot-verification data is created by this boundary.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
    connect_private_supabase_test_scheduling_readonly,
)
from veteran_access_bridge.app.synthetic_veteran_session import (
    COOKIE_NAME,
    CaseBinding,
    SessionDenied,
    SessionUnavailable,
    SyntheticVeteranSessions,
)
from veteran_access_bridge.services.pg_signed_decisions import AUDIENCE, ISSUER
from veteran_access_bridge.services.supabase_scheduling_gateway import (
    PrivateSyntheticSchedulingGateway,
)
from veteran_access_bridge.services.trusted_primary_care import (
    IDENTITY_EVENT_TYPE,
    IDENTITY_METHOD,
    IDENTITY_TTL,
    IdentityVerificationReceipt,
)

MAX_SLOT_AGE = timedelta(minutes=15)


class ConsentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=128)
    option_id: str = Field(min_length=1, max_length=128)
    slot_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    confirmed: bool


class ConsentNotReady(PermissionError):
    """Identity or chosen appointment has not been independently verified."""


def verified_consent_evidence(
    connect: Callable,
    *,
    binding: CaseBinding | IdentityVerificationReceipt,
    option_id: str,
    slot_id: UUID,
    host_subject: str,
    voice_session_id: str | None = None,
    identity_verification_id: str | None = None,
) -> str:
    """Read existing identity and slot evidence; never manufacture verification."""
    with connect() as conn:
        with conn.cursor() as cur:
            if (
                assert_synthetic_scheduling_database(cur, conn, write=False)
                != "vab_test"
            ):
                raise ConsentNotReady("Isolated synthetic schema required")
            cur.execute(
                "SELECT r.patient_id,r.requested_service,r.status,p.synthetic "
                "FROM vab_test.scheduling_case_link l "
                "JOIN vab_test.appointment_request r ON r.request_id=l.request_id "
                "JOIN vab_test.patient p ON p.patient_id=r.patient_id "
                "WHERE l.case_id=%s AND l.synthetic=true "
                "AND r.request_kind='PRIMARY_CARE'",
                (binding.case_id,),
            )
            case = cur.fetchone()
            if (
                case is None
                or case[0] != binding.patient_id
                or case[1] != "PRIMARY_CARE"
                or case[2] not in ("OPEN", "OPTIONS")
                or case[3] is not True
            ):
                raise ConsentNotReady("Approved synthetic Primary Care case required")

            cur.execute(
                "SELECT event_id,correlation_id,actor,occurred_at,details "
                "FROM vab_test.audit_event "
                "WHERE event_type=%s AND details->>'case_id'=%s "
                "AND details->>'patient_id'=%s "
                "ORDER BY occurred_at DESC,event_id DESC LIMIT 1",
                (IDENTITY_EVENT_TYPE, binding.case_id, str(binding.patient_id)),
            )
            identity = cur.fetchone()
            if identity is None:
                raise ConsentNotReady("Recorded identity verification required")
            event_id, correlation, actor, recorded_at, details = identity
            if voice_session_id is not None and (
                correlation != voice_session_id
                or str(event_id) != identity_verification_id
            ):
                raise ConsentNotReady("Identity must belong to this exact voice call")
            try:
                verified_at = datetime.fromisoformat(details["verified_at"])
                expires_at = datetime.fromisoformat(details["expires_at"])
            except (TypeError, ValueError, KeyError) as exc:
                raise ConsentNotReady("Identity evidence invalid") from exc
            now = datetime.now(timezone.utc)
            if (
                not isinstance(details, dict)
                or details.get("identity_verification_id") != str(event_id)
                or details.get("verified") is not True
                or details.get("outcome") != "VERIFIED"
                or details.get("synthetic") is not True
                or details.get("verification_method") != IDENTITY_METHOD
                or details.get("verification_source") != "PERSISTED_SYNTHETIC_CASE"
                or details.get("verifying_principal") != host_subject
                or actor != host_subject
                or not correlation
                or recorded_at != verified_at
                or verified_at.tzinfo is None
                or expires_at.tzinfo is None
                or verified_at > now
                or expires_at <= now
                or expires_at - verified_at != IDENTITY_TTL
            ):
                raise ConsentNotReady("Fresh trusted identity evidence required")

            cur.execute(
                "SELECT s.status,s.channel,s.begins_at,s.ends_at,s.verified_at,"
                "s.source_id,c.specialty,c.active,d.source_kind,d.provenance "
                "FROM vab_test.slot s "
                "JOIN vab_test.clinic c ON c.clinic_id=s.clinic_id "
                "JOIN vab_test.data_source d ON d.source_id=s.source_id "
                "WHERE s.slot_id=%s",
                (slot_id,),
            )
            slot = cur.fetchone()
            if slot is None:
                raise ConsentNotReady("Selected synthetic slot missing")
            (
                status,
                channel,
                begins_at,
                ends_at,
                checked_at,
                source_id,
                specialty,
                active,
                source_kind,
                provenance,
            ) = slot
            bindings = (
                provenance.get("slot_bindings")
                if isinstance(provenance, dict)
                else None
            )
            selected = (
                bindings.get(str(slot_id)) if isinstance(bindings, dict) else None
            )
            if (
                status != "AVAILABLE"
                or channel not in ("VISTA", "FEDERAL_EHR")
                or source_kind != "synthetic_fixture"
                or active is not True
                or not isinstance(specialty, str)
                or specialty.upper() != "PRIMARY_CARE"
                or not isinstance(selected, dict)
                or selected.get("case_id") != binding.case_id
                or selected.get("option_id") != option_id
                or not isinstance(checked_at, datetime)
                or checked_at.tzinfo is None
                or checked_at > now
                or now - checked_at > MAX_SLOT_AGE
                or not isinstance(begins_at, datetime)
                or not isinstance(ends_at, datetime)
                or begins_at.tzinfo is None
                or ends_at.tzinfo is None
                or begins_at <= now
                or ends_at <= begins_at
            ):
                raise ConsentNotReady("Fresh case-bound slot verification required")
            return str(source_id)


class ProtectedConsentCapture:
    """Issue only an internal actor assertion after real session and evidence checks."""

    def __init__(
        self,
        *,
        sessions: SyntheticVeteranSessions,
        read_connect: Callable,
        gateway: PrivateSyntheticSchedulingGateway,
        signing_secret: str,
        host_subject: str,
        approved_case: str,
    ) -> None:
        if not approved_case or not host_subject or len(signing_secret.encode()) < 32:
            raise PermissionError("Protected synthetic consent configuration required")
        self.sessions = sessions
        self.read_connect = read_connect
        self.gateway = gateway
        self.signing_secret = signing_secret
        self.host_subject = host_subject
        self.approved_case = approved_case

    def offers(self, cookie: str | None) -> dict:
        """Return at most three independently verified appointments for review."""
        binding = self.sessions.authorize(cookie, self.approved_case)
        with self.read_connect() as conn:
            with conn.cursor() as cur:
                if (
                    assert_synthetic_scheduling_database(cur, conn, write=False)
                    != "vab_test"
                ):
                    raise ConsentNotReady("Isolated synthetic schema required")
                cur.execute(
                    "SELECT s.slot_id,"
                    "d.provenance->'slot_bindings'->(s.slot_id::text)->>'option_id',"
                    "s.begins_at,s.ends_at "
                    "FROM vab_test.slot s "
                    "JOIN vab_test.data_source d ON d.source_id=s.source_id "
                    "JOIN vab_test.clinic c ON c.clinic_id=s.clinic_id "
                    "WHERE s.status='AVAILABLE' "
                    "AND s.channel IN ('VISTA','FEDERAL_EHR') "
                    "AND d.source_kind='synthetic_fixture' "
                    "AND c.active=true AND upper(c.specialty)='PRIMARY_CARE' "
                    "AND d.provenance->'slot_bindings'->(s.slot_id::text)"
                    "->>'case_id'=%s "
                    "AND s.begins_at>clock_timestamp() "
                    "AND s.verified_at IS NOT NULL "
                    "AND s.verified_at<=clock_timestamp() "
                    "AND s.verified_at>=clock_timestamp()-interval '15 minutes' "
                    "ORDER BY s.begins_at,s.slot_id LIMIT 10",
                    (binding.case_id,),
                )
                candidates = cur.fetchall()
        offered = []
        for slot_id, option_id, begins_at, ends_at in candidates:
            if not isinstance(option_id, str) or not option_id:
                continue
            try:
                verified_consent_evidence(
                    self.read_connect,
                    binding=binding,
                    option_id=option_id,
                    slot_id=slot_id,
                    host_subject=self.host_subject,
                )
            except ConsentNotReady:
                continue
            offered.append(
                {
                    "option_id": option_id,
                    "slot_id": str(slot_id),
                    "begins_at": begins_at.isoformat(),
                    "ends_at": ends_at.isoformat(),
                }
            )
            if len(offered) == 3:
                break
        return {"synthetic": True, "case_id": binding.case_id, "offers": offered}

    def capture(self, cookie: str | None, body: ConsentResponse) -> dict:
        binding = self.sessions.authorize(cookie, body.case_id)
        if body.case_id != self.approved_case:
            raise ConsentNotReady("Case not approved for synthetic consent")
        source = verified_consent_evidence(
            self.read_connect,
            binding=binding,
            option_id=body.option_id,
            slot_id=body.slot_id,
            host_subject=self.host_subject,
        )
        now = int(time.time())
        actor = "synthetic-auth:" + str(binding.subject)
        # This assertion remains inside the backend; it is never an MCP argument
        # or a browser response. The signed-decision writer rechecks option provenance.
        assertion = jwt.encode(
            {
                "iss": ISSUER,
                "aud": AUDIENCE,
                "sub": actor,
                "role": "VETERAN",
                "case_id": binding.case_id,
                "synthetic": True,
                "iat": now,
                "exp": now + 30,
            },
            self.signing_secret,
            algorithm="HS256",
        )
        receipt = self.gateway.record_internal_va_veteran_response_from_trusted_service(
            assertion=assertion,
            expected_actor_id=actor,
            case_id=binding.case_id,
            option_id=body.option_id,
            idempotency_key=body.idempotency_key,
            correlation_id=body.correlation_id,
            verified_evidence_reference=source,
            accepted=body.confirmed,
        )
        return {
            "synthetic": True,
            "case_id": receipt.case_id,
            "option_id": receipt.option_id,
            "consent_recorded": True,
            "confirmed": receipt.status == "ACCEPTED",
            "decision_id": receipt.decision_id,
            "transition_id": receipt.transition_id,
            "booking_created": False,
        }


def build_protected_consent(
    sessions: SyntheticVeteranSessions,
) -> ProtectedConsentCapture:
    if os.getenv("VAB_SUPABASE_TEST_MODE") != "true":
        raise PermissionError("Isolated synthetic test mode required")
    try:
        secret = os.environ["VAB_SIGNED_DECISION_VERIFIER_SECRET"]
        host_subject = os.environ["VAB_TRUSTED_HOST_SUBJECT"]
        approved_case = os.environ["VAB_PRIVATE_PC_APPROVED_CASE"]
        if approved_case != sessions._binding.case_id:
            raise PermissionError("Consent and session case approvals differ")
    except KeyError as exc:
        raise PermissionError("Protected consent configuration missing") from exc
    return ProtectedConsentCapture(
        sessions=sessions,
        read_connect=connect_private_supabase_test_scheduling_readonly,
        gateway=PrivateSyntheticSchedulingGateway(
            connect=connect_private_supabase_test_scheduling,
            verifier_secret=secret,
        ),
        signing_secret=secret,
        host_subject=host_subject,
        approved_case=approved_case,
    )


def create_protected_consent_router(
    capture: ProtectedConsentCapture,
    *,
    origin: str,
) -> APIRouter:
    router = APIRouter(prefix="/api/synthetic-veteran/consent")

    @router.get("/offers", include_in_schema=False)
    async def get_offers(request: Request, response: Response):
        response.headers["Cache-Control"] = "no-store"
        try:
            return await run_in_threadpool(
                capture.offers, request.cookies.get(COOKIE_NAME)
            )
        except (ConsentNotReady, SessionDenied, PermissionError, ValueError) as exc:
            raise HTTPException(
                status_code=403, detail="Offers not authorized"
            ) from exc
        except SessionUnavailable as exc:
            raise HTTPException(status_code=503, detail="Session unavailable") from exc

    @router.post("", include_in_schema=False)
    async def record_consent(
        body: ConsentResponse, request: Request, response: Response
    ):
        response.headers["Cache-Control"] = "no-store"
        if request.headers.get("origin") != origin:
            raise HTTPException(status_code=403, detail="Invalid request origin")
        try:
            return await run_in_threadpool(
                capture.capture, request.cookies.get(COOKIE_NAME), body
            )
        except (ConsentNotReady, SessionDenied, PermissionError, ValueError) as exc:
            raise HTTPException(
                status_code=403, detail="Consent not authorized"
            ) from exc
        except SessionUnavailable as exc:
            raise HTTPException(status_code=503, detail="Session unavailable") from exc

    return router
