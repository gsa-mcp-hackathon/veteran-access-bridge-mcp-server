"""Offline recovery contract: failed/unknown commits cannot become bookings."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from veteran_access_bridge.services import pg_booking_readback

CASE = "DEMO-CARD-5000335-001"


def _read(monkeypatch, outcome):
    slot, auth, booking = uuid4(), uuid4(), uuid4()
    calls = []

    def recover(_connect, **kwargs):
        calls.append(kwargs)
        if isinstance(outcome, Exception):
            raise outcome
        if outcome == "present":
            return SimpleNamespace(
                booking_id=booking,
                case_id=CASE,
                option_id="OPT-1",
                slot_id=slot,
                scheduler_actor_id="msa-1",
                status="BOOKED_SIMULATED",
            )
        if outcome == "wrong-case":
            return SimpleNamespace(
                booking_id=booking,
                case_id="OTHER",
                option_id="OPT-1",
                slot_id=slot,
                scheduler_actor_id="msa-1",
                status="BOOKED_SIMULATED",
            )
        return None

    monkeypatch.setattr(pg_booking_readback, "recover_committed_eps_booking", recover)
    result = pg_booking_readback.readback_known_booking(
        lambda: pytest.fail("Unexpected direct connection"),
        case_id=CASE,
        option_id="OPT-1",
        slot_id=slot,
        authorization_id=auth,
        idempotency_key="known-commit",
        scheduler_actor_id="msa-1",
    )
    assert calls[0]["idempotency_key"] == "known-commit"
    assert calls[0]["case_id"] == CASE
    return result


def test_verified_fresh_connection_receipt_can_be_reported(monkeypatch):
    receipt = _read(monkeypatch, "present")
    assert receipt.state == "BOOKED_SIMULATED"
    assert receipt.verified is True
    assert receipt.booking_id is not None
    assert receipt.retry_commit_allowed is False


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (None, "NOT_FOUND_UNCONFIRMED"),
        (ConnectionError("db offline"), "RECOVERY_REQUIRED"),
        ("wrong-case", "RECOVERY_REQUIRED"),
    ],
)
def test_missing_unknown_and_cross_case_recovery_fail_closed(
    monkeypatch, outcome, expected
):
    receipt = _read(monkeypatch, outcome)
    assert receipt.state == expected
    assert receipt.verified is False
    assert receipt.booking_id is None
    assert receipt.retry_commit_allowed is False


def test_incomplete_identity_is_rejected_before_any_read(monkeypatch):
    def unexpected(*_args, **_kwargs):
        pytest.fail("Unexpected recovery")

    monkeypatch.setattr(
        pg_booking_readback, "recover_committed_eps_booking", unexpected
    )
    with pytest.raises(ValueError, match="Complete trusted"):
        pg_booking_readback.readback_known_booking(
            None,
            case_id=CASE,
            option_id="",
            slot_id=uuid4(),
            authorization_id=uuid4(),
            idempotency_key="original",
            scheduler_actor_id="msa-1",
        )
