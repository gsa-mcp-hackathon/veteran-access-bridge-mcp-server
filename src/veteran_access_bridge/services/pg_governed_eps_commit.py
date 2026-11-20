"""Fail-closed booking orchestration: authenticated context, commit, readback.

This local-only service is NOT registered as an MCP tool. Authentication must
be performed by a trusted application boundary, not asserted by an MCP caller.
No VA/EPS network writes are performed.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from veteran_access_bridge.adapters.pg_eps_recovery import (
    recover_committed_eps_booking,
)
from veteran_access_bridge.adapters.pg_synthetic_eps_booking import (
    EPSBookingRequest,
    commit_synthetic_eps_booking,
)


class BookingOutcome(str, Enum):
    COMMITTED = "COMMITTED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class VerifiedSchedulerContext:
    """Trusted boundary assertion, never deserialize from MCP tool arguments."""

    actor_id: str
    case_id: str
    authenticated: bool
    authorized_scheduler: bool


@dataclass(frozen=True)
class BookingOutcomeReceipt:
    status: BookingOutcome
    booking_id: str | None
    detail: str


def commit_verified_synthetic_eps_booking(
    connect: Callable,
    *,
    context: VerifiedSchedulerContext,
    request: EPSBookingRequest,
) -> BookingOutcomeReceipt:
    """Only acknowledge a booking after commit and fresh-connection readback.

    An unknown commit result is RECOVERY_REQUIRED, never a second booking.
    Caller must authenticate and authorize the context independently.
    """
    if not isinstance(context, VerifiedSchedulerContext):
        raise PermissionError("Verified scheduler context required")
    if not context.authenticated or not context.authorized_scheduler:
        raise PermissionError("Scheduler identity and permission required")
    if context.case_id != request.case_id:
        raise PermissionError("Scheduler case scope mismatch")
    if not context.actor_id or context.actor_id != request.scheduler_actor_id:
        raise PermissionError("Scheduler actor does not match request")

    try:
        with connect() as conn:
            try:
                commit_synthetic_eps_booking(conn, request)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
    except ValueError:
        raise
    except Exception:
        # Cannot safely retry an ambiguous commit response.
        return BookingOutcomeReceipt(
            BookingOutcome.RECOVERY_REQUIRED,
            None,
            "Commit outcome unknown; reconcile with the original idempotency key",
        )

    try:
        recovered = recover_committed_eps_booking(
            connect,
            case_id=request.case_id,
            option_id=request.option_id,
            slot_id=request.slot_id,
            authorization_id=request.authorization_id,
            idempotency_key=request.idempotency_key,
            scheduler_actor_id=context.actor_id,
        )
    except Exception:
        return BookingOutcomeReceipt(
            BookingOutcome.RECOVERY_REQUIRED,
            None,
            "Committed booking could not be independently re-read",
        )
    if recovered is None:
        return BookingOutcomeReceipt(
            BookingOutcome.RECOVERY_REQUIRED,
            None,
            "No durable booking found on fresh connection",
        )
    return BookingOutcomeReceipt(
        BookingOutcome.COMMITTED,
        str(recovered.booking_id),
        "Synthetic EPS booking committed and recovered",
    )


def commit_with_signed_scheduler_assertion(
    connect: Callable,
    *,
    scheduler_assertion: str,
    verifier_secret: str,
    request: EPSBookingRequest,
) -> BookingOutcomeReceipt:
    """Trusted-server entry: verify a signed assertion before touching PostgreSQL.

    The verifier secret comes from a protected server setting, never a tool
    argument. This entrypoint is not exposed via MCP or HTTP.
    """
    from veteran_access_bridge.services.scheduler_assertions import (
        verify_scheduler_assertion,
    )

    context = verify_scheduler_assertion(
        scheduler_assertion,
        signing_secret=verifier_secret,
        required_case_id=request.case_id,
    )
    return commit_verified_synthetic_eps_booking(
        connect, context=context, request=request
    )
