"""Fail-closed tests for the private signed PostgreSQL decision boundary."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from veteran_access_bridge.services.pg_signed_decisions import (
    AUDIENCE,
    ISSUER,
    _trusted_claims,
    persist_signed_scheduling_decision,
)

SECRET = "local-testing-only-synthetic-signing-key-32-bytes-long"
CASE = "DEMO-CARD-5000335-001"


def assertion(*, role="VETERAN", case_id=CASE, synthetic=True, delta=60):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": "test-actor-001",
            "role": role,
            "case_id": case_id,
            "synthetic": synthetic,
            "iat": now,
            "exp": now + timedelta(seconds=delta),
            "iss": ISSUER,
            "aud": AUDIENCE,
        },
        SECRET,
        algorithm="HS256",
    )


def no_connection():
    raise AssertionError("No database connection should be opened")


def call_with(token, *, secret=SECRET):
    return persist_signed_scheduling_decision(
        no_connection,
        assertion=token,
        verifier_secret=secret,
        case_id=CASE,
        option_id="OPT-CC-001",
        idempotency_key="test-rejected-before-db",
        correlation_id="test-correlation",
        service_evidence_reference="test-service-evidence",
    )


def test_trusted_veteran_and_scheduler_claims():
    for role in ("VETERAN", "SCHEDULER"):
        claims = _trusted_claims(assertion(role=role), SECRET, CASE)
        assert claims["role"] == role


@pytest.mark.parametrize(
    "token",
    [
        lambda: assertion(role="SYSTEM"),
        lambda: assertion(case_id="OTHER-CASE"),
        lambda: assertion(synthetic=False),
        lambda: assertion(delta=-5),
    ],
)
def test_untrusted_assertions_rejected_without_database(token):
    with pytest.raises(PermissionError):
        call_with(token())


def test_weak_verifier_secret_rejected_without_database():
    with pytest.raises(PermissionError):
        call_with(assertion(), secret="short")


def test_missing_reference_rejected_without_database():
    with pytest.raises(ValueError):
        persist_signed_scheduling_decision(
            no_connection,
            assertion=assertion(),
            verifier_secret=SECRET,
            case_id=CASE,
            option_id="OPT-CC-001",
            idempotency_key="test",
            correlation_id="test",
            service_evidence_reference="",
        )


class DecisionCursor:
    def __init__(self):
        self.statements = []
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        self.statements.append((statement, params))
        if "SELECT l.request_id" in statement:
            self.result = ("request-id",)
        elif "SELECT EXISTS" in statement:
            self.result = (params[-1] == "trusted-source",)
        else:
            raise AssertionError(f"Unexpected SQL: {statement}")

    def fetchone(self):
        return self.result


class DecisionConnection:
    def __init__(self):
        self.cursor_instance = DecisionCursor()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


def test_unbound_evidence_reference_is_rejected_before_decision_write(monkeypatch):
    from veteran_access_bridge.services import pg_signed_decisions

    monkeypatch.setattr(
        pg_signed_decisions,
        "_trusted_claims",
        lambda *_args: {"role": "VETERAN", "sub": "trusted-veteran"},
    )
    monkeypatch.setattr(
        pg_signed_decisions,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )
    connection = DecisionConnection()

    with pytest.raises(ValueError, match="evidence not owned"):
        persist_signed_scheduling_decision(
            lambda: connection,
            assertion="test-signed-assertion",
            verifier_secret=SECRET,
            case_id=CASE,
            option_id="OPT-CC-001",
            idempotency_key="unbound-evidence",
            correlation_id="test-correlation",
            service_evidence_reference="caller-invented-reference",
        )

    assert not any(
        "INSERT INTO" in statement
        for statement, _params in connection.cursor_instance.statements
    )


@pytest.mark.parametrize(
    ("writer_name", "role", "expected_channels"),
    [
        ("persist_signed_scheduling_decision", "VETERAN", ["EPS"]),
        (
            "persist_signed_va_scheduling_decision",
            "VETERAN",
            ["VISTA", "FEDERAL_EHR"],
        ),
    ],
)
def test_signed_decision_writer_keeps_channel_scopes_separate(
    monkeypatch, writer_name, role, expected_channels
):
    from veteran_access_bridge.services import pg_signed_decisions

    writer = getattr(pg_signed_decisions, writer_name)
    connection = DecisionConnection()
    monkeypatch.setattr(
        pg_signed_decisions,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )

    def execute(cur, schema, statement, params=None):
        assert schema == "vab_test"
        cur.statements.append((statement, params))
        if "SELECT l.request_id" in statement:
            cur.result = ("request-id",)
        elif "SELECT EXISTS" in statement:
            cur.result = (True,)
        elif "WHERE idempotency_key=%s FOR UPDATE" in statement:
            cur.result = None
        else:
            cur.result = None

    monkeypatch.setattr(pg_signed_decisions, "execute_scheduling_sql", execute)
    receipt = writer(
        lambda: connection,
        assertion=assertion(role=role),
        verifier_secret=SECRET,
        case_id=CASE,
        option_id="OPT-CC-001",
        idempotency_key=f"test-{role.lower()}",
        correlation_id="test-correlation",
        service_evidence_reference="trusted-source",
    )

    option_query = next(
        (sql, params)
        for sql, params in connection.cursor_instance.statements
        if "SELECT EXISTS" in sql
    )
    assert "s.channel = ANY(%s)" in option_query[0]
    assert option_query[1][0] == expected_channels
    assert receipt.actor_role == role
    assert any(
        "INSERT INTO vab.scheduling_decision" in sql
        for sql, _ in connection.cursor_instance.statements
    )


def test_scheduler_decision_checks_latest_case_wide_veteran_response(
    monkeypatch,
):
    from veteran_access_bridge.services import pg_signed_decisions

    connection = DecisionConnection()
    monkeypatch.setattr(
        pg_signed_decisions,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )
    evidence = {"service_evidence_reference": "trusted-veteran-evidence"}

    def execute(cur, schema, statement, params=None):
        assert schema == "vab_test"
        cur.statements.append((statement, params))
        if "SELECT l.request_id" in statement:
            cur.result = ("request-id",)
        elif "SELECT EXISTS" in statement:
            cur.result = (True,)
        elif "WHERE idempotency_key=%s FOR UPDATE" in statement:
            cur.result = None
        elif "SELECT d.decision_status" in statement:
            cur.result = (
                "REJECTED",
                "OTHER-OPTION",
                "test-actor-001",
                evidence,
                "transition-1",
                "VETERAN_CONFIRMATION_RECORDED",
                "VETERAN",
                "test-actor-001",
                evidence,
            )
        else:
            cur.result = None

    monkeypatch.setattr(pg_signed_decisions, "execute_scheduling_sql", execute)
    with pytest.raises(ValueError, match="Current Veteran confirmation"):
        pg_signed_decisions.persist_signed_va_scheduling_decision(
            lambda: connection,
            assertion=assertion(role="SCHEDULER"),
            verifier_secret=SECRET,
            case_id=CASE,
            option_id="OPT-CC-001",
            idempotency_key="test-scheduler",
            correlation_id="test-correlation",
            service_evidence_reference="trusted-source",
        )

    latest_query = next(
        sql
        for sql, _ in connection.cursor_instance.statements
        if "SELECT d.decision_status" in sql
    )
    assert "WHERE d.case_id=%s" in latest_query
    assert "d.option_id=%s" not in latest_query
    assert not any(
        "INSERT INTO vab.scheduling_decision" in sql
        for sql, _ in connection.cursor_instance.statements
    )
