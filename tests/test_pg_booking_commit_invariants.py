"""Regression tests for the private primary-care SQL booking commit gates.

All database interactions use an in-memory cursor stub. No SQL is executed.
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from veteran_access_bridge.adapters.pg_synthetic_eps_booking import (
    EPSBookingRequest,
    commit_synthetic_eps_booking,
)


class FakeCursor:
    def __init__(
        self,
        request,
        *,
        kind="PRIMARY_CARE",
        eligible=True,
        veteran="ACCEPTED",
        scheduler="ACCEPTED",
        audit_failure=False,
        replay=False,
        existing_active=False,
        conflicting_replay=False,
        missing_replay_audit=False,
        veteran_order=10,
        scheduler_order=11,
    ):
        self.request = request
        self.kind = kind
        self.eligible = eligible
        self.veteran = veteran
        self.scheduler = scheduler
        self.audit_failure = audit_failure
        self.replay = replay
        self.existing_active = existing_active
        self.conflicting_replay = conflicting_replay
        self.missing_replay_audit = missing_replay_audit
        self.veteran_order = veteran_order
        self.scheduler_order = scheduler_order
        self.queries = []
        self.rowcount = 1
        self.now = datetime.now(timezone.utc)
        self.request_id = uuid4()
        self.patient_id = uuid4()
        self._result = None
        self.appointment_evidence = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        r = self.request
        if sql == "SELECT current_database()":
            self._result = ("veteran_access_bridge_dev",)
        elif "FROM vab.scheduling_case_link l" in sql and "JOIN vab.appointment_request" in sql:
            self._result = (self.request_id, self.patient_id, "PRIMARY CARE", self.kind)
        elif "FROM vab.slot WHERE slot_id=%s FOR UPDATE" in sql:
            self._result = (
                "EPS", "AVAILABLE", "provider-1", self.now,
                "fixture-source", self.now + timedelta(days=1)
            )
        elif "SELECT source_kind,provenance" in sql:
            self._result = (
                "synthetic_fixture",
                {"slot_bindings": {str(r.slot_id): {
                    "case_id": r.case_id, "option_id": r.option_id,
                    "initial_consult_eligible": self.eligible,
                }}},
            )
        elif "SELECT source_kind FROM vab.data_source" in sql:
            self._result = ("synthetic_fixture",)
        elif "FROM vab.authorization a" in sql:
            self._result = (
                "ACTIVE", self.now - timedelta(days=1),
                self.now + timedelta(days=1), "PRIMARY CARE",
                {
                    "synthetic": True, "case_id": r.case_id,
                    "option_id": r.option_id, "slot_id": str(r.slot_id),
                    "provider_id": "provider-1", "provenance_ref": "fixture-ref",
                },
                "fixture-source", self.patient_id, "ACTIVE",
                {"case_id": r.case_id},
            )
        elif "SELECT (%s <= clock_timestamp()" in sql:
            self._result = (True,)
        elif "SELECT d.decision_status,d.decision_order" in sql:
            role = params[2]
            self._result = (
                self.veteran if role == "VETERAN" else self.scheduler,
                self.veteran_order if role == "VETERAN" else self.scheduler_order,
            )
        elif "FROM vab.appointment a JOIN vab.slot s" in sql:
            from veteran_access_bridge.adapters.synthetic_ids import persistent_uuid

            self._result = (
                persistent_uuid("appointment", r.idempotency_key),
                self.request_id,
                uuid4() if self.conflicting_replay else r.slot_id,
                r.scheduler_actor_id,
                "BOOKED_SIMULATED",
                self.patient_id,
                "BOOKED",
                "EPS",
                "provider-1",
                "fixture-source",
            ) if self.replay else None
        elif "SELECT appointment_id FROM vab.appointment" in sql:
            self._result = (uuid4(),) if self.existing_active else None
        elif "SELECT evidence,case_id,idempotency_key" in sql:
            self._result = (
                self.replay_evidence(),
                r.case_id,
                "booking:" + r.idempotency_key,
            ) if self.replay else None
        elif "SELECT details,correlation_id,source_id" in sql:
            self._result = (
                self.replay_evidence(),
                r.idempotency_key,
                "fixture-source",
            ) if self.replay and not self.missing_replay_audit else None
        elif "INSERT INTO vab.scheduling_transition" in sql:
            self.appointment_evidence = json.loads(params[-1])
            self._result = None
        elif "INSERT INTO vab.audit_event" in sql:
            if self.audit_failure:
                raise RuntimeError("simulated audit insertion failure")
            self._result = None
        else:
            self._result = None

    def replay_evidence(self):
        from veteran_access_bridge.adapters.synthetic_ids import persistent_uuid

        return {
            "synthetic": True,
            "appointment_id": str(persistent_uuid("appointment", self.request.idempotency_key)),
            "case_id": self.request.case_id,
            "option_id": self.request.option_id,
            "slot_id": str(self.request.slot_id),
            "authorization_id": str(self.request.authorization_id),
            "provider_id": "provider-1",
            "scheduler_actor_id": self.request.scheduler_actor_id,
            "idempotency_key": self.request.idempotency_key,
            "slot_source_id": "fixture-source",
            "authorization_source_id": "fixture-source",
        }

    def fetchone(self):
        return self._result


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_stub = cursor
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self):
        return self.cursor_stub

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def booking_request():
    return EPSBookingRequest(
        case_id="DEMO-PC-5000999-001",
        option_id="OPT-PC-001",
        slot_id=uuid4(),
        authorization_id=uuid4(),
        idempotency_key=uuid4().hex,
        scheduler_actor_id="trusted-scheduler",
    )


@pytest.mark.parametrize("role", ["VETERAN", "SCHEDULER"])
def test_latest_rejection_blocks_booking_before_slot_update(role):
    request = booking_request()
    cursor = FakeCursor(
        request,
        veteran="REJECTED" if role == "VETERAN" else "ACCEPTED",
        scheduler="REJECTED" if role == "SCHEDULER" else "ACCEPTED",
    )
    with pytest.raises(ValueError, match="not accepted"):
        commit_synthetic_eps_booking(FakeConnection(cursor), request)
    assert not any("UPDATE vab.slot" in q for q, _ in cursor.queries)
    assert any("ORDER BY d.decision_order DESC" in q for q, _ in cursor.queries)


def test_ineligible_slot_blocks_booking_at_commit_not_only_preflight():
    request = booking_request()
    cursor = FakeCursor(request, eligible=False)
    with pytest.raises(ValueError, match="eligibility denied"):
        commit_synthetic_eps_booking(FakeConnection(cursor), request)
    assert not any("UPDATE vab.slot" in q for q, _ in cursor.queries)


def test_specialty_booking_fails_closed_without_consult_implementation():
    request = booking_request()
    cursor = FakeCursor(request, kind="SPECIALTY")
    with pytest.raises(ValueError, match="Only primary-care"):
        commit_synthetic_eps_booking(FakeConnection(cursor), request)
    assert not any("UPDATE vab.slot" in q for q, _ in cursor.queries)


def test_primary_care_booking_writes_transition_and_audit_in_same_transaction():
    request = booking_request()
    cursor = FakeCursor(request)
    conn = FakeConnection(cursor)
    appointment = commit_synthetic_eps_booking(conn, request)
    sqls = [sql for sql, _ in cursor.queries]
    assert any("INSERT INTO vab.appointment " in sql for sql in sqls)
    assert any("INSERT INTO vab.scheduling_transition " in sql for sql in sqls)
    assert any("INSERT INTO vab.audit_event " in sql for sql in sqls)
    assert cursor.appointment_evidence["appointment_id"] == str(appointment)
    assert cursor.appointment_evidence["authorization_id"] == str(request.authorization_id)
    assert conn.commit_calls == 0  # caller owns atomic commit


def test_audit_failure_propagates_without_booking_acknowledgement():
    request = booking_request()
    cursor = FakeCursor(request, audit_failure=True)
    conn = FakeConnection(cursor)
    with pytest.raises(RuntimeError, match="audit insertion failure"):
        commit_synthetic_eps_booking(conn, request)
    assert conn.commit_calls == 0
    assert any("INSERT INTO vab.appointment " in q for q, _ in cursor.queries)


def test_ambiguous_evidence_failure_causes_caller_rollback():
    from veteran_access_bridge.services.pg_governed_eps_commit import (
        BookingOutcome,
        VerifiedSchedulerContext,
        commit_verified_synthetic_eps_booking,
    )

    request = booking_request()
    cursor = FakeCursor(request, audit_failure=True)
    tx = FakeConnection(cursor)
    context = VerifiedSchedulerContext(
        actor_id=request.scheduler_actor_id,
        case_id=request.case_id,
        authenticated=True,
        authorized_scheduler=True,
    )
    receipt = commit_verified_synthetic_eps_booking(
        lambda: tx, context=context, request=request
    )
    assert receipt.status == BookingOutcome.RECOVERY_REQUIRED
    assert tx.commit_calls == 0
    assert tx.rollback_calls == 1


def test_approval_predating_latest_consent_cannot_book():
    request = booking_request()
    # Sequence order is authoritative even if clocks reported otherwise.
    cursor = FakeCursor(request, veteran_order=27, scheduler_order=26)
    with pytest.raises(ValueError, match="predates latest Veteran consent"):
        commit_synthetic_eps_booking(FakeConnection(cursor), request)
    assert not any("UPDATE vab.slot" in sql for sql, _ in cursor.queries)


def test_booking_queries_never_select_latest_decision_by_transaction_timestamp():
    request = booking_request()
    cursor = FakeCursor(request)
    commit_synthetic_eps_booking(FakeConnection(cursor), request)
    decision_queries = [
        sql for sql, _ in cursor.queries
        if "FROM vab.scheduling_decision d" in sql
    ]
    assert len(decision_queries) == 2
    assert all("ORDER BY d.decision_order DESC" in sql for sql in decision_queries)
    assert all("ORDER BY d.decided_at" not in sql for sql in decision_queries)


def test_second_booking_key_for_same_request_is_rejected_before_slot_write():
    request = booking_request()
    cursor = FakeCursor(request, existing_active=True)
    with pytest.raises(ValueError, match="already has an active"):
        commit_synthetic_eps_booking(FakeConnection(cursor), request)
    sqls = [sql for sql, _ in cursor.queries]
    assert any("WHERE request_id=%s AND status='BOOKED_SIMULATED'" in sql for sql in sqls)
    assert not any("UPDATE vab.slot" in sql for sql in sqls)
    assert not any("INSERT INTO vab.appointment " in sql for sql in sqls)


def test_exact_key_replay_is_verified_before_mutable_booking_checks():
    from veteran_access_bridge.adapters.synthetic_ids import persistent_uuid

    request = booking_request()
    cursor = FakeCursor(request, replay=True, eligible=False, veteran="REJECTED")
    result = commit_synthetic_eps_booking(FakeConnection(cursor), request)
    assert result == persistent_uuid("appointment", request.idempotency_key)
    sqls = [sql for sql, _ in cursor.queries]
    assert not any("FROM vab.slot WHERE" in sql for sql in sqls)
    assert not any("FROM vab.authorization" in sql for sql in sqls)
    assert not any("FROM vab.scheduling_decision" in sql for sql in sqls)
    assert not any("UPDATE vab.slot" in sql for sql in sqls)


def test_conflicting_exact_key_replay_is_rejected():
    request = booking_request()
    cursor = FakeCursor(request, replay=True, conflicting_replay=True)
    with pytest.raises(ValueError, match="Conflicting EPS booking idempotency key"):
        commit_synthetic_eps_booking(FakeConnection(cursor), request)
    assert not any("UPDATE vab.slot" in sql for sql, _ in cursor.queries)


def test_missing_atomic_audit_denies_replay():
    request = booking_request()
    cursor = FakeCursor(request, replay=True, missing_replay_audit=True)
    with pytest.raises(ValueError, match="missing matching atomic evidence"):
        commit_synthetic_eps_booking(FakeConnection(cursor), request)
    assert not any("UPDATE vab.slot" in sql for sql, _ in cursor.queries)


def test_replay_keeps_original_booking_even_if_second_attempt_could_not_pass_current_gates():
    request = booking_request()
    cursor = FakeCursor(
        request,
        replay=True,
        existing_active=True,
        eligible=False,
        scheduler="REJECTED",
        veteran="REJECTED",
    )
    commit_synthetic_eps_booking(FakeConnection(cursor), request)
    assert not any("WHERE request_id=%s AND status='BOOKED_SIMULATED'" in sql
                   for sql, _ in cursor.queries)


def test_lock_wait_time_checks_use_wall_clock_not_transaction_start():
    request = booking_request()
    cursor = FakeCursor(request)
    commit_synthetic_eps_booking(FakeConnection(cursor), request)
    checks = [q for q, _ in cursor.queries if "interval '15 minutes'" in q]
    assert len(checks) == 1
    assert "clock_timestamp()" in checks[0]
    assert "now()" not in checks[0]
    assert any("FOR UPDATE OF a,f" in q for q, _ in cursor.queries)
    assert cursor.queries.index(
        next(item for item in cursor.queries if "FOR UPDATE OF a,f" in item[0])
    ) < cursor.queries.index(
        next(item for item in cursor.queries if "interval '15 minutes'" in item[0])
    )
