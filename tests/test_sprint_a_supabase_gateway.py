"""Sprint A private gateway enforces signed identity before data operations."""

from unittest.mock import Mock
from uuid import uuid4

import pytest

from veteran_access_bridge.adapters.pg_synthetic_eps_booking import EPSBookingRequest
from veteran_access_bridge.services import supabase_scheduling_gateway as gateway

SECRET = "synthetic-internal-test-signing-secret-at-least-32-bytes"


def request(actor="scheduler"):
    return EPSBookingRequest(
        case_id="TEST-S6-CASE",
        option_id="TEST-OPTION",
        slot_id=uuid4(),
        authorization_id=uuid4(),
        idempotency_key="test-key",
        scheduler_actor_id=actor,
    )


def test_gateway_rejects_weak_secret_before_database_access():
    with pytest.raises(PermissionError):
        gateway.PrivateSyntheticSchedulingGateway(
            connect=Mock(side_effect=AssertionError("must not connect")),
            verifier_secret="short",
        )


def test_gateway_routes_signed_decision_without_exposing_credentials(monkeypatch):
    connect = Mock()
    service = gateway.PrivateSyntheticSchedulingGateway(
        connect=connect, verifier_secret=SECRET
    )
    write = Mock(return_value="receipt")
    monkeypatch.setattr(gateway, "persist_signed_scheduling_decision", write)
    result = service.record_decision(
        assertion="signed-test-token",
        case_id="case",
        option_id="option",
        idempotency_key="key",
        correlation_id="trace",
        service_evidence_reference="evidence",
        accepted=False,
    )
    assert result == "receipt"
    assert write.call_args.args[0] is connect
    assert write.call_args.kwargs["accepted"] is False
    connect.assert_not_called()


def test_gateway_delegates_booking_with_signed_assertion(monkeypatch):
    connect = Mock()
    service = gateway.PrivateSyntheticSchedulingGateway(
        connect=connect, verifier_secret=SECRET
    )
    booked = Mock(return_value="result")
    monkeypatch.setattr(gateway, "commit_with_signed_scheduler_assertion", booked)
    req = request()
    assert service.book(scheduler_assertion="signed", request=req) == "result"
    assert booked.call_args.kwargs["scheduler_assertion"] == "signed"
    assert booked.call_args.kwargs["request"] is req
    connect.assert_not_called()


def test_gateway_denies_actor_mismatch_before_recovery_query(monkeypatch):
    connect = Mock(side_effect=AssertionError("must not connect"))
    service = gateway.PrivateSyntheticSchedulingGateway(
        connect=connect, verifier_secret=SECRET
    )
    monkeypatch.setattr(
        gateway,
        "verify_scheduler_assertion",
        lambda *_args, **_kwargs: Mock(actor_id="other-scheduler"),
    )
    recover = Mock()
    monkeypatch.setattr(gateway, "recover_committed_eps_booking", recover)
    with pytest.raises(PermissionError, match="original scheduler identity"):
        service.recover(scheduler_assertion="signed", request=request())
    recover.assert_not_called()
    connect.assert_not_called()


def test_private_veteran_confirmation_requires_matching_signed_actor(monkeypatch):
    import jwt
    from datetime import datetime, timedelta, timezone
    from veteran_access_bridge.services.pg_signed_decisions import AUDIENCE, ISSUER

    service = gateway.PrivateSyntheticSchedulingGateway(
        connect=Mock(side_effect=AssertionError("database must not be used")),
        verifier_secret=SECRET,
    )
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "sub": "signed-veteran",
            "role": "VETERAN",
            "case_id": "test-case",
            "synthetic": True,
        },
        SECRET,
        algorithm="HS256",
    )
    write = Mock()
    monkeypatch.setattr(service.__class__, "record_decision", write)
    with pytest.raises(PermissionError, match="actor does not match"):
        service.confirm_veteran_from_trusted_service(
            assertion=token,
            expected_actor_id="spoofed-veteran",
            case_id="test-case",
            option_id="option",
            idempotency_key="key",
            correlation_id="correlation",
            verified_evidence_reference="evidence",
        )
    write.assert_not_called()


@pytest.mark.parametrize(
    "method,role,expected_actor,accepted",
    [
        ("record_veteran_response_from_trusted_service", "VETERAN", "veteran", False),
        ("approve_scheduler_from_trusted_service", "SCHEDULER", "scheduler", True),
    ],
)
def test_private_signed_decision_checks_actor_before_write(
    monkeypatch, method, role, expected_actor, accepted
):
    from veteran_access_bridge.services import pg_signed_decisions
    service = gateway.PrivateSyntheticSchedulingGateway(
        connect=Mock(side_effect=AssertionError("must not connect")),
        verifier_secret=SECRET,
    )
    monkeypatch.setattr(
        pg_signed_decisions,
        "_trusted_claims",
        lambda assertion, secret, case_id: {
            "role": role,
            "sub": expected_actor,
        },
    )
    write = Mock(return_value="signed-receipt")
    monkeypatch.setattr(service.__class__, "record_decision", write)
    params = dict(
        assertion="signed-token",
        expected_actor_id="imposter",
        case_id="case",
        option_id="option",
        idempotency_key="key",
        correlation_id="correlation",
        verified_evidence_reference="evidence",
        accepted=accepted,
    )
    with pytest.raises(PermissionError, match="actor does not match"):
        getattr(service, method)(**params)
    write.assert_not_called()
    params["expected_actor_id"] = expected_actor
    assert getattr(service, method)(**params) == "signed-receipt"
    assert write.call_args.kwargs["accepted"] is accepted
    assert write.call_args.kwargs["service_evidence_reference"] == "evidence"


def test_private_case_read_checks_signed_actor_before_database(monkeypatch):
    from veteran_access_bridge.mcp import durable_runtime
    from veteran_access_bridge.services import pg_signed_decisions

    connect = Mock(side_effect=AssertionError("unauthorized database access"))
    service = gateway.PrivateSyntheticSchedulingGateway(
        connect=connect, verifier_secret=SECRET
    )
    monkeypatch.setattr(
        pg_signed_decisions,
        "_trusted_claims",
        lambda assertion, secret, case_id: {
            "role": "VETERAN", "sub": "veteran-1", "case_id": case_id
        },
    )
    read = Mock(return_value={"case_id": "CASE-1", "found": True})
    monkeypatch.setattr(durable_runtime, "read_case_from_supabase", read)

    with pytest.raises(PermissionError, match="authorized case reader"):
        service.read_case_from_trusted_service(
            assertion="signed", expected_actor_id="veteran-2", case_id="CASE-1"
        )
    read.assert_not_called()
    connect.assert_not_called()

    result = service.read_case_from_trusted_service(
        assertion="signed",
        expected_actor_id="veteran-1",
        case_id="CASE-1",
        include_history=True,
    )
    assert result["found"] is True
    assert read.call_args.kwargs["connect"] is connect
    assert read.call_args.kwargs["include_history"] is True


def test_private_case_read_rejects_cross_case_token_before_database(monkeypatch):
    """A valid token for case A must not authorize case B."""
    from datetime import datetime, timedelta, timezone

    import jwt

    from veteran_access_bridge.mcp import durable_runtime
    from veteran_access_bridge.services.pg_signed_decisions import AUDIENCE, ISSUER

    connect = Mock(side_effect=AssertionError("must not access database"))
    service = gateway.PrivateSyntheticSchedulingGateway(
        connect=connect, verifier_secret=SECRET
    )
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "sub": "veteran-1",
            "role": "VETERAN",
            "case_id": "CASE-A",
            "synthetic": True,
        },
        SECRET,
        algorithm="HS256",
    )
    read = Mock(side_effect=AssertionError("must not read cross-case data"))
    monkeypatch.setattr(durable_runtime, "read_case_from_supabase", read)
    with pytest.raises((PermissionError, ValueError)):
        service.read_case_from_trusted_service(
            assertion=token, expected_actor_id="veteran-1", case_id="CASE-B"
        )
    read.assert_not_called()
    connect.assert_not_called()
