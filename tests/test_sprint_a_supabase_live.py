"""Opt-in real Python/Supabase synthetic scheduling acceptance matrix.

NEVER run against the operational vab schema or without a dedicated test login.
No app, MCP or VA network calls. This suite creates synthetic records only in
vab_test, verifies governed transactions and cleans up by exact random IDs.

Run after protected test-role credential provisioning:
VAB_SUPABASE_PROJECT_REF=wntbjxjeaxngjrffmnis
VAB_SUPABASE_TEST_MODE=true
VAB_ENABLE_SUPABASE_TEST_WRITES=true
VAB_RUN_SPRINT_A_DB_ACCEPTANCE=true
VAB_SUPABASE_TEST_DATABASE_URL=<trusted-server-secret>
uv run --extra dev --with 'psycopg[binary]>=3.2,<4' \
  pytest -q tests/test_sprint_a_supabase_live.py
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4, uuid5

import jwt
import pytest

from veteran_access_bridge.adapters.pg_synthetic_eps_booking import EPSBookingRequest
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
)
from veteran_access_bridge.adapters.synthetic_ids import VAB_SYNTHETIC_NAMESPACE
from veteran_access_bridge.services.pg_governed_eps_commit import BookingOutcome
from veteran_access_bridge.services.pg_provider_reconciliation import (
    AUDIENCE as PROVIDER_AUDIENCE,
)
from veteran_access_bridge.services.pg_provider_reconciliation import (
    ISSUER as PROVIDER_ISSUER,
)
from veteran_access_bridge.services.pg_provider_reconciliation import (
    read_test_provider_status,
    record_signed_test_provider_status,
)
from veteran_access_bridge.services.pg_signed_decisions import AUDIENCE, ISSUER
from veteran_access_bridge.services.supabase_scheduling_gateway import (
    PrivateSyntheticSchedulingGateway,
)
from veteran_access_bridge.services.trusted_primary_care import (
    HOST_ASSERTION_EVENT_TYPE,
    PostgresHostAssertionReplayGuard,
)

REQUIRED_OPT_IN = (
    os.getenv("VAB_RUN_SPRINT_A_DB_ACCEPTANCE") == "true"
    and os.getenv("VAB_SUPABASE_TEST_MODE") == "true"
    and os.getenv("VAB_ENABLE_SUPABASE_TEST_WRITES") == "true"
)
pytestmark = pytest.mark.skipif(
    not REQUIRED_OPT_IN, reason="Opt-in isolated Supabase test acceptance disabled"
)


def test_host_assertion_replay_concurrent_and_exact_cleanup():
    """Race one isolated assertion without creating a synthetic patient."""
    issuer = "urn:vab:test-replay"
    subject = "test-host-" + uuid4().hex
    token_id = uuid4().hex
    encoded = json.dumps([issuer, subject, token_id], separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    correlation_id = "trusted-host-assertion:" + digest
    event_id = uuid5(VAB_SYNTHETIC_NAMESPACE, correlation_id)
    connect = connect_private_supabase_test_scheduling
    guard = PostgresHostAssertionReplayGuard(connect)
    barrier = Barrier(2, timeout=30)
    expires_at = int(datetime.now(timezone.utc).timestamp()) + 240

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM vab_test.audit_event WHERE event_id=%s",
                (event_id,),
            )
            if cur.fetchone()[0]:
                raise AssertionError("Replay test event ID already exists")

    def consume():
        barrier.wait()
        try:
            guard.consume(
                issuer=issuer,
                subject=subject,
                token_id=token_id,
                expires_at=expires_at,
            )
        except PermissionError as exc:
            if str(exc) != "Host assertion expired or already consumed":
                raise
            return "rejected"
        return "consumed"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: consume(), range(2)))
        assert sorted(results) == ["consumed", "rejected"]
        with pytest.raises(PermissionError, match="already consumed"):
            PostgresHostAssertionReplayGuard(connect).consume(
                issuer=issuer,
                subject=subject,
                token_id=token_id,
                expires_at=expires_at,
            )
    finally:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT actor,event_type,correlation_id,details "
                    "FROM vab_test.audit_event WHERE event_id=%s FOR UPDATE",
                    (event_id,),
                )
                row = cur.fetchone()
                if row is not None:
                    expected = (
                        subject,
                        HOST_ASSERTION_EVENT_TYPE,
                        correlation_id,
                        {"synthetic": True, "assertion_digest": digest},
                    )
                    if row != expected:
                        raise AssertionError("Replay cleanup ownership mismatch")
                    cur.execute(
                        "DELETE FROM vab_test.audit_event WHERE event_id=%s "
                        "AND actor=%s AND event_type=%s AND correlation_id=%s",
                        (event_id, subject, HOST_ASSERTION_EVENT_TYPE, correlation_id),
                    )
                    if cur.rowcount != 1:
                        raise AssertionError("Replay exact-ID cleanup failed")
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM vab_test.audit_event WHERE event_id=%s",
                    (event_id,),
                )
                if cur.fetchone()[0]:
                    raise AssertionError("Replay event remains after cleanup")


def actor_token(role: str, actor: str, case_id: str, secret: str) -> str:
    import jwt

    issued = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": actor,
            "role": role,
            "case_id": case_id,
            "synthetic": True,
            "iat": issued,
            "exp": issued + timedelta(minutes=5),
            "iss": ISSUER,
            "aud": AUDIENCE,
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture
def synthetic_cohort():
    """Committed synthetic fixture, always cleaned by exact test-only IDs."""
    if not REQUIRED_OPT_IN:
        pytest.skip("Test-only credential opt-in is missing")
    suffix = uuid4().hex
    patient_id, request_id, slot_id = uuid4(), uuid4(), uuid4()
    referral_id, authorization_id = uuid4(), uuid4()
    case_id = "TEST-S6-" + suffix
    option_id = "OPTION-" + suffix
    source_id = "test-sprint-a-" + suffix
    actor = "test-scheduler-" + suffix
    secret = secrets.token_urlsafe(48)
    evidence_ref = source_id
    bindings = {
        "slot_bindings": {
            str(slot_id): {
                "case_id": case_id,
                "option_id": option_id,
                "initial_consult_eligible": True,
            }
        }
    }
    auth_evidence = {
        "synthetic": True,
        "provenance_ref": source_id,
        "case_id": case_id,
        "option_id": option_id,
        "slot_id": str(slot_id),
        "provider_id": "test-provider",
    }
    connect = connect_private_supabase_test_scheduling
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO vab_test.data_source "
                "(source_id,source_kind,description,provenance) "
                "VALUES (%s,'synthetic_fixture','Sprint A test',%s::jsonb)",
                (source_id, json.dumps(bindings)),
            )
            cur.execute(
                "INSERT INTO vab_test.patient "
                "(patient_id,demo_patient_key,source_id) VALUES (%s,%s,%s)",
                (patient_id, "test-patient-" + suffix, source_id),
            )
            cur.execute(
                "INSERT INTO vab_test.appointment_request "
                "(request_id,patient_id,requested_service,request_kind,status) "
                "VALUES (%s,%s,'PRIMARY CARE','PRIMARY_CARE','OPEN')",
                (request_id, patient_id),
            )
            cur.execute(
                "INSERT INTO vab_test.scheduling_case_link "
                "(case_id,request_id,source_request_id,synthetic) "
                "VALUES (%s,%s,%s,true)",
                (case_id, request_id, "test-request-" + suffix),
            )
            cur.execute(
                "INSERT INTO vab_test.slot "
                "(slot_id,channel,provider_id,begins_at,ends_at,status,source_id,"
                "verified_at) "
                "VALUES (%s,'EPS','test-provider',now()+interval '2 days',"
                "now()+interval '2 days 30 minutes','AVAILABLE',%s,now())",
                (slot_id, source_id),
            )
            cur.execute(
                "INSERT INTO vab_test.referral "
                "(referral_id,patient_id,status,evidence) "
                "VALUES (%s,%s,'ACTIVE',%s::jsonb)",
                (referral_id, patient_id, json.dumps({"case_id": case_id})),
            )
            cur.execute(
                "INSERT INTO vab_test.authorization "
                "(authorization_id,referral_id,status,valid_from,valid_until,"
                "service_scope,source_id,evidence) "
                "VALUES (%s,%s,'ACTIVE',now()-interval '1 hour',"
                "now()+interval '1 day','PRIMARY CARE',%s,%s::jsonb)",
                (authorization_id, referral_id, source_id, json.dumps(auth_evidence)),
            )
        conn.commit()

    data = {
        "case_id": case_id,
        "option_id": option_id,
        "patient_id": patient_id,
        "request_id": request_id,
        "slot_id": slot_id,
        "referral_id": referral_id,
        "authorization_id": authorization_id,
        "source_id": source_id,
        "actor": actor,
        "secret": secret,
        "evidence_ref": evidence_ref,
        "connect": connect,
        "gateway": PrivateSyntheticSchedulingGateway(connect, secret),
        "suffix": suffix,
    }
    try:
        yield data
    finally:
        # Unique test-only keys, strict ordering under foreign keys.
        # Never accept a user-provided schema or cleanup scope.
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM vab_test.audit_event WHERE source_id=%s",
                    (source_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.appointment WHERE request_id=%s",
                    (request_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.scheduling_transition WHERE case_id=%s",
                    (case_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.scheduling_decision WHERE case_id=%s",
                    (case_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.authorization WHERE authorization_id=%s",
                    (authorization_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.referral WHERE referral_id=%s",
                    (referral_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.slot WHERE slot_id=%s",
                    (slot_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.scheduling_case_link WHERE case_id=%s",
                    (case_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.appointment_request WHERE request_id=%s",
                    (request_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.patient WHERE patient_id=%s",
                    (patient_id,),
                )
                cur.execute(
                    "DELETE FROM vab_test.data_source WHERE source_id=%s",
                    (source_id,),
                )
            conn.commit()
        cleanup_checks = (
            (
                "SELECT count(*) FROM vab_test.audit_event WHERE source_id=%s",
                (source_id,),
            ),
            (
                "SELECT count(*) FROM vab_test.appointment WHERE request_id=%s",
                (request_id,),
            ),
            (
                "SELECT count(*) FROM vab_test.scheduling_transition WHERE case_id=%s",
                (case_id,),
            ),
            (
                "SELECT count(*) FROM vab_test.scheduling_decision WHERE case_id=%s",
                (case_id,),
            ),
            (
                "SELECT count(*) FROM vab_test.authorization WHERE authorization_id=%s",
                (authorization_id,),
            ),
            (
                "SELECT count(*) FROM vab_test.referral WHERE referral_id=%s",
                (referral_id,),
            ),
            ("SELECT count(*) FROM vab_test.slot WHERE slot_id=%s", (slot_id,)),
            (
                "SELECT count(*) FROM vab_test.scheduling_case_link WHERE case_id=%s",
                (case_id,),
            ),
            (
                "SELECT count(*) FROM vab_test.appointment_request WHERE request_id=%s",
                (request_id,),
            ),
            (
                "SELECT count(*) FROM vab_test.patient WHERE patient_id=%s",
                (patient_id,),
            ),
            (
                "SELECT count(*) FROM vab_test.data_source WHERE source_id=%s",
                (source_id,),
            ),
        )
        with connect() as conn:
            with conn.cursor() as cur:
                for sql, params in cleanup_checks:
                    cur.execute(sql, params)
                    remaining = cur.fetchone()[0]
                    if remaining:
                        raise AssertionError(
                            f"Exact-ID cleanup left {remaining} rows for {params[0]}"
                        )


def decision(cohort, role: str, *, accepted=True):
    return cohort["gateway"].record_decision(
        assertion=actor_token(
            role,
            cohort["actor"] if role == "SCHEDULER" else "test-veteran",
            cohort["case_id"],
            cohort["secret"],
        ),
        case_id=cohort["case_id"],
        option_id=cohort["option_id"],
        idempotency_key=f"test-{role}-{accepted}-{uuid4().hex}",
        correlation_id=f"test-correlation-{cohort['suffix']}",
        service_evidence_reference=cohort["evidence_ref"],
        accepted=accepted,
    )


def request(cohort, *, key=None):
    return EPSBookingRequest(
        case_id=cohort["case_id"],
        option_id=cohort["option_id"],
        slot_id=cohort["slot_id"],
        authorization_id=cohort["authorization_id"],
        idempotency_key=key or ("test-booking-" + uuid4().hex),
        scheduler_actor_id=cohort["actor"],
    )


def book(cohort, req):
    return cohort["gateway"].book(
        scheduler_assertion=actor_token(
            "SCHEDULER", cohort["actor"], cohort["case_id"], cohort["secret"]
        ),
        request=req,
    )


def test_primary_care_signed_commit_readback_and_idempotency(synthetic_cohort):
    c = synthetic_cohort
    veteran = decision(c, "VETERAN")
    scheduler = decision(c, "SCHEDULER")
    assert veteran.status == scheduler.status == "ACCEPTED"
    req = request(c)
    first = book(c, req)
    assert first.status == BookingOutcome.COMMITTED
    assert first.booking_id
    replay = book(c, req)
    assert replay.status == BookingOutcome.COMMITTED
    assert replay.booking_id == first.booking_id
    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM vab_test.appointment WHERE request_id=%s",
                (c["request_id"],),
            )
            assert cur.fetchone()[0] == 1
            cur.execute(
                "SELECT count(*) FROM vab_test.audit_event "
                "WHERE event_type='BOOKED_SIMULATED' AND source_id=%s",
                (c["source_id"],),
            )
            assert cur.fetchone()[0] == 1
    with pytest.raises(ValueError, match="already has an active"):
        book(c, request(c))


def test_new_booking_denied_after_veteran_rejection(synthetic_cohort):
    c = synthetic_cohort
    decision(c, "VETERAN")
    decision(c, "SCHEDULER")
    decision(c, "VETERAN", accepted=False)
    with pytest.raises(ValueError, match="Current VETERAN_CONFIRMED"):
        book(c, request(c))


def test_scheduler_rejected_or_missing_approval_denies_booking(synthetic_cohort):
    c = synthetic_cohort
    decision(c, "VETERAN")
    decision(c, "SCHEDULER", accepted=False)
    with pytest.raises(ValueError, match="Current SCHEDULER_APPROVED"):
        book(c, request(c))


def test_expired_authorization_blocks_fresh_booking(synthetic_cohort):
    c = synthetic_cohort
    decision(c, "VETERAN")
    decision(c, "SCHEDULER")
    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vab_test.authorization SET valid_until=now()-interval '1 day' "
                "WHERE authorization_id=%s",
                (c["authorization_id"],),
            )
        conn.commit()
    with pytest.raises(ValueError, match="validity window"):
        book(c, request(c))


def test_existing_committed_booking_survives_later_expiration(synthetic_cohort):
    c = synthetic_cohort
    decision(c, "VETERAN")
    decision(c, "SCHEDULER")
    req = request(c)
    original = book(c, req)
    assert original.status == BookingOutcome.COMMITTED
    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vab_test.authorization SET valid_until=now()-interval '1 day' "
                "WHERE authorization_id=%s",
                (c["authorization_id"],),
            )
            cur.execute(
                "UPDATE vab_test.slot SET verified_at=now()-interval '1 day' "
                "WHERE slot_id=%s",
                (c["slot_id"],),
            )
        conn.commit()
    assert book(c, req).booking_id == original.booking_id


def test_audit_write_error_rolls_back_slot_and_appointment(
    synthetic_cohort, monkeypatch
):
    from veteran_access_bridge.adapters import pg_synthetic_eps_booking

    c = synthetic_cohort
    decision(c, "VETERAN")
    decision(c, "SCHEDULER")
    original_execute = pg_synthetic_eps_booking.execute_scheduling_sql

    def fail_audit(cur, schema, statement, params=None):
        if statement.startswith("INSERT INTO vab.audit_event"):
            raise RuntimeError("synthetic forced audit insert failure")
        return original_execute(cur, schema, statement, params)

    monkeypatch.setattr(pg_synthetic_eps_booking, "execute_scheduling_sql", fail_audit)
    result = book(c, request(c))
    assert result.status == BookingOutcome.RECOVERY_REQUIRED
    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM vab_test.slot WHERE slot_id=%s", (c["slot_id"],)
            )
            assert cur.fetchone()[0] == "AVAILABLE"
            cur.execute(
                "SELECT count(*) FROM vab_test.appointment WHERE request_id=%s",
                (c["request_id"],),
            )
            assert cur.fetchone()[0] == 0


def test_wrong_scheduler_signature_rejected_before_db(synthetic_cohort):
    c = synthetic_cohort
    req = request(c)
    wrong_token = actor_token("VETERAN", "test-veteran", c["case_id"], c["secret"])
    with pytest.raises(PermissionError):
        c["gateway"].book(
            scheduler_assertion=wrong_token,
            request=req,
        )


def test_latest_scheduler_rejection_blocks_new_booking(synthetic_cohort):
    c = synthetic_cohort
    decision(c, "VETERAN")
    decision(c, "SCHEDULER")
    decision(c, "SCHEDULER", accepted=False)
    with pytest.raises(ValueError, match="Current SCHEDULER_APPROVED"):
        book(c, request(c))


def test_non_initial_consult_slot_blocked_at_commit(synthetic_cohort):
    c = synthetic_cohort
    decision(c, "VETERAN")
    decision(c, "SCHEDULER")
    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vab_test.data_source SET provenance="
                "jsonb_set(provenance, "
                "ARRAY['slot_bindings',%s,'initial_consult_eligible'],"
                "'false'::jsonb) WHERE source_id=%s",
                (str(c["slot_id"]), c["source_id"]),
            )
        conn.commit()
    with pytest.raises(ValueError, match="eligibility denied"):
        book(c, request(c))


def test_immutable_booking_evidence_required_for_exact_replay(synthetic_cohort):
    c = synthetic_cohort
    decision(c, "VETERAN")
    decision(c, "SCHEDULER")
    req = request(c)
    assert book(c, req).status == BookingOutcome.COMMITTED
    # Deliberately corrupt only this disposable synthetic test case.
    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM vab_test.audit_event "
                "WHERE source_id=%s AND event_type='BOOKED_SIMULATED'",
                (c["source_id"],),
            )
        conn.commit()
    with pytest.raises(ValueError, match="missing matching atomic evidence"):
        book(c, req)


def test_specialty_request_cannot_use_primary_care_commit(synthetic_cohort):
    c = synthetic_cohort
    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE vab_test.appointment_request SET request_kind='SPECIALTY' "
                "WHERE request_id=%s",
                (c["request_id"],),
            )
        conn.commit()
    with pytest.raises(ValueError, match="Only primary-care"):
        book(c, request(c))


def test_dedicated_test_role_cannot_query_operational_kb(synthetic_cohort):
    import psycopg

    c = synthetic_cohort
    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT has_schema_privilege(current_user,'vab','USAGE')")
            assert cur.fetchone()[0] is False

            # Access to the operational KB must be denied.
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with conn.transaction():
                    cur.execute("SELECT 1 FROM vab.kb_article LIMIT 1")


def test_signed_private_case_read_and_actor_isolation(synthetic_cohort, monkeypatch):

    c = synthetic_cohort
    monkeypatch.setenv("VAB_SCHEDULING_RUNTIME_MODE", "supabase_test")
    assertion = actor_token("VETERAN", "test-veteran", c["case_id"], c["secret"])
    with pytest.raises(PermissionError, match="authorized case reader"):
        c["gateway"].read_case_from_trusted_service(
            assertion=assertion,
            expected_actor_id="different-veteran",
            case_id=c["case_id"],
        )
    record = c["gateway"].read_case_from_trusted_service(
        assertion=assertion,
        expected_actor_id="test-veteran",
        case_id=c["case_id"],
        include_history=True,
    )
    assert record["found"] is True
    assert record["request_id"] == str(c["request_id"])
    assert record["persistence"] == "supabase_test"
    assert record["event_history"] == []


def test_signed_scheduler_replay_after_veteran_decline(synthetic_cohort):
    """Historical approval receipt survives later decline without new writes."""
    c = synthetic_cohort
    decision(c, "VETERAN")
    key = "test-replay-scheduler-" + c["suffix"]
    assertion = actor_token("SCHEDULER", c["actor"], c["case_id"], c["secret"])
    kwargs = dict(
        assertion=assertion,
        expected_actor_id=c["actor"],
        case_id=c["case_id"],
        option_id=c["option_id"],
        idempotency_key=key,
        correlation_id="test-correlation-" + c["suffix"],
        verified_evidence_reference=c["evidence_ref"],
        accepted=True,
    )
    original = c["gateway"].approve_scheduler_from_trusted_service(**kwargs)
    assert original.idempotent_replay is False
    decision(c, "VETERAN", accepted=False)
    replay = c["gateway"].approve_scheduler_from_trusted_service(**kwargs)
    assert replay.idempotent_replay is True
    assert replay.decision_id == original.decision_id
    assert replay.transition_id == original.transition_id
    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM vab_test.scheduling_decision "
                "WHERE idempotency_key=%s",
                (key,),
            )
            assert cur.fetchone()[0] == 1
    with pytest.raises(ValueError, match="Current VETERAN_CONFIRMED"):
        book(c, request(c))


def test_integrated_restart_booking_provider_reconciliation_and_cleanup(
    synthetic_cohort, monkeypatch
):
    c = synthetic_cohort
    monkeypatch.setenv("VAB_SCHEDULING_RUNTIME_MODE", "supabase_test")
    veteran_assertion = actor_token(
        "VETERAN", "test-veteran", c["case_id"], c["secret"]
    )
    scheduler_assertion = actor_token(
        "SCHEDULER", c["actor"], c["case_id"], c["secret"]
    )
    decision_kwargs = {
        "case_id": c["case_id"],
        "option_id": c["option_id"],
        "idempotency_key": "test-integrated-veteran-" + c["suffix"],
        "correlation_id": "test-integrated-" + c["suffix"],
        "verified_evidence_reference": c["evidence_ref"],
    }

    with pytest.raises(PermissionError, match="actor"):
        c["gateway"].confirm_veteran_from_trusted_service(
            assertion=veteran_assertion,
            expected_actor_id="imposter",
            **decision_kwargs,
        )
    veteran = c["gateway"].confirm_veteran_from_trusted_service(
        assertion=veteran_assertion,
        expected_actor_id="test-veteran",
        **decision_kwargs,
    )
    scheduler = c["gateway"].approve_scheduler_from_trusted_service(
        assertion=scheduler_assertion,
        expected_actor_id=c["actor"],
        case_id=c["case_id"],
        option_id=c["option_id"],
        idempotency_key="test-integrated-scheduler-" + c["suffix"],
        correlation_id="test-integrated-" + c["suffix"],
        verified_evidence_reference=c["evidence_ref"],
        accepted=True,
    )
    assert veteran.status == scheduler.status == "ACCEPTED"

    req = request(c, key="test-integrated-booking-" + c["suffix"])
    first_instance = PrivateSyntheticSchedulingGateway(c["connect"], c["secret"])
    booked = first_instance.book(scheduler_assertion=scheduler_assertion, request=req)
    assert booked.status == BookingOutcome.COMMITTED
    assert booked.booking_id

    restarted_instance = PrivateSyntheticSchedulingGateway(c["connect"], c["secret"])
    recovered = restarted_instance.recover(
        scheduler_assertion=scheduler_assertion, request=req
    )
    assert recovered is not None
    assert str(recovered.booking_id) == booked.booking_id
    projection = restarted_instance.read_case_from_trusted_service(
        assertion=veteran_assertion,
        expected_actor_id="test-veteran",
        case_id=c["case_id"],
        include_history=True,
    )
    assert projection["current_state"] == "BOOKED_SIMULATED"
    assert projection["booking_id"] == booked.booking_id
    assert projection["history_order_authoritative"] is False

    def provider_assertion(status, event_key):
        issued = datetime.now(timezone.utc)
        return jwt.encode(
            {
                "sub": "test-provider-actor",
                "role": "PROVIDER",
                "case_id": c["case_id"],
                "appointment_id": booked.booking_id,
                "provider_id": "test-provider",
                "status": status,
                "event_key": event_key,
                "synthetic": True,
                "iss": PROVIDER_ISSUER,
                "aud": PROVIDER_AUDIENCE,
                "iat": issued,
                "exp": issued + timedelta(minutes=5),
            },
            c["secret"],
            algorithm="HS256",
        )

    confirmed_key = "provider-confirmed-" + c["suffix"]
    completed_key = "provider-completed-" + c["suffix"]
    confirmed = record_signed_test_provider_status(
        c["connect"],
        assertion=provider_assertion("CONFIRMED", confirmed_key),
        verifier_secret=c["secret"],
        case_id=c["case_id"],
        appointment_id=UUID(booked.booking_id),
        provider_id="test-provider",
        status="CONFIRMED",
        event_key=confirmed_key,
    )
    completed_assertion = provider_assertion("COMPLETED", completed_key)
    completed = record_signed_test_provider_status(
        c["connect"],
        assertion=completed_assertion,
        verifier_secret=c["secret"],
        case_id=c["case_id"],
        appointment_id=UUID(booked.booking_id),
        provider_id="test-provider",
        status="COMPLETED",
        event_key=completed_key,
    )
    replay = record_signed_test_provider_status(
        c["connect"],
        assertion=completed_assertion,
        verifier_secret=c["secret"],
        case_id=c["case_id"],
        appointment_id=UUID(booked.booking_id),
        provider_id="test-provider",
        status="COMPLETED",
        event_key=completed_key,
    )
    assert not confirmed.replay
    assert not completed.replay
    assert replay.replay
    assert replay.event_id == completed.event_id

    provider_readback = read_test_provider_status(
        c["connect"],
        case_id=c["case_id"],
        appointment_id=UUID(booked.booking_id),
    )
    assert provider_readback["provider_status"] == "COMPLETED"
    assert provider_readback["provider_order"] == 2
    assert provider_readback["appointment_status"] == "BOOKED_SIMULATED"
    assert provider_readback["changes_booking"] is False

    with c["connect"]() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT event_id,details,correlation_id,actor,event_type,source_id "
                "FROM vab_test.audit_event WHERE event_id IN (%s,%s) "
                "ORDER BY (details->>'provider_order')::bigint",
                (confirmed.event_id, completed.event_id),
            )
            audit = cur.fetchall()
            assert len(audit) == 2
            assert [row[1]["provider_order"] for row in audit] == [1, 2]
            assert all(row[1]["synthetic"] is True for row in audit)
            assert all(row[4] == "SYNTHETIC_PROVIDER_STATUS" for row in audit)
            assert all(row[5] == c["source_id"] for row in audit)

    final_instance = PrivateSyntheticSchedulingGateway(c["connect"], c["secret"])
    final_recovery = final_instance.recover(
        scheduler_assertion=scheduler_assertion, request=req
    )
    assert final_recovery is not None
    assert str(final_recovery.booking_id) == booked.booking_id
