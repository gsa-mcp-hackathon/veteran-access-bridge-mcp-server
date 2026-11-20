"""Offline orchestration acceptance: no demo identity or duplicate booking retries."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from veteran_access_bridge.adapters.pg_eps_recovery import EPSRecoveryReceipt
from veteran_access_bridge.adapters.pg_synthetic_eps_booking import EPSBookingRequest
from veteran_access_bridge.services import signed_scheduling_lifecycle as lifecycle
from veteran_access_bridge.services.pg_booking_readback import BookingReadback
from veteran_access_bridge.services.pg_governed_eps_commit import (
    BookingOutcome,
    BookingOutcomeReceipt,
)
from veteran_access_bridge.services.pg_governed_va_commit import (
    SCOPE,
    VABookingReceipt,
    VABookingRequest,
    _verified_booking_claims,
)
from veteran_access_bridge.services.private_va_booking_grant_issuer import (
    AuthenticatedService,
    EvaluatedBookingPolicy,
    PrivateVABookingGrantIssuer,
)

VA_TEST_SECRET = "isolated-test-only-booking-secret-" + "x" * 40


def _request():
    return EPSBookingRequest(
        case_id="DEMO-PC-5000999-001",
        option_id="OPT-1",
        slot_id=uuid4(),
        authorization_id=uuid4(),
        idempotency_key="original-booking-idempotency-key",
        scheduler_actor_id="msa-trusted-1",
    )


def _va_request():
    return VABookingRequest(
        case_id="DEMO-VA-PC-001",
        option_id="VA-PC-OPT-1",
        slot_id=uuid4(),
        idempotency_key="va-booking-1",
    )


def _grant_issuer(request, events):
    actor = AuthenticatedService(
        subject="trusted-vab-avery-host",
        authenticated=True,
        scope=SCOPE,
        case_ids=frozenset({request.case_id}),
    )
    policy = EvaluatedBookingPolicy(
        case_id=request.case_id,
        option_id=request.option_id,
        slot_id=request.slot_id,
        identity_verification_id="test-identity-evidence",
        identity_verification_expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=5),
        veteran_confirmation_id=uuid4(),
        policy_evidence_reference="test-policy-evidence",
        decision="ALLOW",
        human_review_required=False,
        synthetic=True,
        care_pathway="INTERNAL_VA",
    )

    def authenticate(assertion):
        events.append("authenticate")
        if assertion != "private-host-assertion":
            raise PermissionError("Host authentication failed")
        return actor

    def evaluate(passed_request, passed_actor):
        events.append("evaluate")
        assert passed_request == request
        assert passed_actor is actor
        return policy

    return PrivateVABookingGrantIssuer(
        signing_secret=VA_TEST_SECRET,
        authenticate_service=authenticate,
        evaluate_booking=evaluate,
    )


def _services():
    return lifecycle.TrustedSchedulingServices(
        connect=lambda: None, verifier_secret="test-signing-secret-32-bytes-long!"
    )


def test_rejects_weak_server_verifier_before_any_database_access():
    with pytest.raises(PermissionError):
        lifecycle.TrustedSchedulingServices(lambda: None, "short")


def test_persists_decision_through_existing_signed_service(monkeypatch):
    passed = []

    def persist(self, **kwargs):
        passed.append((self.connect, self.verifier_secret, kwargs))
        return "durable-receipt"

    monkeypatch.setattr(
        lifecycle.PrivateSyntheticSchedulingGateway, "record_decision", persist
    )
    services = _services()
    receipt = services.record_decision(
        assertion="independent-jwt",
        case_id="DEMO-PC-5000999-001",
        option_id="OPT-1",
        idempotency_key="confirmation-1",
        correlation_id="correlation-1",
        service_evidence_reference="verified-service-evidence",
    )
    assert receipt == "durable-receipt"
    assert passed[0][0] is services.connect
    assert passed[0][1] == services.verifier_secret
    assert passed[0][2]["assertion"] == "independent-jwt"


def test_internal_va_booking_requires_a_separate_protected_verifier():
    services = _services()
    request = VABookingRequest(
        case_id="DEMO-PC-001",
        option_id="VA-PC-OPT-1",
        slot_id=uuid4(),
        idempotency_key="va-booking-1",
    )

    with pytest.raises(PermissionError, match="internal VA booking verifier"):
        services.commit_internal_va_booking(
            assertion="trusted-host-assertion",
            request=request,
        )


def test_internal_va_application_facade_delegates_to_governed_services(monkeypatch):
    calls = []

    def commit(connect, *, assertion, verifier_secret, request):
        calls.append(("commit", connect, assertion, verifier_secret, request))
        return VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            "appointment-1",
            None,
            None,
            True,
        )

    def recover(connect, *, assertion, verifier_secret, request):
        calls.append(("recover", connect, assertion, verifier_secret, request))
        return VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            "appointment-1",
            None,
            None,
            True,
        )

    monkeypatch.setattr(lifecycle, "commit_internal_va_booking", commit)
    monkeypatch.setattr(lifecycle, "readback_internal_va_booking", recover)
    services = lifecycle.TrustedSchedulingServices(
        connect=lambda: None,
        verifier_secret="test-signing-secret-32-bytes-long!",
        va_booking_verifier_secret="separate-va-booking-secret-32-bytes!",
    )
    request = VABookingRequest(
        case_id="DEMO-PC-001",
        option_id="VA-PC-OPT-1",
        slot_id=uuid4(),
        idempotency_key="va-booking-1",
    )

    booked = services.commit_internal_va_booking(
        assertion="signed-service-assertion",
        request=request,
    )
    recovered = services.inspect_internal_va_booking(
        assertion="signed-service-assertion",
        request=request,
    )

    assert booked.verified is True
    assert recovered.appointment_id == booked.appointment_id
    assert [call[0] for call in calls] == ["commit", "recover"]
    assert all(call[1] is services.connect for call in calls)
    assert all(call[2] == "signed-service-assertion" for call in calls)
    assert all(call[3] == "separate-va-booking-secret-32-bytes!" for call in calls)


def test_autonomous_va_coordinator_issues_once_commits_once_and_reads_back(
    monkeypatch,
):
    request = _va_request()
    events = []
    appointment_id = "verified-appointment"
    services = lifecycle.TrustedSchedulingServices(
        connect=lambda: None,
        verifier_secret="test-signing-secret-32-bytes-long!",
        va_booking_verifier_secret=VA_TEST_SECRET,
    )

    def commit(_self, *, assertion, request):
        events.append("commit")
        claims = _verified_booking_claims(assertion, VA_TEST_SECRET, request)
        assert claims["sub"] == "trusted-vab-avery-host"
        return VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            appointment_id,
            None,
            None,
            True,
        )

    def inspect(_self, *, assertion, request):
        events.append("readback")
        _verified_booking_claims(assertion, VA_TEST_SECRET, request)
        return VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            appointment_id,
            None,
            None,
            True,
        )

    monkeypatch.setattr(
        lifecycle.TrustedSchedulingServices, "commit_internal_va_booking", commit
    )
    monkeypatch.setattr(
        lifecycle.TrustedSchedulingServices, "inspect_internal_va_booking", inspect
    )
    coordinator = lifecycle.TrustedPrimaryCareBookingCoordinator(
        services=services,
        grant_issuer=_grant_issuer(request, events),
    )

    receipt = coordinator.commit_and_verify(
        host_assertion="private-host-assertion",
        request=request,
    )

    assert receipt.state == "BOOKED_SIMULATED"
    assert receipt.verified is True
    assert not hasattr(receipt, "assertion")
    assert events == ["authenticate", "evaluate", "commit", "readback"]


def test_autonomous_va_coordinator_recovers_unknown_commit_without_resubmitting(
    monkeypatch,
):
    request = _va_request()
    events = []
    services = lifecycle.TrustedSchedulingServices(
        connect=lambda: None,
        verifier_secret="test-signing-secret-32-bytes-long!",
        va_booking_verifier_secret=VA_TEST_SECRET,
    )
    calls = {"commits": 0, "reads": 0}
    recovered = VABookingReceipt(
        "BOOKED_SIMULATED",
        request.case_id,
        "recovered-appointment",
        None,
        None,
        True,
    )

    def commit(_self, *, assertion, request):
        calls["commits"] += 1
        _verified_booking_claims(assertion, VA_TEST_SECRET, request)
        return VABookingReceipt(
            "RECOVERY_REQUIRED",
            request.case_id,
            None,
            None,
            None,
            False,
        )

    def inspect(_self, *, assertion, request):
        calls["reads"] += 1
        _verified_booking_claims(assertion, VA_TEST_SECRET, request)
        return recovered

    monkeypatch.setattr(
        lifecycle.TrustedSchedulingServices, "commit_internal_va_booking", commit
    )
    monkeypatch.setattr(
        lifecycle.TrustedSchedulingServices, "inspect_internal_va_booking", inspect
    )
    coordinator = lifecycle.TrustedPrimaryCareBookingCoordinator(
        services=services,
        grant_issuer=_grant_issuer(request, events),
    )

    receipt = coordinator.commit_and_verify(
        host_assertion="private-host-assertion",
        request=request,
    )

    assert receipt == recovered
    assert calls == {"commits": 1, "reads": 1}


def test_autonomous_va_coordinator_preserves_recovery_when_readback_raises(
    monkeypatch,
):
    request = _va_request()
    events = []
    services = lifecycle.TrustedSchedulingServices(
        connect=lambda: None,
        verifier_secret="test-signing-secret-32-bytes-long!",
        va_booking_verifier_secret=VA_TEST_SECRET,
    )
    commits = []

    def commit(_self, *, assertion, request):
        commits.append((assertion, request))
        return VABookingReceipt(
            "RECOVERY_REQUIRED",
            request.case_id,
            None,
            None,
            None,
            False,
        )

    def inspect(_self, *, assertion, request):
        raise PermissionError("Grant expired before recovery readback")

    monkeypatch.setattr(
        lifecycle.TrustedSchedulingServices, "commit_internal_va_booking", commit
    )
    monkeypatch.setattr(
        lifecycle.TrustedSchedulingServices, "inspect_internal_va_booking", inspect
    )
    coordinator = lifecycle.TrustedPrimaryCareBookingCoordinator(
        services=services,
        grant_issuer=_grant_issuer(request, events),
    )

    receipt = coordinator.commit_and_verify(
        host_assertion="private-host-assertion",
        request=request,
    )

    assert receipt.state == "RECOVERY_REQUIRED"
    assert receipt.verified is False
    assert len(commits) == 1
    assert events == ["authenticate", "evaluate"]


def test_autonomous_va_coordinator_fails_closed_before_commit_on_host_auth_error(
    monkeypatch,
):
    request = _va_request()
    events = []
    services = lifecycle.TrustedSchedulingServices(
        connect=lambda: None,
        verifier_secret="test-signing-secret-32-bytes-long!",
        va_booking_verifier_secret=VA_TEST_SECRET,
    )
    commits = []
    monkeypatch.setattr(
        lifecycle.TrustedSchedulingServices,
        "commit_internal_va_booking",
        lambda *_args, **_kwargs: commits.append("commit"),
    )
    coordinator = lifecycle.TrustedPrimaryCareBookingCoordinator(
        services=services,
        grant_issuer=_grant_issuer(request, events),
    )

    with pytest.raises(PermissionError, match="Host authentication failed"):
        coordinator.commit_and_verify(
            host_assertion="untrusted-host-assertion",
            request=request,
        )

    assert commits == []
    assert events == ["authenticate"]


def test_autonomous_va_coordinator_rejects_mismatched_fresh_readback(monkeypatch):
    request = _va_request()
    events = []
    services = lifecycle.TrustedSchedulingServices(
        connect=lambda: None,
        verifier_secret="test-signing-secret-32-bytes-long!",
        va_booking_verifier_secret=VA_TEST_SECRET,
    )
    monkeypatch.setattr(
        lifecycle.TrustedSchedulingServices,
        "commit_internal_va_booking",
        lambda *_args, **_kwargs: VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            "first-appointment",
            None,
            None,
            True,
        ),
    )
    monkeypatch.setattr(
        lifecycle.TrustedSchedulingServices,
        "inspect_internal_va_booking",
        lambda *_args, **_kwargs: VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            "different-appointment",
            None,
            None,
            True,
        ),
    )
    coordinator = lifecycle.TrustedPrimaryCareBookingCoordinator(
        services=services,
        grant_issuer=_grant_issuer(request, events),
    )

    receipt = coordinator.commit_and_verify(
        host_assertion="private-host-assertion",
        request=request,
    )

    assert receipt.state == "RECOVERY_REQUIRED"
    assert receipt.verified is False


def test_actor_decisions_delegate_to_private_gateway_with_expected_actor(
    monkeypatch,
):
    calls = []

    def capture(method_name):
        def call(_self, **kwargs):
            calls.append((method_name, kwargs))
            return method_name

        return call

    monkeypatch.setattr(
        lifecycle.PrivateSyntheticSchedulingGateway,
        "confirm_veteran_from_trusted_service",
        capture("confirm"),
    )
    monkeypatch.setattr(
        lifecycle.PrivateSyntheticSchedulingGateway,
        "record_veteran_response_from_trusted_service",
        capture("response"),
    )
    monkeypatch.setattr(
        lifecycle.PrivateSyntheticSchedulingGateway,
        "approve_scheduler_from_trusted_service",
        capture("approval"),
    )
    services = _services()

    common = {
        "assertion": "independent-assertion",
        "expected_actor_id": "trusted-actor",
        "case_id": "DEMO-PC-5000999-001",
        "option_id": "OPTION-1",
        "idempotency_key": "decision-1",
        "correlation_id": "correlation-1",
        "verified_evidence_reference": "verified-source",
    }
    assert services.confirm_veteran_from_trusted_service(**common) == "confirm"
    assert (
        services.record_veteran_response_from_trusted_service(**common, accepted=False)
        == "response"
    )
    assert (
        services.approve_scheduler_from_trusted_service(**common, accepted=True)
        == "approval"
    )
    assert [name for name, _ in calls] == ["confirm", "response", "approval"]
    assert calls[1][1]["accepted"] is False
    assert calls[2][1]["expected_actor_id"] == "trusted-actor"


def test_inspect_booking_uses_private_signed_recovery(monkeypatch):
    request = _request()
    booking_id = uuid4()
    passed = []

    def recover(self, **kwargs):
        passed.append((self.connect, kwargs))
        return EPSRecoveryReceipt(
            booking_id=booking_id,
            case_id=request.case_id,
            option_id=request.option_id,
            slot_id=request.slot_id,
            scheduler_actor_id=request.scheduler_actor_id,
            status="BOOKED_SIMULATED",
        )

    monkeypatch.setattr(lifecycle.PrivateSyntheticSchedulingGateway, "recover", recover)
    receipt = _services().inspect_booking(
        scheduler_assertion="independent-scheduler-assertion",
        request=request,
    )

    assert receipt == BookingReadback(
        state="BOOKED_SIMULATED",
        booking_id=str(booking_id),
        case_id=request.case_id,
        verified=True,
    )
    assert passed[0][1]["scheduler_assertion"] == "independent-scheduler-assertion"
    assert passed[0][1]["request"] is request


@pytest.mark.parametrize(
    "outcome,readback,expected",
    [
        (BookingOutcome.COMMITTED, True, "BOOKED_SIMULATED"),
        (BookingOutcome.COMMITTED, False, "RECOVERY_REQUIRED"),
        (BookingOutcome.RECOVERY_REQUIRED, True, "BOOKED_SIMULATED"),
        (BookingOutcome.RECOVERY_REQUIRED, False, "RECOVERY_REQUIRED"),
        (BookingOutcome.CONFLICT, True, "RECOVERY_REQUIRED"),
    ],
)
def test_commit_and_verify_never_resubmits_unknown_commit(
    monkeypatch, outcome, readback, expected
):
    calls = {"commits": 0, "reads": 0}
    booking_request = _request()
    booking_id = uuid4()

    def commit(_self, *, scheduler_assertion, request):
        assert scheduler_assertion == "independent-scheduler-jwt"
        assert request is booking_request
        calls["commits"] += 1
        return BookingOutcomeReceipt(outcome, str(booking_id), "test")

    def recover(_self, *, scheduler_assertion, request):
        assert scheduler_assertion == "independent-scheduler-jwt"
        assert request is booking_request
        calls["reads"] += 1
        if not readback:
            return None
        return EPSRecoveryReceipt(
            booking_id=booking_id,
            case_id=booking_request.case_id,
            option_id=booking_request.option_id,
            slot_id=booking_request.slot_id,
            scheduler_actor_id=booking_request.scheduler_actor_id,
            status="BOOKED_SIMULATED",
        )

    monkeypatch.setattr(lifecycle.PrivateSyntheticSchedulingGateway, "book", commit)
    monkeypatch.setattr(lifecycle.PrivateSyntheticSchedulingGateway, "recover", recover)
    receipt = _services().commit_and_verify(
        scheduler_assertion="independent-scheduler-jwt", request=booking_request
    )
    assert receipt.state == expected
    assert calls["commits"] == 1
    assert calls["reads"] == (0 if outcome == BookingOutcome.CONFLICT else 1)
    assert receipt.retry_commit_allowed is False
