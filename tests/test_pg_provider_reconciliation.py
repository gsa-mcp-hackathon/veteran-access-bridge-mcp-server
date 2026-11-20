"""Provider-status reconciliation is signed, synthetic, local and append-only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4, uuid5

import jwt
import pytest

from veteran_access_bridge.adapters.synthetic_ids import VAB_SYNTHETIC_NAMESPACE
from veteran_access_bridge.services.pg_provider_reconciliation import (
    AUDIENCE,
    ISSUER,
    _claims,
    read_provider_status,
    record_signed_provider_status,
    record_signed_test_provider_status,
)

SECRET = "synthetic-provider-test-signing-secret-32bytes-minimum"
CASE = "DEMO-CARD-5000335-001"
APPOINTMENT_ID = uuid4()
PROVIDER = "PROV-SYNTHETIC-TEST"
EVENT = "provider-event-test-001"


def assertion(*, role="PROVIDER", status="COMPLETED", case_id=CASE):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": "synthetic-provider-actor",
            "role": role,
            "case_id": case_id,
            "appointment_id": str(APPOINTMENT_ID),
            "provider_id": PROVIDER,
            "status": status,
            "event_key": EVENT,
            "synthetic": True,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )


def no_connection():
    raise AssertionError("Invalid request must not access PostgreSQL")


def test_valid_signed_provider_claims():
    data = _claims(
        assertion(),
        secret=SECRET,
        case_id=CASE,
        appointment_id=APPOINTMENT_ID,
        provider_id=PROVIDER,
        status="COMPLETED",
        event_key=EVENT,
    )
    assert data["role"] == "PROVIDER"


@pytest.mark.parametrize(
    "token",
    [
        lambda: assertion(role="SCHEDULER"),
        lambda: assertion(status="CANCELLED"),
        lambda: assertion(case_id="OTHER-CASE"),
    ],
)
def test_wrong_provider_assertion_scope_rejected(token):
    with pytest.raises(PermissionError):
        _claims(
            token(),
            secret=SECRET,
            case_id=CASE,
            appointment_id=APPOINTMENT_ID,
            provider_id=PROVIDER,
            status="COMPLETED",
            event_key=EVENT,
        )


def test_provider_status_disabled_by_default(monkeypatch):
    monkeypatch.delenv("VAB_ENABLE_LOCAL_PROVIDER_RECONCILIATION", raising=False)
    with pytest.raises(PermissionError):
        record_signed_provider_status(
            no_connection,
            assertion=assertion(),
            verifier_secret=SECRET,
            case_id=CASE,
            appointment_id=APPOINTMENT_ID,
            provider_id=PROVIDER,
            status="COMPLETED",
            event_key=EVENT,
        )


def test_test_database_provider_reconciliation_requires_all_opt_in_flags(
    monkeypatch,
):
    monkeypatch.setenv("VAB_SUPABASE_TEST_MODE", "true")
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_TEST_WRITES", "true")
    monkeypatch.delenv("VAB_RUN_SPRINT_A_DB_ACCEPTANCE", raising=False)
    with pytest.raises(PermissionError, match="Opt-in"):
        record_signed_test_provider_status(
            no_connection,
            assertion=assertion(),
            verifier_secret=SECRET,
            case_id=CASE,
            appointment_id=APPOINTMENT_ID,
            provider_id=PROVIDER,
            status="COMPLETED",
            event_key=EVENT,
        )


def test_test_database_provider_reconciliation_rejects_local_database(
    monkeypatch,
):
    monkeypatch.setenv("VAB_RUN_SPRINT_A_DB_ACCEPTANCE", "true")
    monkeypatch.setenv("VAB_SUPABASE_TEST_MODE", "true")
    monkeypatch.setenv("VAB_ENABLE_SUPABASE_TEST_WRITES", "true")

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            assert sql == "SELECT current_database()"

        def fetchone(self):
            return ("veteran_access_bridge_dev",)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    with pytest.raises(PermissionError, match="isolated test schema"):
        record_signed_test_provider_status(
            Connection,
            assertion=assertion(),
            verifier_secret=SECRET,
            case_id=CASE,
            appointment_id=APPOINTMENT_ID,
            provider_id=PROVIDER,
            status="COMPLETED",
            event_key=EVENT,
        )


def test_provider_replay_rejects_mismatched_audit_provenance(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local_synthetic")
    monkeypatch.setenv("VAB_MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("VAB_ENABLE_LOCAL_PROVIDER_RECONCILIATION", "true")
    expected_details = {
        "synthetic": True,
        "case_id": CASE,
        "appointment_id": str(APPOINTMENT_ID),
        "provider_id": PROVIDER,
        "status": "COMPLETED",
        "event_key": EVENT,
        "issuer": ISSUER,
        "provider_order": 1,
    }

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            if sql == "SELECT current_database()":
                self.result = ("veteran_access_bridge_dev",)
            elif "FROM vab.appointment a" in sql:
                self.result = (PROVIDER, "BOOKED_SIMULATED", "fixture-source")
            elif "FROM vab.audit_event WHERE event_id=%s" in sql:
                self.result = (
                    expected_details,
                    "wrong-correlation",
                    "synthetic-provider:synthetic-provider-actor",
                    "SYNTHETIC_PROVIDER_STATUS",
                    "fixture-source",
                )
            else:
                raise AssertionError(f"Unexpected SQL: {sql}")

        def fetchone(self):
            return self.result

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    with pytest.raises(ValueError, match="Conflicting provider event"):
        record_signed_provider_status(
            Connection,
            assertion=assertion(),
            verifier_secret=SECRET,
            case_id=CASE,
            appointment_id=APPOINTMENT_ID,
            provider_id=PROVIDER,
            status="COMPLETED",
            event_key=EVENT,
        )


def test_provider_readback_rejects_audit_for_another_case(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local_synthetic")
    monkeypatch.setenv("VAB_MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("VAB_ENABLE_LOCAL_PROVIDER_RECONCILIATION", "true")
    details = {
        "synthetic": True,
        "case_id": "OTHER-CASE",
        "appointment_id": str(APPOINTMENT_ID),
        "provider_id": PROVIDER,
        "status": "COMPLETED",
        "event_key": EVENT,
        "issuer": ISSUER,
        "provider_order": 1,
    }

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            if sql == "SELECT current_database()":
                self.result = ("veteran_access_bridge_dev",)
            elif "FROM vab.appointment a" in sql:
                self.result = ("BOOKED_SIMULATED", PROVIDER, "fixture-source")
            elif "FROM vab.audit_event WHERE event_type=%s" in sql:
                self.result = (
                    uuid5(VAB_SYNTHETIC_NAMESPACE, "provider-event:" + EVENT),
                    details,
                    EVENT,
                    "synthetic-provider:synthetic-provider-actor",
                    "fixture-source",
                    "SYNTHETIC_PROVIDER_STATUS",
                    datetime.now(timezone.utc),
                )
            else:
                raise AssertionError(f"Unexpected SQL: {sql}")

        def fetchone(self):
            return self.result

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return Cursor()

    with pytest.raises(ValueError, match="Conflicting provider audit"):
        read_provider_status(Connection, case_id=CASE, appointment_id=APPOINTMENT_ID)


def test_invalid_status_rejected_before_sql(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local_synthetic")
    monkeypatch.setenv("VAB_MCP_TRANSPORT", "stdio")
    monkeypatch.setenv("VAB_ENABLE_LOCAL_PROVIDER_RECONCILIATION", "true")
    with pytest.raises(ValueError):
        record_signed_provider_status(
            no_connection,
            assertion=assertion(),
            verifier_secret=SECRET,
            case_id=CASE,
            appointment_id=APPOINTMENT_ID,
            provider_id=PROVIDER,
            status="UNTRUSTED_STATUS",
            event_key=EVENT,
        )


def test_provider_event_order_is_serialized_not_transaction_timestamp():
    import inspect

    from veteran_access_bridge.services.pg_provider_reconciliation import (
        _read_provider_status,
        _record_signed_provider_status,
    )

    writer = inspect.getsource(_record_signed_provider_status)
    reader = inspect.getsource(_read_provider_status)
    assert "FOR UPDATE OF a" in writer
    assert 'expected["provider_order"] = (latest[1] if latest else 0) + 1' in writer
    assert "ORDER BY COALESCE((details->>'provider_order')::bigint,0)" in writer
    assert "ORDER BY COALESCE((details->>'provider_order')::bigint,0)" in reader
    assert writer.index("FOR UPDATE OF a") < writer.index('expected["provider_order"]')
