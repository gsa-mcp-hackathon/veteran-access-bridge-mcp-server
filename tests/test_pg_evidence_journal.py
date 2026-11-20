"""Contract tests for guarded lifecycle evidence journal."""

import pytest

from veteran_access_bridge.adapters.pg_evidence_journal import (
    ValidatedTransition,
    persist_validated_transition,
)


class FakeCursor:
    def __init__(self):
        self.statements = []
        self.last = ""
        self.inserted = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))
        self.last = sql
        if "INSERT INTO" in sql:
            self.inserted = True

    def fetchone(self):
        if "current_database()" in self.last:
            return ("veteran_access_bridge_dev",)
        if "RETURNING transition_id" in self.last:
            return ("some-uuid",)
        return None


class FakeConnection:
    def __init__(self):
        self.cur = FakeCursor()

    def cursor(self):
        return self.cur


def event(**overrides):
    values = {
        "case_id": "DEMO-PC-5000999-001",
        "event_type": "OPTION_SELECTED",
        "from_state": "READY_TO_SEARCH",
        "to_state": "OPTION_SELECTED",
        "actor_role": "VETERAN",
        "actor_id": "synthetic-veteran",
        "idempotency_key": "selection-01",
        "correlation_id": "synthetic-correlation",
        "evidence_reference": "service-result-01",
    }
    values.update(overrides)
    return ValidatedTransition(**values)


def test_validated_event_uses_parameterized_sql():
    conn = FakeConnection()
    assert persist_validated_transition(conn, event())
    sql, params = conn.cur.statements[-1]
    assert "VALUES (%s,%s" in sql
    assert params[1] == "DEMO-PC-5000999-001"
    assert "appointment" not in sql
    assert "service_evidence_reference" in params[-1]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"event_type": "BOOKED_SIMULATED"}, "Unsupported"),
        ({"actor_role": "LLM"}, "Unsupported"),
        ({"evidence_reference": ""}, "nonempty"),
        (
            {"event_type": "VETERAN_CONFIRMATION_RECORDED", "actor_role": "SYSTEM"},
            "Veteran",
        ),
        (
            {"event_type": "SCHEDULER_REVIEW_RECORDED", "actor_role": "VETERAN"},
            "Scheduler",
        ),
    ],
)
def test_unsafe_evidence_fails_closed(overrides, message):
    conn = FakeConnection()
    with pytest.raises(ValueError, match=message):
        persist_validated_transition(conn, event(**overrides))
    assert not conn.cur.inserted
