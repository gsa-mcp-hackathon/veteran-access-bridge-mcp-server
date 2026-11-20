"""Signed scheduler verifier must fail closed on spoofed/expired claims."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from veteran_access_bridge.services.scheduler_assertions import (
    AUDIENCE,
    ISSUER,
    verify_scheduler_assertion,
)

SECRET = "local-test-secret-with-at-least-32-bytes-long"
CASE = "DEMO-CARD-5000335-001"


def make_token(**changes):
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "scheduler-001",
        "role": "SCHEDULER",
        "case_id": CASE,
        "synthetic": True,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(changes)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def test_valid_scoped_assertion():
    context = verify_scheduler_assertion(
        make_token(), signing_secret=SECRET, required_case_id=CASE
    )
    assert context.authenticated
    assert context.authorized_scheduler
    assert context.actor_id == "scheduler-001"
    assert context.case_id == CASE


@pytest.mark.parametrize(
    "changes",
    [
        {"role": "VETERAN"},
        {"case_id": "OTHER-CASE"},
        {"synthetic": False},
        {"iss": "untrusted"},
        {"aud": "other-audience"},
        {"sub": ""},
        {"exp": datetime.now(timezone.utc) - timedelta(seconds=5)},
    ],
)
def test_wrong_claims_rejected(changes):
    with pytest.raises(PermissionError):
        verify_scheduler_assertion(
            make_token(**changes), signing_secret=SECRET, required_case_id=CASE
        )


def test_bad_signing_key_and_tampering_rejected():
    with pytest.raises(PermissionError):
        verify_scheduler_assertion(
            make_token(), signing_secret="short", required_case_id=CASE
        )
    attacker_token = jwt.encode(
        {
            "sub": "scheduler-001",
            "role": "SCHEDULER",
            "case_id": CASE,
            "synthetic": True,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "attacker-signing-key-at-least-32-bytes",
        algorithm="HS256",
    )
    with pytest.raises(PermissionError):
        verify_scheduler_assertion(
            attacker_token, signing_secret=SECRET, required_case_id=CASE
        )


def test_signed_commit_boundary_rejects_bad_actor_before_database():
    from unittest.mock import Mock
    from uuid import uuid4

    from veteran_access_bridge.adapters.pg_synthetic_eps_booking import (
        EPSBookingRequest,
    )
    from veteran_access_bridge.services.pg_governed_eps_commit import (
        commit_with_signed_scheduler_assertion,
    )

    request = EPSBookingRequest(
        case_id=CASE,
        option_id="test",
        slot_id=uuid4(),
        authorization_id=uuid4(),
        scheduler_actor_id="scheduler-001",
        idempotency_key=uuid4().hex,
    )
    connect = Mock()
    with pytest.raises(PermissionError):
        commit_with_signed_scheduler_assertion(
            connect,
            scheduler_assertion=make_token(role="VETERAN"),
            verifier_secret=SECRET,
            request=request,
        )
    connect.assert_not_called()


def test_signed_commit_boundary_rejects_cross_actor_before_database():
    from unittest.mock import Mock
    from uuid import uuid4

    from veteran_access_bridge.adapters.pg_synthetic_eps_booking import (
        EPSBookingRequest,
    )
    from veteran_access_bridge.services.pg_governed_eps_commit import (
        commit_with_signed_scheduler_assertion,
    )

    request = EPSBookingRequest(
        case_id=CASE,
        option_id="test",
        slot_id=uuid4(),
        authorization_id=uuid4(),
        scheduler_actor_id="someone-else",
        idempotency_key=uuid4().hex,
    )
    connect = Mock()
    with pytest.raises(PermissionError):
        commit_with_signed_scheduler_assertion(
            connect,
            scheduler_assertion=make_token(),
            verifier_secret=SECRET,
            request=request,
        )
    connect.assert_not_called()
