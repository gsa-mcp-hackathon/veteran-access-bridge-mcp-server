"""Trusted application-service facade for signed synthetic scheduling.

No HTTP/MCP route, credential issuer, or demo-header authentication lives here.
Actor-scoped operations delegate to the existing private gateway. Callers must
supply independently issued assertions and protected verifier configuration.
Nothing calls VA/EPS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from veteran_access_bridge.adapters.pg_synthetic_eps_booking import EPSBookingRequest
from veteran_access_bridge.services.pg_booking_readback import (
    BookingReadback,
)
from veteran_access_bridge.services.pg_governed_eps_commit import (
    BookingOutcome,
    BookingOutcomeReceipt,
)
from veteran_access_bridge.services.pg_governed_va_commit import (
    VABookingReceipt,
    VABookingRequest,
    commit_internal_va_booking,
    readback_internal_va_booking,
)
from veteran_access_bridge.services.pg_signed_decisions import DecisionReceipt
from veteran_access_bridge.services.private_va_booking_grant_issuer import (
    PrivateVABookingGrantIssuer,
)
from veteran_access_bridge.services.supabase_scheduling_gateway import (
    PrivateSyntheticSchedulingGateway,
)


@dataclass(frozen=True)
class TrustedSchedulingServices:
    """Dependencies injected from independently authenticated server code."""

    connect: Callable
    verifier_secret: str
    va_booking_verifier_secret: str | None = None

    def __post_init__(self) -> None:
        if not callable(self.connect):
            raise ValueError("Database connection factory required")
        if (
            not isinstance(self.verifier_secret, str)
            or len(self.verifier_secret.encode()) < 32
        ):
            raise PermissionError("Protected trusted verifier required")
        if self.va_booking_verifier_secret is not None and (
            not isinstance(self.va_booking_verifier_secret, str)
            or len(self.va_booking_verifier_secret.encode()) < 32
        ):
            raise PermissionError("Protected internal VA booking verifier required")

    def _va_booking_secret(self) -> str:
        secret = self.va_booking_verifier_secret
        if not isinstance(secret, str) or len(secret.encode()) < 32:
            raise PermissionError("Trusted internal VA booking verifier required")
        return secret

    def _private_gateway(self) -> PrivateSyntheticSchedulingGateway:
        return PrivateSyntheticSchedulingGateway(
            connect=self.connect,
            verifier_secret=self.verifier_secret,
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
        accepted: bool = True,
    ) -> DecisionReceipt:
        """Record a Veteran or scheduler decision using a signed actor claim."""
        return self._private_gateway().record_decision(
            assertion=assertion,
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
        """Persist Veteran confirmation only for the independently asserted actor."""
        return self._private_gateway().confirm_veteran_from_trusted_service(
            assertion=assertion,
            expected_actor_id=expected_actor_id,
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            verified_evidence_reference=verified_evidence_reference,
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
        """Persist confirmation or rejection without converting it into approval."""
        return self._private_gateway().record_veteran_response_from_trusted_service(
            assertion=assertion,
            expected_actor_id=expected_actor_id,
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            verified_evidence_reference=verified_evidence_reference,
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
        """Persist Scheduler review through the role- and case-scoped gateway."""
        return self._private_gateway().approve_scheduler_from_trusted_service(
            assertion=assertion,
            expected_actor_id=expected_actor_id,
            case_id=case_id,
            option_id=option_id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            verified_evidence_reference=verified_evidence_reference,
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
        """Record a signed Veteran response against a synthetic VistA/EHR option."""
        gateway = self._private_gateway()
        return gateway.record_internal_va_veteran_response_from_trusted_service(
            assertion=assertion,
            expected_actor_id=expected_actor_id,
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
        """Record an independently asserted Scheduler decision for internal VA."""
        return (
            self._private_gateway().approve_internal_va_schedule_from_trusted_service(
                assertion=assertion,
                expected_actor_id=expected_actor_id,
                case_id=case_id,
                option_id=option_id,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                verified_evidence_reference=verified_evidence_reference,
                accepted=accepted,
            )
        )

    def commit_internal_va_booking(
        self, *, assertion: str, request: VABookingRequest
    ) -> VABookingReceipt:
        """Submit one private internal-VA booking under the dedicated service grant."""
        return commit_internal_va_booking(
            self.connect,
            assertion=assertion,
            verifier_secret=self._va_booking_secret(),
            request=request,
        )

    def inspect_internal_va_booking(
        self, *, assertion: str, request: VABookingRequest
    ) -> VABookingReceipt:
        """Read back only the original case/option/slot-scoped VA booking."""
        return readback_internal_va_booking(
            self.connect,
            assertion=assertion,
            verifier_secret=self._va_booking_secret(),
            request=request,
        )

    def commit_booking(
        self, *, scheduler_assertion: str, request: EPSBookingRequest
    ) -> BookingOutcomeReceipt:
        """Commit only with a signed scheduler identity, never a demo persona."""
        return self._private_gateway().book(
            scheduler_assertion=scheduler_assertion,
            request=request,
        )

    def inspect_booking(
        self, *, scheduler_assertion: str, request: EPSBookingRequest
    ) -> BookingReadback:
        """Read back a known booking only for the original signed Scheduler."""
        recovered = self._private_gateway().recover(
            scheduler_assertion=scheduler_assertion,
            request=request,
        )
        if recovered is None:
            return BookingReadback(
                state="NOT_FOUND_UNCONFIRMED",
                booking_id=None,
                case_id=request.case_id,
                verified=False,
            )
        if (
            recovered.case_id != request.case_id
            or recovered.option_id != request.option_id
            or recovered.slot_id != request.slot_id
            or recovered.scheduler_actor_id != request.scheduler_actor_id
            or recovered.status != "BOOKED_SIMULATED"
        ):
            return BookingReadback(
                state="RECOVERY_REQUIRED",
                booking_id=None,
                case_id=request.case_id,
                verified=False,
            )
        return BookingReadback(
            state="BOOKED_SIMULATED",
            booking_id=str(recovered.booking_id),
            case_id=request.case_id,
            verified=True,
        )

    def commit_and_verify(
        self, *, scheduler_assertion: str, request: EPSBookingRequest
    ) -> BookingReadback:
        """One submission only; ambiguous outcomes may only be inspected.

        The commit service already performs a fresh-connection recovery check.
        An unknown commit cannot be retried by this coordinator.
        """
        outcome = self.commit_booking(
            scheduler_assertion=scheduler_assertion, request=request
        )
        if outcome.status == BookingOutcome.CONFLICT:
            return BookingReadback(
                state="RECOVERY_REQUIRED",
                booking_id=None,
                case_id=request.case_id,
                verified=False,
            )
        if outcome.status == BookingOutcome.RECOVERY_REQUIRED:
            # Unknown commit may have succeeded; absence is not safe to retry.
            receipt = self.inspect_booking(
                scheduler_assertion=scheduler_assertion,
                request=request,
            )
            if receipt.verified:
                return receipt
            return BookingReadback(
                state="RECOVERY_REQUIRED",
                booking_id=None,
                case_id=request.case_id,
                verified=False,
            )
        receipt = self.inspect_booking(
            scheduler_assertion=scheduler_assertion,
            request=request,
        )
        if not receipt.verified or receipt.booking_id != outcome.booking_id:
            return BookingReadback(
                state="RECOVERY_REQUIRED",
                booking_id=None,
                case_id=request.case_id,
                verified=False,
            )
        return receipt


@dataclass(frozen=True)
class TrustedPrimaryCareBookingCoordinator:
    """Private composition of grant issuance, one booking submission, and readback.

    The host must provide real authentication and persisted-evidence adapters to
    the issuer. This coordinator is not an HTTP or MCP endpoint and never
    returns the short-lived booking grant.
    """

    services: TrustedSchedulingServices
    grant_issuer: PrivateVABookingGrantIssuer

    def commit_and_verify(
        self, *, host_assertion: str, request: VABookingRequest
    ) -> VABookingReceipt:
        grant = self.grant_issuer.issue(
            host_assertion=host_assertion,
            request=request,
        )
        outcome = self.services.commit_internal_va_booking(
            assertion=grant,
            request=request,
        )
        try:
            receipt = self.services.inspect_internal_va_booking(
                assertion=grant,
                request=request,
            )
        except Exception:
            return VABookingReceipt(
                "RECOVERY_REQUIRED",
                request.case_id,
                None,
                None,
                None,
                False,
            )
        if (
            receipt.state != "BOOKED_SIMULATED"
            or not receipt.verified
            or receipt.case_id != request.case_id
            or (
                outcome.state == "BOOKED_SIMULATED"
                and (
                    outcome.case_id != request.case_id
                    or outcome.appointment_id != receipt.appointment_id
                )
            )
        ):
            return VABookingReceipt(
                "RECOVERY_REQUIRED",
                request.case_id,
                None,
                None,
                None,
                False,
            )
        return receipt
