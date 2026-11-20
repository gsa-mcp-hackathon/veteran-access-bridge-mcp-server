"""Offline contract tests for private trusted-host policy-grant issuance.

No remote issuer, real VA, IBM, database, or MCP write access is used. The
injected callbacks are explicit test doubles, not production authentication.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from veteran_access_bridge.services.pg_governed_va_commit import (
    SCOPE,
    VABookingRequest,
    _verified_booking_claims,
)
from veteran_access_bridge.services.private_va_booking_grant_issuer import (
    AuthenticatedService,
    EvaluatedBookingPolicy,
    PrivateVABookingGrantIssuer,
)

SECRET = "isolated-test-only-signing-key-" + "x" * 40


def _request():
    return VABookingRequest(
        case_id="TEST-VA-PC-001",
        option_id="OPTION-1",
        slot_id=uuid4(),
        idempotency_key="book-key-1",
    )


def _evidence(request):
    return EvaluatedBookingPolicy(
        case_id=request.case_id,
        option_id=request.option_id,
        slot_id=request.slot_id,
        identity_verification_id="verified-identity-event-1",
        identity_verification_expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=5),
        veteran_confirmation_id=uuid4(),
        policy_evidence_reference="deterministic-policy-evaluation-1",
        decision="ALLOW",
        human_review_required=False,
        synthetic=True,
        care_pathway="INTERNAL_VA",
    )


def _make_issuer(request, *, actor=None, evidence=None, counter=None):
    actor = actor or AuthenticatedService(
        subject="trusted-vab-avery-host",
        authenticated=True,
        scope=SCOPE,
        case_ids=frozenset({request.case_id}),
    )
    evidence = evidence or _evidence(request)

    def authenticate(assertion):
        if counter is not None:
            counter.append("authenticate")
        if assertion != "host-only-test-credential":
            raise PermissionError("Host authentication failed")
        return actor

    def evaluate(passed_request, passed_actor):
        if counter is not None:
            counter.append("evaluate")
        assert passed_request == request
        assert passed_actor == actor
        return evidence

    return PrivateVABookingGrantIssuer(
        signing_secret=SECRET,
        authenticate_service=authenticate,
        evaluate_booking=evaluate,
    )


def test_trusted_service_grant_matches_private_booking_verifier():
    request = _request()
    token = _make_issuer(request).issue(
        host_assertion="host-only-test-credential",
        request=request,
    )
    claims = _verified_booking_claims(token, SECRET, request)
    assert claims["role"] == "SERVICE"
    assert claims["scope"] == SCOPE
    assert claims["policy_decision"] == "ALLOW"
    assert claims["human_review_required"] is False
    assert claims["case_id"] == request.case_id
    assert claims["slot_id"] == str(request.slot_id)


def test_grant_never_evaluates_policy_without_authenticated_service():
    request = _request()
    events = []
    issuer = _make_issuer(request, counter=events)
    with pytest.raises(PermissionError, match="Host authentication failed"):
        issuer.issue(host_assertion="untrusted", request=request)
    assert events == ["authenticate"]


@pytest.mark.parametrize(
    "change",
    [
        {"decision": "DENY"},
        {"decision": "REVIEW"},
        {"human_review_required": True},
        {"synthetic": False},
        {"care_pathway": "COMMUNITY_CARE"},
        {"case_id": "ANOTHER-CASE"},
        {"option_id": "OTHER-OPTION"},
        {"slot_id": uuid4()},
        {"identity_verification_id": ""},
        {
            "identity_verification_expires_at": datetime.now(timezone.utc)
            - timedelta(seconds=1)
        },
        {"policy_evidence_reference": ""},
    ],
)
def test_mismatched_or_denied_policy_never_issues_token(change):
    request = _request()
    issuer = _make_issuer(request, evidence=replace(_evidence(request), **change))
    with pytest.raises(PermissionError, match="Current verified"):
        issuer.issue(host_assertion="host-only-test-credential", request=request)


@pytest.mark.parametrize(
    "actor",
    [
        AuthenticatedService("unverified", False, SCOPE),
        AuthenticatedService("insufficient-scope", True, "va_primary_care:read"),
        AuthenticatedService("", True, SCOPE),
        AuthenticatedService("wrong-case", True, SCOPE, frozenset({"ANOTHER-CASE"})),
    ],
)
def test_untrusted_or_underprivileged_service_is_rejected(actor):
    request = _request()
    issuer = _make_issuer(request, actor=actor)
    with pytest.raises(PermissionError, match="Independently authenticated"):
        issuer.issue(host_assertion="host-only-test-credential", request=request)


def test_issuer_requires_real_protected_adapters_and_strong_key():
    with pytest.raises(PermissionError):
        PrivateVABookingGrantIssuer(
            signing_secret="short",
            authenticate_service=lambda _: None,
            evaluate_booking=lambda *_: None,
        )
    with pytest.raises(PermissionError):
        PrivateVABookingGrantIssuer(
            signing_secret=SECRET,
            authenticate_service=None,
            evaluate_booking=None,
        )


def test_issuer_is_not_registered_as_public_mcp_tool():
    import inspect

    from veteran_access_bridge.services import private_va_booking_grant_issuer

    source = inspect.getsource(private_va_booking_grant_issuer)
    assert "@mcp.tool" not in source
    assert "@app.post" not in source
    assert "jwt.encode(" in source  # Only this private trusted-host service may issue.


def test_voice_binding_survives_grant_signature():
    request = _request()
    evidence = replace(_evidence(request), voice_session_id="vs-authenticated-call")
    token = _make_issuer(request, evidence=evidence).issue(
        host_assertion="host-only-test-credential",
        request=request,
    )
    assert (
        _verified_booking_claims(token, SECRET, request)["voice_session_id"]
        == "vs-authenticated-call"
    )


@pytest.mark.parametrize("call_id", ["", " ", " vs-call", "x" * 129, 42, "vs\ncall"])
def test_grant_rejects_invalid_voice_binding(call_id):
    request = _request()
    evidence = replace(_evidence(request), voice_session_id=call_id)
    with pytest.raises(PermissionError, match="voice session"):
        _make_issuer(request, evidence=evidence).issue(
            host_assertion="host-only-test-credential",
            request=request,
        )
