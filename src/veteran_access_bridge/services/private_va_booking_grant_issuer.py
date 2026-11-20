"""Private trusted-host grant issuance contract for synthetic VA Primary Care.

This module is NOT a public MCP/HTTP endpoint. An independently protected host
must inject a genuine service authenticator and a database-backed policy/evidence
evaluator. Neither is provided by the model, browser, nor an MCP tool parameter.

It is deliberately not wired into production until these adapters pass review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID, uuid4

import jwt

from veteran_access_bridge.services.pg_governed_va_commit import (
    AUDIENCE,
    ISSUER,
    POLICY_VERSION,
    SCOPE,
    VABookingRequest,
    _validate_voice_session_id,
    _verified_booking_claims,
)


@dataclass(frozen=True)
class AuthenticatedService:
    """Host-verified service principal; never constructed from client claims."""

    subject: str
    authenticated: bool
    scope: str
    case_ids: frozenset[str] = frozenset()
    voice_session_id: str | None = None


@dataclass(frozen=True)
class EvaluatedBookingPolicy:
    """Snapshot returned solely by trusted, independently implemented policy code.

    A future host implementation must derive this from the persisted patient,
    case, newest paired Veteran confirmation, synthetic VA slot provenance,
    policy rules, and permitted service identity.
    """

    case_id: str
    option_id: str
    slot_id: UUID
    identity_verification_id: str | None
    identity_verification_expires_at: datetime | None
    veteran_confirmation_id: UUID | None
    policy_evidence_reference: str
    decision: str
    human_review_required: bool
    synthetic: bool
    care_pathway: str
    consent_expires_at: datetime | None = None
    voice_session_id: str | None = None


class PrivateVABookingGrantIssuer:
    """No default authentication, evaluator, endpoint, or stored credentials.

    The protected host is responsible for independently authenticating the
    calling service and evaluating authoritative persisted evidence. This
    class only enforces the resulting typed contract and signs a narrowly
    scoped grant accepted by the existing private booking verifier.
    """

    def __init__(
        self,
        *,
        signing_secret: str,
        authenticate_service: Callable[[str], AuthenticatedService],
        evaluate_booking: Callable[
            [VABookingRequest, AuthenticatedService], EvaluatedBookingPolicy
        ],
    ) -> None:
        if not isinstance(signing_secret, str) or len(signing_secret.encode()) < 32:
            raise PermissionError("Protected signing key of at least 32 bytes required")
        if not callable(authenticate_service) or not callable(evaluate_booking):
            raise PermissionError("Independent protected host adapters required")
        self._signing_secret = signing_secret
        self._authenticate_service = authenticate_service
        self._evaluate_booking = evaluate_booking

    def issue(self, *, host_assertion: str, request: VABookingRequest) -> str:
        """Sign only after independent host authentication and policy evaluation.

        host_assertion is a private host credential, never a public MCP tool
        argument. No caller-supplied actor, policy ALLOW flag, or consent ID
        is accepted in this method.
        """
        if not isinstance(host_assertion, str) or not host_assertion.strip():
            raise PermissionError("Authenticated host context required")
        if not isinstance(request, VABookingRequest):
            raise TypeError("Typed booking request required")

        actor = self._authenticate_service(host_assertion)
        if (
            not isinstance(actor, AuthenticatedService)
            or actor.authenticated is not True
            or not isinstance(actor.subject, str)
            or not actor.subject.strip()
            or actor.scope != SCOPE
            or request.case_id not in actor.case_ids
        ):
            raise PermissionError(
                "Independently authenticated case-scoped booking service required"
            )

        policy = self._evaluate_booking(request, actor)
        if (
            not isinstance(policy, EvaluatedBookingPolicy)
            or policy.decision != "ALLOW"
            or policy.human_review_required is not False
            or policy.synthetic is not True
            or policy.care_pathway != "INTERNAL_VA"
            or policy.case_id != request.case_id
            or policy.option_id != request.option_id
            or policy.slot_id != request.slot_id
            or not isinstance(policy.identity_verification_id, str)
            or not policy.identity_verification_id.strip()
            or not isinstance(policy.identity_verification_expires_at, datetime)
            or policy.identity_verification_expires_at.tzinfo is None
            or policy.identity_verification_expires_at <= datetime.now(timezone.utc)
            or not isinstance(policy.veteran_confirmation_id, UUID)
            or not isinstance(policy.policy_evidence_reference, str)
            or not policy.policy_evidence_reference.strip()
        ):
            raise PermissionError("Current verified synthetic VA policy grant required")

        now = datetime.now(timezone.utc)
        consent_expiry = policy.consent_expires_at
        if consent_expiry is not None and (
            consent_expiry.tzinfo is None or consent_expiry <= now
        ):
            raise PermissionError("Current Veteran consent required")
        grant_expiry = now + timedelta(seconds=90)
        if consent_expiry is not None:
            grant_expiry = min(grant_expiry, consent_expiry)
        claims = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": actor.subject,
            "role": "SERVICE",
            "scope": SCOPE,
            "case_id": request.case_id,
            "option_id": request.option_id,
            "slot_id": str(request.slot_id),
            "idempotency_key": request.idempotency_key,
            "synthetic": True,
            "identity_verified": True,
            "identity_case_id": request.case_id,
            "identity_verification_id": policy.identity_verification_id,
            "identity_verification_expires_at": int(
                policy.identity_verification_expires_at.timestamp()
            ),
            "veteran_confirmation_id": str(policy.veteran_confirmation_id),
            "policy_version": POLICY_VERSION,
            "policy_decision": "ALLOW",
            "policy_evidence_reference": policy.policy_evidence_reference,
            "human_review_required": False,
            "jti": uuid4().hex,
            "iat": now,
            "exp": grant_expiry,
        }
        if policy.voice_session_id is not None:
            claims["voice_session_id"] = _validate_voice_session_id(
                policy.voice_session_id
            )
        token = jwt.encode(claims, self._signing_secret, algorithm="HS256")
        # Verify against the exact protected booking service contract before
        # handing the grant to a separately authorized private service caller.
        _verified_booking_claims(token, self._signing_secret, request)
        return token
