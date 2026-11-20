"""Opt-in protected synthetic Primary Care booking endpoint, not an MCP tool."""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.pg_scheduling_sql import execute_scheduling_sql
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
)
from veteran_access_bridge.services.pg_governed_va_commit import (
    VABookingReceipt,
    VABookingRequest,
    _ids,
    _readback,
)
from veteran_access_bridge.services.private_va_booking_grant_issuer import (
    PrivateVABookingGrantIssuer,
)
from veteran_access_bridge.services.signed_scheduling_lifecycle import (
    TrustedPrimaryCareBookingCoordinator,
    TrustedSchedulingServices,
)
from veteran_access_bridge.services.trusted_primary_care import (
    IDENTITY_EVENT_TYPE,
    PostgresPrimaryCarePolicyEvaluator,
    TrustedHostAuthenticator,
)

logger = logging.getLogger(__name__)
APPROVED_CASE = "VAB-DEMO-20261113-CASE-031"
CONSENT_MAX_AGE = timedelta(minutes=5)


class PrivateBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1, max_length=128)
    option_id: str = Field(min_length=1, max_length=128)
    slot_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=128)


class ProtectedPrimaryCareBooking:
    """Request-scoped composition of existing trusted authorization and booking."""

    def __init__(
        self,
        *,
        services: TrustedSchedulingServices,
        authenticator: TrustedHostAuthenticator,
        signing_secret: str,
        approved_case: str = APPROVED_CASE,
    ) -> None:
        if (
            not approved_case
            or approved_case != approved_case.strip()
            or len(approved_case) > 128
        ):
            raise PermissionError("Exactly one approved synthetic case is required")
        self._approved_case = approved_case
        if services._va_booking_secret() != signing_secret:
            raise PermissionError("Grant issuer and booking verifier key mismatch")
        self._services = services
        self._authenticator = authenticator
        self._signing_secret = signing_secret

    def book(self, *, assertion: str, request: VABookingRequest):
        if request.case_id != self._approved_case:
            raise PermissionError("Case is not approved for isolated booking")
        bound: dict = {}

        def authenticate(token):
            principal, claims = self._authenticator.authenticate_bound_booking(
                token, request
            )
            bound.update(claims)
            return principal

        def evaluate(candidate, actor):
            policy = PostgresPrimaryCarePolicyEvaluator(self._services.connect)(
                candidate, actor
            )
            if policy.identity_verification_id != bound.get(
                "identity_verification_id"
            ) or str(policy.veteran_confirmation_id) != bound.get(
                "veteran_confirmation_id"
            ):
                raise PermissionError("Host and persisted evidence do not match")
            consent_expires = datetime.fromtimestamp(
                bound["consent_expires_at"], tz=timezone.utc
            )
            with self._services.connect() as conn:
                with conn.cursor() as cur:
                    schema = assert_synthetic_scheduling_database(
                        cur, conn, write=False
                    )
                    if schema != "vab_test":
                        raise PermissionError("Isolated test schema required")
                    execute_scheduling_sql(
                        cur,
                        schema,
                        "SELECT decided_at,clock_timestamp() "
                        "FROM vab.scheduling_decision WHERE decision_id=%s "
                        "AND case_id=%s AND option_id=%s "
                        "AND decision_kind='VETERAN_CONFIRMED' "
                        "AND decision_status='ACCEPTED' AND actor_role='VETERAN'",
                        (
                            policy.veteran_confirmation_id,
                            candidate.case_id,
                            candidate.option_id,
                        ),
                    )
                    row = cur.fetchone()
                    if "voice_session_id" in bound:
                        execute_scheduling_sql(
                            cur,
                            schema,
                            "SELECT EXISTS (SELECT 1 FROM vab.audit_event i "
                            "JOIN vab.scheduling_decision d "
                            "ON d.correlation_id=i.correlation_id "
                            "WHERE i.event_id=%s AND i.event_type=%s "
                            "AND i.details->>'case_id'=%s AND i.correlation_id=%s "
                            "AND d.decision_id=%s AND d.case_id=%s)",
                            (
                                policy.identity_verification_id,
                                IDENTITY_EVENT_TYPE,
                                candidate.case_id,
                                bound["voice_session_id"],
                                policy.veteran_confirmation_id,
                                candidate.case_id,
                            ),
                        )
                        if cur.fetchone()[0] is not True:
                            raise PermissionError(
                                "Identity and consent must belong to the same call"
                            )
            if (
                row is None
                or row[0] > row[1]
                or consent_expires <= row[1]
                or consent_expires > row[0] + CONSENT_MAX_AGE
            ):
                raise PermissionError("Fresh persisted Veteran consent required")
            return replace(
                policy,
                consent_expires_at=consent_expires,
                voice_session_id=bound.get("voice_session_id"),
            )

        issuer = PrivateVABookingGrantIssuer(
            signing_secret=self._signing_secret,
            authenticate_service=authenticate,
            evaluate_booking=evaluate,
        )
        return TrustedPrimaryCareBookingCoordinator(
            services=self._services, grant_issuer=issuer
        ).commit_and_verify(host_assertion=assertion, request=request)

    def recover(self, *, assertion: str, request: VABookingRequest):
        if request.case_id != self._approved_case:
            raise PermissionError("Case is not approved for isolated recovery")
        principal = self._authenticator.authenticate_bound_recovery(assertion, request)
        _, _, audit_id = _ids(request)
        with self._services.connect() as conn:
            with conn.cursor() as cur:
                schema = assert_synthetic_scheduling_database(
                    conn=conn, cur=cur, write=False
                )
                if schema != "vab_test":
                    raise PermissionError("Isolated test schema required")
                execute_scheduling_sql(
                    cur,
                    schema,
                    "SELECT actor,details FROM vab.audit_event "
                    "WHERE event_id=%s AND event_type='BOOKED_SIMULATED'",
                    (audit_id,),
                )
                row = cur.fetchone()
            if row is None:
                return VABookingReceipt(
                    "NOT_FOUND_UNCONFIRMED", request.case_id, None, None, None, False
                )
            actor, details = row
            if actor != principal.subject or not isinstance(details, dict):
                raise PermissionError("Original booking service identity required")
            if details.get("voice_session_id") != principal.voice_session_id:
                raise PermissionError("Original voice session required for recovery")
            fields = (
                "identity_verification_id",
                "identity_verification_expires_at",
                "policy_evidence_reference",
                "veteran_confirmation_id",
            )
            if any(field not in details for field in fields):
                raise ValueError("Original booking evidence is incomplete")
            claims = {"sub": actor, **{field: details[field] for field in fields}}
            if principal.voice_session_id is not None:
                claims["voice_session_id"] = principal.voice_session_id
            return _readback(conn, request, claims)


def build_private_booking_from_environment(
    *, approved_case: str | None = None
) -> ProtectedPrimaryCareBooking:
    services = TrustedSchedulingServices(
        connect=connect_private_supabase_test_scheduling,
        verifier_secret=os.getenv("VAB_SIGNED_DECISION_VERIFIER_SECRET", ""),
        va_booking_verifier_secret=os.getenv(
            "VAB_PRIVATE_VA_BOOKING_SIGNING_SECRET", ""
        ),
    )
    return ProtectedPrimaryCareBooking(
        services=services,
        authenticator=TrustedHostAuthenticator.from_environment(services.connect),
        signing_secret=os.environ["VAB_PRIVATE_VA_BOOKING_SIGNING_SECRET"],
        approved_case=approved_case
        or os.getenv("VAB_PRIVATE_PC_APPROVED_CASE", APPROVED_CASE),
    )


def _verified_receipt(result: VABookingReceipt, case_id: str):
    try:
        appointment_id = UUID(result.appointment_id)
    except (ValueError, TypeError, AttributeError):
        appointment_id = None
    if (
        result.state != "BOOKED_SIMULATED"
        or not result.verified
        or result.case_id != case_id
        or appointment_id is None
        or result.begins_at is None
        or result.ends_at is None
        or result.begins_at.tzinfo is None
        or result.ends_at.tzinfo is None
        or result.ends_at <= result.begins_at
    ):
        raise HTTPException(
            status_code=409, detail="Booking unverified; recovery required"
        )
    return {
        "state": result.state,
        "case_id": result.case_id,
        "appointment_id": result.appointment_id,
        "begins_at": result.begins_at,
        "ends_at": result.ends_at,
        "synthetic": True,
        "verified": True,
        **{
            key: value.strip()
            for key, value in {
                "clinic_name": result.clinic_name,
                "provider_name": result.provider_name,
            }.items()
            if isinstance(value, str)
            and 0 < len(value.strip()) <= 200
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
        },
        **(
            {"voice_session_id": result.voice_session_id}
            if result.voice_session_id is not None
            else {}
        ),
    }


def create_private_booking_router(service: ProtectedPrimaryCareBooking) -> APIRouter:
    router = APIRouter()

    def perform(
        body: PrivateBookingRequest,
        authorization: str | None,
        *,
        recovery: bool,
    ):
        scheme, separator, assertion = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or separator != " " or not assertion.strip():
            raise HTTPException(
                status_code=401, detail="Trusted host assertion required"
            )
        try:
            operation = service.recover if recovery else service.book
            result = operation(
                assertion=assertion,
                request=VABookingRequest(**body.model_dump()),
            )
        except PermissionError as exc:
            raise HTTPException(
                status_code=403, detail="Booking not authorized"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="Booking rejected") from exc
        except Exception as exc:
            logger.error("Protected booking failed: %s", type(exc).__name__)
            raise HTTPException(
                status_code=503, detail="Booking unavailable; recovery may be required"
            ) from exc
        return _verified_receipt(result, body.case_id)

    @router.post("/internal/synthetic-primary-care/booking", include_in_schema=False)
    def book(
        body: PrivateBookingRequest,
        authorization: Annotated[str | None, Header()] = None,
    ):
        return perform(body, authorization, recovery=False)

    @router.post("/internal/synthetic-primary-care/recovery", include_in_schema=False)
    def recover(
        body: PrivateBookingRequest,
        authorization: Annotated[str | None, Header()] = None,
    ):
        return perform(body, authorization, recovery=True)

    return router
