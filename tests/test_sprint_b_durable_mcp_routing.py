"""Existing scheduling MCP tools: private durable reads and fail-closed writes."""

from datetime import datetime, timezone

import pytest

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    SUPABASE_PROJECT_REF,
    SUPABASE_TEST_LOGIN,
    SUPABASE_TEST_ROLE,
)
from veteran_access_bridge.mcp import durable_runtime
from veteran_access_bridge.mcp.tools import (
    get_case_lifecycle_state,
    get_scheduling_encounter,
    record_lifecycle_event,
    record_option_selection,
    record_veteran_confirmation,
    validate_booking_preconditions,
)


class FakeCursor:
    def __init__(self, exists=True):
        self.exists = exists
        self.sql = []
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        if sql == "SELECT current_database()":
            self.result = ("postgres",)
        elif sql == "SELECT current_user, session_user":
            self.result = (SUPABASE_TEST_ROLE, SUPABASE_TEST_LOGIN)
        elif "FROM vab_test.scheduling_case_link l" in sql:
            self.result = (
                (
                    "TEST-CASE",
                    "request-uuid",
                    "PRIMARY_CARE",
                    "PRIMARY CARE",
                    "OPEN",
                    datetime(2026, 11, 12, tzinfo=timezone.utc),
                )
                if self.exists
                else None
            )
        elif "FROM vab_test.appointment a" in sql:
            self.result = None
        elif "FROM vab_test.scheduling_decision d" in sql:
            self.result = None
        elif "SELECT count(*)" in sql:
            self.result = (0,)
        elif "FROM vab_test.scheduling_transition WHERE" in sql:
            self.result = []
        else:
            raise AssertionError(f"Unexpected SQL {sql}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result


class FakeConnection:
    def __init__(self, cursor):
        self.c = cursor
        self.info = type(
            "ConnectionInfo",
            (),
            {
                "host": f"db.{SUPABASE_PROJECT_REF}.supabase.co",
                "user": SUPABASE_TEST_LOGIN,
            },
        )()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.c


@pytest.fixture
def durable(monkeypatch):
    monkeypatch.setenv("VAB_SCHEDULING_RUNTIME_MODE", "supabase_test")
    monkeypatch.setenv("VAB_SUPABASE_PROJECT_REF", SUPABASE_PROJECT_REF)
    monkeypatch.setenv("VAB_SUPABASE_TEST_MODE", "true")
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_TEST_WRITES", "true")


def test_unknown_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("VAB_SCHEDULING_RUNTIME_MODE", "not-a-real-mode")
    with pytest.raises(PermissionError, match="Unknown"):
        durable_runtime.scheduling_mode()


def test_default_mode_is_demo(monkeypatch):
    monkeypatch.delenv("VAB_SCHEDULING_RUNTIME_MODE", raising=False)
    assert durable_runtime.scheduling_mode() == "demo"


def test_public_durable_lifecycle_read_denied_before_db(durable):
    with pytest.raises(PermissionError, match="independently verified"):
        get_case_lifecycle_state.run("TEST-CASE", include_history=True)
    with pytest.raises(PermissionError, match="independently verified"):
        get_scheduling_encounter.run("TEST-CASE")


def test_private_read_requires_explicit_server_connection(durable):
    cursor = FakeCursor()
    result = durable_runtime.read_case_from_supabase(
        "TEST-CASE", include_history=True, connect=lambda: FakeConnection(cursor)
    )
    assert result["persistence"] == "supabase_test"
    assert result["found"] is True
    assert result["event_history"] == []


def test_private_read_rejects_non_test_database_before_case_query(durable):
    class LocalDatabaseCursor(FakeCursor):
        def execute(self, sql, params=None):
            self.sql.append((sql, params))
            if sql == "SELECT current_database()":
                self.result = ("veteran_access_bridge_dev",)
            else:
                raise AssertionError(f"Case query must not run: {sql}")

    cursor = LocalDatabaseCursor()
    with pytest.raises(PermissionError, match="isolated test schema"):
        durable_runtime.read_case_from_supabase(
            "TEST-CASE", connect=lambda: FakeConnection(cursor)
        )
    assert len(cursor.sql) == 1


def test_private_read_missing_case_never_uses_demo(durable):
    cursor = FakeCursor(exists=False)
    result = durable_runtime.read_case_from_supabase(
        "TEST-CASE", connect=lambda: FakeConnection(cursor)
    )
    assert result["found"] is False
    assert result["persistence"] == "supabase_test"


def test_private_read_database_failure_never_falls_back(durable):
    def offline():
        raise ConnectionError("test database unavailable")

    with pytest.raises(ConnectionError, match="unavailable"):
        durable_runtime.read_case_from_supabase("TEST-CASE", connect=offline)


@pytest.mark.parametrize(
    "tool,args",
    [
        (record_option_selection.run, ("case", "handoff", "option", "actor", "key")),
        (
            record_veteran_confirmation.run,
            ("case", "confirmation", "option", "CONFIRMED", "actor", "key"),
        ),
        (
            record_lifecycle_event.run,
            ("case", "APPOINTMENT_CANCELLED", "VETERAN", "actor", "key"),
        ),
    ],
)
def test_durable_mutations_refuse_untrusted_actor_id(durable, tool, args):
    with pytest.raises(PermissionError, match="trusted signed actor"):
        tool(*args)


def test_durable_preconditions_never_claim_bookable(durable, monkeypatch):
    with pytest.raises(PermissionError, match="independently verified"):
        validate_booking_preconditions.run(
            "case",
            "option",
            "slot",
            "EPS",
            "PRIMARY CARE",
            "INITIAL_CONSULT",
            "untrusted-actor",
            "key",
        )


def test_private_signed_confirmation_routes_to_durable_gateway(durable):
    from veteran_access_bridge.services.pg_signed_decisions import DecisionReceipt

    class Gateway:
        def __init__(self):
            self.kwargs = None

        def record_veteran_response_from_trusted_service(self, **kwargs):
            self.kwargs = kwargs
            return DecisionReceipt(
                case_id="case",
                option_id="option",
                actor_role="VETERAN",
                status="ACCEPTED",
                decision_id="decision",
                transition_id="transition",
                idempotent_replay=False,
            )

    gateway = Gateway()
    value = record_veteran_confirmation.run(
        "case",
        "confirmation",
        "option",
        "CONFIRMED",
        "veteran",
        "key",
        trusted_gateway=gateway,
        trusted_assertion="server-only-signed-token",
        verified_evidence_reference="server-verified-evidence",
    )
    assert value["persistence"] == "supabase_test"
    assert value["status"] == "ACCEPTED"
    assert value["creates_booking"] is False
    assert gateway.kwargs["expected_actor_id"] == "veteran"
    assert gateway.kwargs["verified_evidence_reference"] == "server-verified-evidence"


def test_private_durable_confirmation_rejects_unsupported_change(durable):
    class Gateway:
        def record_veteran_response_from_trusted_service(self, **_kwargs):
            raise AssertionError("Must reject before persisting")

    with pytest.raises(PermissionError, match="reviewed signed lifecycle"):
        record_veteran_confirmation.run(
            "case",
            "confirmation",
            "option",
            "REQUESTED_CHANGE",
            "veteran",
            "key",
            trusted_gateway=Gateway(),
            trusted_assertion="server-only-signed-token",
            verified_evidence_reference="server-verified-evidence",
        )


def test_private_signed_decline_is_persisted_as_rejected(durable):
    from veteran_access_bridge.services.pg_signed_decisions import DecisionReceipt

    class Gateway:
        def record_veteran_response_from_trusted_service(self, **kwargs):
            assert kwargs["accepted"] is False
            return DecisionReceipt(
                case_id="case",
                option_id="option",
                actor_role="VETERAN",
                status="REJECTED",
                decision_id="decision",
                transition_id="transition",
                idempotent_replay=False,
            )

    value = record_veteran_confirmation.run(
        "case",
        "confirmation",
        "option",
        "DECLINED",
        "veteran",
        "key",
        trusted_gateway=Gateway(),
        trusted_assertion="server-only-signed-token",
        verified_evidence_reference="server-verified-evidence",
    )
    assert value["status"] == "REJECTED"
    assert value["creates_booking"] is False


def test_signed_scheduler_replay_checked_before_current_consent():
    import inspect

    from veteran_access_bridge.services.pg_signed_decisions import (
        _persist_signed_scheduling_decision,
    )

    source = inspect.getsource(_persist_signed_scheduling_decision)
    assert source.index("WHERE idempotency_key=%s FOR UPDATE") < source.index(
        'if role == "SCHEDULER" and accepted:'
    )
    assert source.index("return DecisionReceipt(") < source.index(
        'if role == "SCHEDULER" and accepted:'
    )
