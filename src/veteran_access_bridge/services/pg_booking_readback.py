"""Private, read-only recovery of one known synthetic EPS booking.

Callers supply the original transaction identity from trusted server state.
Neither an MSA demo persona nor an LLM may invent recovery parameters.
"""

from dataclasses import dataclass
from uuid import UUID

from veteran_access_bridge.adapters.pg_eps_recovery import (
    recover_committed_eps_booking,
)


@dataclass(frozen=True)
class BookingReadback:
    state: str
    booking_id: str | None
    case_id: str
    verified: bool
    retry_commit_allowed: bool = False


def readback_known_booking(
    connect,
    *,
    case_id: str,
    option_id: str,
    slot_id: UUID,
    authorization_id: UUID,
    idempotency_key: str,
    scheduler_actor_id: str,
) -> BookingReadback:
    """Inspect a known booking identity without issuing another commit.

    A missing or unreadable receipt is never presented as booked.
    """
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            case_id,
            option_id,
            idempotency_key,
            scheduler_actor_id,
        )
    ):
        raise ValueError("Complete trusted booking identity required")
    if not isinstance(slot_id, UUID) or not isinstance(authorization_id, UUID):
        raise ValueError("UUID slot and authorization identities required")
    try:
        receipt = recover_committed_eps_booking(
            connect,
            case_id=case_id,
            option_id=option_id,
            slot_id=slot_id,
            authorization_id=authorization_id,
            idempotency_key=idempotency_key,
            scheduler_actor_id=scheduler_actor_id,
        )
    except Exception:
        return BookingReadback(
            state="RECOVERY_REQUIRED",
            booking_id=None,
            case_id=case_id,
            verified=False,
        )
    if receipt is None:
        return BookingReadback(
            state="NOT_FOUND_UNCONFIRMED",
            booking_id=None,
            case_id=case_id,
            verified=False,
        )
    if (
        receipt.case_id != case_id
        or receipt.option_id != option_id
        or receipt.slot_id != slot_id
        or receipt.scheduler_actor_id != scheduler_actor_id
        or receipt.status != "BOOKED_SIMULATED"
    ):
        return BookingReadback(
            state="RECOVERY_REQUIRED",
            booking_id=None,
            case_id=case_id,
            verified=False,
        )
    return BookingReadback(
        state="BOOKED_SIMULATED",
        booking_id=str(receipt.booking_id),
        case_id=case_id,
        verified=True,
    )
