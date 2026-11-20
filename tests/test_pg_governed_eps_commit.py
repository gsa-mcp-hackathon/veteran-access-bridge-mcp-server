"""Unit tests for governed EPS booking acknowledgment; no database writes."""

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from veteran_access_bridge.adapters.pg_synthetic_eps_booking import (
    EPSBookingRequest,
)
from veteran_access_bridge.services.pg_governed_eps_commit import (
    BookingOutcome,
    VerifiedSchedulerContext,
    commit_verified_synthetic_eps_booking,
)


def make_inputs():
    request = EPSBookingRequest(
        case_id="DEMO-CARD-5000335-001",
        option_id="test-option",
        slot_id=uuid4(),
        authorization_id=uuid4(),
        idempotency_key=uuid4().hex,
        scheduler_actor_id="verified-scheduler",
    )
    context = VerifiedSchedulerContext(
        actor_id="verified-scheduler",
        case_id=request.case_id,
        authenticated=True,
        authorized_scheduler=True,
    )
    return request, context


@pytest.mark.parametrize(
    "changes",
    [
        {"authenticated": False},
        {"authorized_scheduler": False},
        {"actor_id": "other"},
        {"case_id": "wrong-case"},
    ],
)
def test_unverified_context_fails_before_opening_connection(changes):
    request, context = make_inputs()
    context = VerifiedSchedulerContext(**{**vars(context), **changes})
    connect = Mock()
    with pytest.raises(PermissionError):
        commit_verified_synthetic_eps_booking(connect, context=context, request=request)
    connect.assert_not_called()


def test_commit_and_readback_required(monkeypatch):
    request, context = make_inputs()
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connect = Mock(return_value=connection)
    monkeypatch.setattr(
        "veteran_access_bridge.services.pg_governed_eps_commit."
        "commit_synthetic_eps_booking",
        Mock(return_value=uuid4()),
    )
    receipt = Mock(booking_id=uuid4())
    recover = Mock(return_value=receipt)
    monkeypatch.setattr(
        "veteran_access_bridge.services.pg_governed_eps_commit."
        "recover_committed_eps_booking",
        recover,
    )
    result = commit_verified_synthetic_eps_booking(
        connect, context=context, request=request
    )
    assert result.status == BookingOutcome.COMMITTED
    assert result.booking_id == str(receipt.booking_id)
    connection.commit.assert_called_once()
    connect.assert_called_once_with()
    recover.assert_called_once_with(
        connect,
        case_id=request.case_id,
        option_id=request.option_id,
        slot_id=request.slot_id,
        authorization_id=request.authorization_id,
        idempotency_key=request.idempotency_key,
        scheduler_actor_id=context.actor_id,
    )


def test_missing_readback_fails_closed(monkeypatch):
    request, context = make_inputs()
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(
        "veteran_access_bridge.services.pg_governed_eps_commit."
        "commit_synthetic_eps_booking",
        Mock(return_value=uuid4()),
    )
    monkeypatch.setattr(
        "veteran_access_bridge.services.pg_governed_eps_commit."
        "recover_committed_eps_booking",
        Mock(return_value=None),
    )
    result = commit_verified_synthetic_eps_booking(
        lambda: connection, context=context, request=request
    )
    assert result.status == BookingOutcome.RECOVERY_REQUIRED
    assert result.booking_id is None


def test_ambiguous_commit_does_not_retry(monkeypatch):
    request, context = make_inputs()
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.commit.side_effect = ConnectionError("ack lost")
    write = Mock(return_value=uuid4())
    monkeypatch.setattr(
        "veteran_access_bridge.services.pg_governed_eps_commit."
        "commit_synthetic_eps_booking",
        write,
    )
    result = commit_verified_synthetic_eps_booking(
        lambda: connection, context=context, request=request
    )
    assert result.status == BookingOutcome.RECOVERY_REQUIRED
    write.assert_called_once()
