"""Private Sprint A scheduling gateway for future governed MCP tools.

No remote route or tool is registered here. An independent trusted server
issues case-scoped JWT assertions. All database writes remain synthetic-only
and fail closed unless configured with a separately approved connection.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

from veteran_access_bridge.adapters.pg_eps_recovery import (
    EPSRecoveryReceipt,
    recover_committed_eps_booking,
)
from veteran_access_bridge.adapters.pg_synthetic_eps_booking import EPSBookingRequest
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
)
from veteran_access_bridge.services.pg_governed_eps_commit import (
    BookingOutcomeReceipt,
    commit_with_signed_scheduler_assertion,
)
from veteran_access_bridge.services.pg_signed_decisions import (
    DecisionReceipt,
    persist_signed_scheduling_decision,
    persist_signed_va_scheduling_decision,
)
from veteran_access_bridge.services.scheduler_assertions import (
    verify_scheduler_assertion,
)


@dataclass(frozen=True)
class PrivateSyntheticSchedulingGateway:
    """Only callable from a separately authenticated private service boundary."""

    connect: Callable
    verifier_secret: str

    def __post_init__(self):
        if not isinstance(self.verifier_secret, str) or (
            len(self.verifier_secret.encode()) < 32
        ):
            raise PermissionError("Protected signing verifier secret required")

    def read_case_from_trusted_service(
        self,
        *,
        assertion: str,
        expected_actor_id: str,
        case_id: str,
        include_history: bool = False,
    ) -> dict:
        """Authorize a synthetic case-scoped read before opening PostgreSQL.

        This is a private server method, not a public MCP tool. The issuer
        must independently authenticate and authorize the subject for this
        case; the shared demo bearer token is never sufficient.
        """
        from veteran_access_bridge.mcp.durable_runtime import (
            read_case_from_supabase,
        )
        from veteran_access_bridge.services.pg_signed_decisions import _trusted_claims

        claims = _trusted_claims(assertion, self.verifier_secret, case_id)
        if claims["sub"] != expected_actor_id or claims["role"] not in {
            "VETERAN",
            "SCHEDULER",
        }:
            raise PermissionError(
                "Verified actor does not match authorized case reader"
            )
        return read_case_from_supabase(
            case_id, include_history=include_history, connect=self.connect
        )

    def record_decision(
        self,
        *,
        assertion: str,
        case_id: str,
        option_id: str,
        idempotency_key: str,
        correlation_id: str,
        service_evidence_reference: str,
        accepted: bool,
    ) -> DecisionReceipt:
        return persist_signed_scheduling_decision(
            self.connect,
            assertion=assertion,
            verifier_secret=self.verifier_secret,
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            service_evidence_reference=service_evidence_reference,
            accepted=accepted,
        )

    def confirm_veteran_from_trusted_service(
        self,
        *,
        assertion: str,
        expected_actor_id: str,
        case_id: str,
        option_id: str,
        idempotency_key: str,
        correlation_id: str,
        verified_evidence_reference: str,
    ) -> DecisionReceipt:
        """Persist an accepted Veteran decision after verifying the signed actor.

        Only a trusted private caller may provide the assertion/evidence.
        Public MCP tools never accept either credential as an argument.
        """
        from veteran_access_bridge.services.pg_signed_decisions import _trusted_claims

        claims = _trusted_claims(assertion, self.verifier_secret, case_id)
        if claims["role"] != "VETERAN" or claims["sub"] != expected_actor_id:
            raise PermissionError("Verified Veteran actor does not match case action")
        return self.record_decision(
            assertion=assertion,
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            service_evidence_reference=verified_evidence_reference,
            accepted=True,
        )

    def record_veteran_response_from_trusted_service(
        self,
        *,
        assertion: str,
        expected_actor_id: str,
        case_id: str,
        option_id: str,
        idempotency_key: str,
        correlation_id: str,
        verified_evidence_reference: str,
        accepted: bool,
    ) -> DecisionReceipt:
        """Record a signed Veteran response; a rejection never creates booking."""
        from veteran_access_bridge.services.pg_signed_decisions import _trusted_claims

        claims = _trusted_claims(assertion, self.verifier_secret, case_id)
        if claims["role"] != "VETERAN" or claims["sub"] != expected_actor_id:
            raise PermissionError("Verified Veteran actor does not match case action")
        return self.record_decision(
            assertion=assertion,
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            service_evidence_reference=verified_evidence_reference,
            accepted=accepted,
        )

    def approve_scheduler_from_trusted_service(
        self,
        *,
        assertion: str,
        expected_actor_id: str,
        case_id: str,
        option_id: str,
        idempotency_key: str,
        correlation_id: str,
        verified_evidence_reference: str,
        accepted: bool,
    ) -> DecisionReceipt:
        """Persist scheduler review only after verifying signed scheduler scope."""
        from veteran_access_bridge.services.pg_signed_decisions import _trusted_claims

        claims = _trusted_claims(assertion, self.verifier_secret, case_id)
        if claims["role"] != "SCHEDULER" or claims["sub"] != expected_actor_id:
            raise PermissionError("Verified Scheduler actor does not match case action")
        return self.record_decision(
            assertion=assertion,
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            service_evidence_reference=verified_evidence_reference,
            accepted=accepted,
        )

    def _record_internal_va_decision(
        self,
        *,
        assertion: str,
        expected_actor_id: str,
        expected_role: str,
        case_id: str,
        option_id: str,
        idempotency_key: str,
        correlation_id: str,
        verified_evidence_reference: str,
        accepted: bool,
    ) -> DecisionReceipt:
        from veteran_access_bridge.services.pg_signed_decisions import _trusted_claims

        claims = _trusted_claims(assertion, self.verifier_secret, case_id)
        if claims["role"] != expected_role or claims["sub"] != expected_actor_id:
            raise PermissionError("Verified VA scheduling actor does not match action")
        return persist_signed_va_scheduling_decision(
            self.connect,
            assertion=assertion,
            verifier_secret=self.verifier_secret,
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            service_evidence_reference=verified_evidence_reference,
            accepted=accepted,
        )

    def record_internal_va_veteran_response_from_trusted_service(
        self,
        *,
        assertion: str,
        expected_actor_id: str,
        case_id: str,
        option_id: str,
        idempotency_key: str,
        correlation_id: str,
        verified_evidence_reference: str,
        accepted: bool,
    ) -> DecisionReceipt:
        """Persist a signed Veteran response only for a VistA/EHR option."""
        return self._record_internal_va_decision(
            assertion=assertion,
            expected_actor_id=expected_actor_id,
            expected_role="VETERAN",
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            verified_evidence_reference=verified_evidence_reference,
            accepted=accepted,
        )

    def approve_internal_va_schedule_from_trusted_service(
        self,
        *,
        assertion: str,
        expected_actor_id: str,
        case_id: str,
        option_id: str,
        idempotency_key: str,
        correlation_id: str,
        verified_evidence_reference: str,
        accepted: bool,
    ) -> DecisionReceipt:
        """Persist actual Scheduler approval; service identity is not substituted."""
        return self._record_internal_va_decision(
            assertion=assertion,
            expected_actor_id=expected_actor_id,
            expected_role="SCHEDULER",
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            verified_evidence_reference=verified_evidence_reference,
            accepted=accepted,
        )

    def book(
        self, *, scheduler_assertion: str, request: EPSBookingRequest
    ) -> BookingOutcomeReceipt:
        return commit_with_signed_scheduler_assertion(
            self.connect,
            scheduler_assertion=scheduler_assertion,
            verifier_secret=self.verifier_secret,
            request=request,
        )

    def recover(
        self, *, scheduler_assertion: str, request: EPSBookingRequest
    ) -> EPSRecoveryReceipt | None:
        actor = verify_scheduler_assertion(
            scheduler_assertion,
            signing_secret=self.verifier_secret,
            required_case_id=request.case_id,
        )
        if actor.actor_id != request.scheduler_actor_id:
            raise PermissionError("Recovery requires the original scheduler identity")
        return recover_committed_eps_booking(
            self.connect,
            case_id=request.case_id,
            option_id=request.option_id,
            slot_id=request.slot_id,
            authorization_id=request.authorization_id,
            idempotency_key=request.idempotency_key,
            scheduler_actor_id=actor.actor_id,
        )


def create_private_sprint_a_test_gateway() -> PrivateSyntheticSchedulingGateway:
    """Trusted-server construction; impossible via HTTP/MCP tool parameters."""
    secret = os.getenv("VAB_SIGNED_DECISION_VERIFIER_SECRET", "")
    return PrivateSyntheticSchedulingGateway(
        connect=connect_private_supabase_test_scheduling,
        verifier_secret=secret,
    )
