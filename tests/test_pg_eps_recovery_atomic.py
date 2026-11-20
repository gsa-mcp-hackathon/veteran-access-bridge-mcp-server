"""Offline regression checks for immutable committed EPS booking recovery."""

from uuid import uuid4

import pytest

from veteran_access_bridge.adapters.pg_eps_recovery import (
    recover_committed_eps_booking,
)
from veteran_access_bridge.adapters.synthetic_ids import persistent_uuid

CASE = "DEMO-PC-5000999-001"


class RecoveryCursor:
    def __init__(self, identity, *, missing_audit=False, wrong_authorization=False):
        self.identity = identity
        self.missing_audit = missing_audit
        self.wrong_authorization = wrong_authorization
        self.queries = []
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.queries.append(sql)
        i = self.identity
        if sql == "SELECT current_database()":
            self.result = ("veteran_access_bridge_dev",)
        elif "FROM vab.appointment a" in sql:
            self.result = (
                persistent_uuid("appointment", i["idempotency_key"]),
                i["slot_id"],
                i["scheduler_actor_id"],
                "BOOKED_SIMULATED",
                "EPS",
                "BOOKED",
                i["case_id"],
                i["patient_id"],
                i["patient_id"],
                "provider-1",
                "fixture-source",
            )
        elif "FROM vab.scheduling_transition" in sql:
            self.result = (
                self.evidence(),
                i["case_id"],
                "booking:" + i["idempotency_key"],
            )
        elif "FROM vab.audit_event" in sql:
            self.result = (
                self.evidence(),
                i["idempotency_key"],
                "fixture-source",
            ) if not self.missing_audit else None
        else:
            self.result = None

    def evidence(self):
        i = self.identity
        return {
            "synthetic": True,
            "appointment_id": str(persistent_uuid("appointment", i["idempotency_key"])),
            "case_id": i["case_id"],
            "option_id": i["option_id"],
            "slot_id": str(i["slot_id"]),
            "authorization_id": str(
                uuid4() if self.wrong_authorization else i["authorization_id"]
            ),
            "provider_id": "provider-1",
            "scheduler_actor_id": i["scheduler_actor_id"],
            "idempotency_key": i["idempotency_key"],
            "slot_source_id": "fixture-source",
            "authorization_source_id": "fixture-source",
        }

    def fetchone(self):
        return self.result


class RecoveryConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_obj


def _inputs():
    return {
        "case_id": CASE,
        "option_id": "OPT-PC-001",
        "slot_id": uuid4(),
        "authorization_id": uuid4(),
        "idempotency_key": uuid4().hex,
        "scheduler_actor_id": "trusted-scheduler",
        "patient_id": uuid4(),
    }


def _recover(cursor, identity):
    args = {key: value for key, value in identity.items() if key != "patient_id"}
    return recover_committed_eps_booking(
        lambda: RecoveryConnection(cursor), **args
    )


def test_recovery_uses_immutable_evidence_not_current_authorization_or_decision():
    identity = _inputs()
    cursor = RecoveryCursor(identity)
    receipt = _recover(cursor, identity)
    assert receipt.status == "BOOKED_SIMULATED"
    assert receipt.booking_id == persistent_uuid(
        "appointment", identity["idempotency_key"]
    )
    assert not any("FROM vab.authorization" in sql for sql in cursor.queries)
    assert not any("FROM vab.scheduling_decision" in sql for sql in cursor.queries)
    assert any("FROM vab.audit_event" in sql for sql in cursor.queries)


@pytest.mark.parametrize("failure", ["missing_audit", "wrong_authorization"])
def test_missing_or_conflicting_immutable_evidence_is_not_recovered(failure):
    identity = _inputs()
    cursor = RecoveryCursor(identity, **{failure: True})
    with pytest.raises(ValueError, match="(missing atomic|Conflicting committed)"):
        _recover(cursor, identity)
