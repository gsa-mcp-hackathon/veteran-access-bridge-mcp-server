"""Isolated contract regressions for private, autonomous internal VA booking.

No network calls, credentials, Supabase writes or real VA booking are used here.
The independently authenticated host issuer and live DB acceptance are separate gates.
"""

import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
import pytest

from veteran_access_bridge.services.pg_governed_va_commit import (
    AUDIENCE,
    ISSUER,
    POLICY_VERSION,
    SCOPE,
    VABookingRequest,
    _verified_booking_claims,
    _verified_machine_actor,
    commit_internal_va_booking,
    readback_internal_va_booking,
)

SECRET = "test-only-never-deploy-" + "Z" * 40
IDENTITY_EVIDENCE_EXPIRES_AT = int(time.time()) + 600


def _request():
    return VABookingRequest(
        case_id="DEMO-PC-001",
        option_id="VA-PC-OPT-1",
        slot_id=uuid4(),
        idempotency_key="va-pc-one-commit",
    )


def test_wrong_signing_key_and_missing_assertion_fail_before_database_access():
    request = _request()
    missing_confirmation_claims = jwt.decode(
        _assertion(request),
        options={"verify_signature": False},
        algorithms=["HS256"],
    )
    missing_confirmation_claims.pop("veteran_confirmation_id")
    missing_confirmation_claim = jwt.encode(
        missing_confirmation_claims, SECRET, algorithm="HS256"
    )

    def never_connect():
        pytest.fail("Unauthorized assertion reached the database")

    for assertion in (
        "",
        _assertion(
            request,
            signing_secret="different-test-signing-key-with-at-least-32-bytes",
        ),
        missing_confirmation_claim,
    ):
        with pytest.raises(PermissionError):
            commit_internal_va_booking(
                never_connect,
                assertion=assertion,
                verifier_secret=SECRET,
                request=request,
            )


def _assertion(request, *, signing_secret=SECRET, **overrides):
    now = datetime.now(timezone.utc)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "trusted-avery-service",
        "role": "SERVICE",
        "scope": SCOPE,
        "case_id": request.case_id,
        "option_id": request.option_id,
        "slot_id": str(request.slot_id),
        "synthetic": True,
        "jti": "assertion-1",
        "idempotency_key": request.idempotency_key,
        "identity_verified": True,
        "identity_case_id": request.case_id,
        "identity_verification_id": "identity-verification-1",
        "identity_verification_expires_at": IDENTITY_EVIDENCE_EXPIRES_AT,
        "veteran_confirmation_id": str(UUID("00000000-0000-0000-0000-000000000001")),
        "policy_version": POLICY_VERSION,
        "policy_decision": "ALLOW",
        "policy_evidence_reference": "trusted-host-policy-evaluation-1",
        "human_review_required": False,
        "iat": now,
        "exp": now + timedelta(minutes=2),
    }
    claims.update(overrides)
    return jwt.encode(claims, signing_secret, algorithm="HS256")


def test_case_scoped_signed_service_assertion_is_required():
    request = _request()
    assert (
        _verified_machine_actor(_assertion(request), SECRET, request)
        == "trusted-avery-service"
    )


@pytest.mark.parametrize(
    "changed",
    [
        {"case_id": "OTHER"},
        {"option_id": "OTHER"},
        {"slot_id": str(uuid4())},
        {"scope": "va_primary_care:read"},
        {"role": "SCHEDULER"},
        {"synthetic": False},
        {"idempotency_key": "different-request"},
        {"identity_verified": False},
        {"identity_case_id": "OTHER"},
        {"identity_verification_id": ""},
        {"veteran_confirmation_id": ""},
        {"veteran_confirmation_id": "not-a-uuid"},
        {"policy_version": "OLD_POLICY"},
        {"policy_decision": "DENY"},
        {"policy_evidence_reference": ""},
        {"human_review_required": True},
        {"jti": ""},
        {"iss": "untrusted"},
        {"aud": "untrusted"},
        {"exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
    ],
)
def test_signed_assertions_fail_closed_before_any_database_access(changed):
    request = _request()

    def never_connect():
        pytest.fail("Unauthorized assertion reached the database")

    with pytest.raises(PermissionError):
        commit_internal_va_booking(
            never_connect,
            assertion=_assertion(request, **changed),
            verifier_secret=SECRET,
            request=request,
        )


def test_missing_verifier_fails_before_database_access():
    request = _request()
    with pytest.raises(PermissionError):
        readback_internal_va_booking(
            lambda: pytest.fail("Unexpected DB access"),
            assertion=_assertion(request),
            verifier_secret="short",
            request=request,
        )


def test_tampered_assertion_fails_closed():
    request = _request()
    assertion = _assertion(request)
    with pytest.raises(PermissionError):
        commit_internal_va_booking(
            lambda: pytest.fail("Unexpected DB access"),
            assertion=assertion[:-2] + "xx",
            verifier_secret=SECRET,
            request=request,
        )


def test_no_issuer_or_public_mcp_side_effect():
    # Contract guard: there is no token minting, public MCP decorator or route.
    import inspect

    from veteran_access_bridge.services import pg_governed_va_commit as mod

    contents = inspect.getsource(mod)
    assert "@mcp.tool" not in contents
    assert "jwt.encode(" not in contents
    assert "commit_synthetic_eps_booking(" not in contents


class _ScriptedCursor:
    """Read-only connection stub: select results follow actual query sequence."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def fetchone(self):
        return self.rows.pop(0)

    def fetchall(self):
        return self.rows.pop(0)


class _ScriptedConnection:
    def __init__(self, rows):
        self.cur = _ScriptedCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def cursor(self):
        return self.cur


def _readback_with_rows(monkeypatch, request, rows, *, assertion=None):
    from veteran_access_bridge.services import pg_governed_va_commit as mod

    conn = _ScriptedConnection(rows)
    monkeypatch.setattr(
        mod,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )

    def execute(cur, schema, statement, params=None):
        assert schema == "vab_test"
        assert (
            "vab." in statement
        )  # existing repository-owned SQL rewriter handles isolation
        cur.statements.append((statement, params))

    monkeypatch.setattr(mod, "execute_scheduling_sql", execute)
    if assertion is None:
        confirmation_id = str(rows[3][0][0]) if len(rows) > 3 and rows[3] else None
        assertion = _assertion(
            request,
            **(
                {"veteran_confirmation_id": confirmation_id}
                if confirmation_id is not None
                else {}
            ),
        )
    claims = _verified_booking_claims(assertion, SECRET, request)
    return mod._readback(conn, request, claims), conn.cur


def _receipt_fixture(request, *, channel="VISTA", transition=True, audit=True):
    from veteran_access_bridge.services.pg_governed_va_commit import _ids

    appointment_id, _transition_id, _audit_id = _ids(request)
    start = datetime.now(timezone.utc) + timedelta(days=3)
    end = start + timedelta(minutes=30)
    patient_id = uuid4()
    veteran_id = uuid4()
    row = (
        appointment_id,
        "BOOKED_SIMULATED",
        "trusted-avery-service",
        request.slot_id,
        channel,
        "BOOKED",
        start,
        end,
        request.case_id,
        "PRIMARY_CARE",
        patient_id,
        patient_id,
        "Demo Primary Care",
        "Dr. Example",
    )
    evidence = {
        "synthetic": True,
        "care_pathway": "INTERNAL_VA",
        "appointment_id": str(appointment_id),
        "case_id": request.case_id,
        "option_id": request.option_id,
        "slot_id": str(request.slot_id),
        "idempotency_key": request.idempotency_key,
        "service_actor": "trusted-avery-service",
        "service_assertion_id": "assertion-1",
        "identity_verified": True,
        "identity_case_id": request.case_id,
        "identity_verification_id": "identity-verification-1",
        "identity_verification_expires_at": IDENTITY_EVIDENCE_EXPIRES_AT,
        "policy_version": POLICY_VERSION,
        "scheduler_approval_required": False,
        "authorization_mode": "TRUSTED_SERVICE_POLICY_GRANT",
        "policy_decision": "ALLOW",
        "policy_evidence_reference": "trusted-host-policy-evaluation-1",
        "human_review_required": False,
        "veteran_confirmation_id": str(veteran_id),
        "channel": channel,
    }
    veteran_evidence = {"service_evidence_reference": "veteran-confirmation"}
    decisions = [
        (
            veteran_id,
            "ACCEPTED",
            request.option_id,
            "VETERAN_CONFIRMED",
            "VETERAN",
            "trusted-veteran",
            1,
            veteran_evidence,
            uuid4(),
            "VETERAN_CONFIRMATION_RECORDED",
            "VETERAN",
            "trusted-veteran",
            veteran_evidence,
        ),
    ]
    return (
        row,
        ((evidence, "trusted-avery-service") if transition else None),
        ((evidence, "trusted-avery-service") if audit else None),
        start,
        end,
        decisions,
    )


def _decision_row(
    *,
    decision_id,
    option_id,
    kind,
    role,
    actor_id,
    order,
    event_type,
    status="ACCEPTED",
):
    evidence = {"service_evidence_reference": f"{kind.lower()}-evidence"}
    return (
        decision_id,
        status,
        option_id,
        kind,
        role,
        actor_id,
        order,
        evidence,
        uuid4(),
        event_type,
        role,
        actor_id,
        evidence,
    )


@pytest.mark.parametrize(
    "voice_rows",
    [
        "legacy",
        ("vs-call",) * 3,
        None,
        ("vs-other",) * 3,
        ("vs-call", "vs-other", "vs-call"),
    ],
)
def test_routine_primary_care_commit_needs_no_scheduler_approval(
    monkeypatch, voice_rows
):
    """Confirmed Veteran + signed ALLOW service grant can reach VA commit."""
    from veteran_access_bridge.services import pg_governed_va_commit as mod

    request = _request()
    now = datetime.now(timezone.utc)
    source_id = "VA-PC-SYNTHETIC-SOURCE"
    veteran = _decision_row(
        decision_id=uuid4(),
        option_id=request.option_id,
        kind="VETERAN_CONFIRMED",
        role="VETERAN",
        actor_id="trusted-veteran",
        order=1,
        event_type="VETERAN_CONFIRMATION_RECORDED",
    )
    case = (uuid4(), uuid4(), "PRIMARY_CARE", "OPEN", "PRIMARY_CARE", True)
    slot = (
        "VISTA",
        "AVAILABLE",
        now + timedelta(days=2),
        now + timedelta(days=2, minutes=30),
        now,
        source_id,
        "PRIMARY_CARE",
        True,
    )
    origin = (
        "synthetic_fixture",
        {
            "slot_bindings": {
                str(request.slot_id): {
                    "case_id": request.case_id,
                    "option_id": request.option_id,
                }
            }
        },
    )
    cursor = _ScriptedCursor([case, None, None, slot, origin, (now,), veteran])
    if voice_rows != "legacy":
        cursor.rows.append(voice_rows)
    cursor.rowcount = 1
    connection = _ScriptedConnection([])
    connection.cur = cursor
    monkeypatch.setattr(
        mod,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )

    def execute(cur, schema, statement, params=None):
        assert schema == "vab_test"
        cur.statements.append((statement, params))

    monkeypatch.setattr(mod, "execute_scheduling_sql", execute)
    monkeypatch.setattr(
        mod,
        "readback_internal_va_booking",
        lambda *_args, **_kwargs: mod.VABookingReceipt(
            "BOOKED_SIMULATED",
            request.case_id,
            "simulated-id",
            slot[2],
            slot[3],
            True,
        ),
    )
    claims = {"veteran_confirmation_id": str(veteran[0])}
    if voice_rows != "legacy":
        claims["voice_session_id"] = "vs-call"

    def commit():
        return commit_internal_va_booking(
            lambda: connection,
            assertion=_assertion(request, **claims),
            verifier_secret=SECRET,
            request=request,
        )

    if voice_rows not in ("legacy", ("vs-call",) * 3):
        with pytest.raises(PermissionError):
            commit()
        assert not any(q.startswith(("INSERT", "UPDATE")) for q, _ in cursor.statements)
        return
    receipt = commit()
    if voice_rows != "legacy":
        binding_index = next(
            i
            for i, (q, _) in enumerate(cursor.statements)
            if "SELECT i.correlation_id" in q
        )
        first_write = next(
            i
            for i, (q, _) in enumerate(cursor.statements)
            if q.startswith(("INSERT", "UPDATE"))
        )
        assert binding_index < first_write
        assert "FOR SHARE OF i,d,t" in cursor.statements[binding_index][0]
    assert receipt.verified is True
    sql = [statement for statement, _ in cursor.statements]
    assert not any("SCHEDULER_APPROVED" in statement for statement in sql)
    assert any(statement.startswith("INSERT INTO vab.appointment") for statement in sql)
    assert not any("EPS" in statement for statement in sql)
    assert not any("SCHEDULER" in statement for statement in sql)


def test_policy_grant_cannot_reuse_an_older_veteran_confirmation(monkeypatch):
    """The signed grant must identify the exact confirmation policy evaluated."""
    from veteran_access_bridge.services import pg_governed_va_commit as mod

    request = _request()
    now = datetime.now(timezone.utc)
    source_id = "VA-PC-SYNTHETIC-SOURCE"
    case = (uuid4(), uuid4(), "PRIMARY_CARE", "OPEN", "PRIMARY_CARE", True)
    slot = (
        "VISTA",
        "AVAILABLE",
        now + timedelta(days=2),
        now + timedelta(days=2, minutes=30),
        now,
        source_id,
        "PRIMARY_CARE",
        True,
    )
    origin = (
        "synthetic_fixture",
        {
            "slot_bindings": {
                str(request.slot_id): {
                    "case_id": request.case_id,
                    "option_id": request.option_id,
                }
            }
        },
    )
    old_confirmation_id = uuid4()
    latest_confirmation = _decision_row(
        decision_id=uuid4(),
        option_id=request.option_id,
        kind="VETERAN_CONFIRMED",
        role="VETERAN",
        actor_id="trusted-veteran",
        order=2,
        event_type="VETERAN_CONFIRMATION_RECORDED",
    )
    cursor = _ScriptedCursor(
        [case, None, None, slot, origin, (now,), latest_confirmation]
    )
    connection = _ScriptedConnection([])
    connection.cur = cursor
    monkeypatch.setattr(
        mod,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )
    monkeypatch.setattr(
        mod,
        "execute_scheduling_sql",
        lambda cur, schema, statement, params=None: cur.statements.append(
            (statement, params)
        ),
    )

    with pytest.raises(ValueError, match="confirmation evaluated by policy grant"):
        commit_internal_va_booking(
            lambda: connection,
            assertion=_assertion(
                request, veteran_confirmation_id=str(old_confirmation_id)
            ),
            verifier_secret=SECRET,
            request=request,
        )

    assert not any(
        statement.startswith(("UPDATE ", "INSERT "))
        for statement, _ in cursor.statements
    )


def test_booking_grant_expiring_during_lock_wait_cannot_commit(monkeypatch):
    from veteran_access_bridge.services import pg_governed_va_commit as mod

    request = _request()
    now = datetime.now(timezone.utc)
    slot = (
        "VISTA",
        "AVAILABLE",
        now + timedelta(days=2),
        now + timedelta(days=2, minutes=30),
        now,
        "source",
        "PRIMARY_CARE",
        True,
    )
    origin = (
        "synthetic_fixture",
        {
            "slot_bindings": {
                str(request.slot_id): {
                    "case_id": request.case_id,
                    "option_id": request.option_id,
                }
            }
        },
    )
    cursor = _ScriptedCursor(
        [
            (uuid4(), uuid4(), "PRIMARY_CARE", "OPEN", "PRIMARY_CARE", True),
            None,
            None,
            slot,
            origin,
            (now + timedelta(minutes=3),),
        ]
    )
    connection = _ScriptedConnection([])
    connection.cur = cursor
    monkeypatch.setattr(
        mod, "assert_synthetic_scheduling_database", lambda *_a, **_kw: "vab_test"
    )
    monkeypatch.setattr(
        mod,
        "execute_scheduling_sql",
        lambda cur, schema, statement, params=None: cur.statements.append(
            (statement, params)
        ),
    )

    with pytest.raises(PermissionError, match="expired while awaiting lock"):
        commit_internal_va_booking(
            lambda: connection,
            assertion=_assertion(request),
            verifier_secret=SECRET,
            request=request,
        )
    assert not any(
        statement.startswith(("UPDATE ", "INSERT "))
        for statement, _ in cursor.statements
    )


def test_unavailable_va_slot_never_creates_booking(monkeypatch):
    from veteran_access_bridge.services import pg_governed_va_commit as mod

    request = _request()
    now = datetime.now(timezone.utc)
    case = (uuid4(), uuid4(), "PRIMARY_CARE", "OPEN", "PRIMARY_CARE", True)
    unavailable_slot = (
        "VISTA",
        "BOOKED",
        now + timedelta(days=2),
        now + timedelta(days=2, minutes=30),
        now,
        "VA-PC-SYNTHETIC-SOURCE",
        "PRIMARY_CARE",
        True,
    )
    cursor = _ScriptedCursor([case, None, None, unavailable_slot])
    connection = _ScriptedConnection([])
    connection.cur = cursor
    monkeypatch.setattr(
        mod,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )
    monkeypatch.setattr(
        mod,
        "execute_scheduling_sql",
        lambda cur, schema, statement, params=None: cur.statements.append(
            (statement, params)
        ),
    )

    with pytest.raises(ValueError, match="slot unavailable"):
        commit_internal_va_booking(
            lambda: connection,
            assertion=_assertion(request),
            verifier_secret=SECRET,
            request=request,
        )

    assert not any(
        statement.startswith(("UPDATE ", "INSERT "))
        for statement, _ in cursor.statements
    )


def test_rejected_latest_veteran_confirmation_never_creates_booking(monkeypatch):
    from veteran_access_bridge.services import pg_governed_va_commit as mod

    request = _request()
    now = datetime.now(timezone.utc)
    source_id = "VA-PC-SYNTHETIC-SOURCE"
    case = (uuid4(), uuid4(), "PRIMARY_CARE", "OPEN", "PRIMARY_CARE", True)
    slot = (
        "VISTA",
        "AVAILABLE",
        now + timedelta(days=2),
        now + timedelta(days=2, minutes=30),
        now,
        source_id,
        "PRIMARY_CARE",
        True,
    )
    origin = (
        "synthetic_fixture",
        {
            "slot_bindings": {
                str(request.slot_id): {
                    "case_id": request.case_id,
                    "option_id": request.option_id,
                }
            }
        },
    )
    rejected_confirmation = _decision_row(
        decision_id=uuid4(),
        option_id=request.option_id,
        kind="VETERAN_CONFIRMED",
        role="VETERAN",
        actor_id="trusted-veteran",
        order=2,
        event_type="VETERAN_CONFIRMATION_RECORDED",
        status="REJECTED",
    )
    cursor = _ScriptedCursor(
        [case, None, None, slot, origin, (now,), rejected_confirmation]
    )
    connection = _ScriptedConnection([])
    connection.cur = cursor
    monkeypatch.setattr(
        mod,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )
    monkeypatch.setattr(
        mod,
        "execute_scheduling_sql",
        lambda cur, schema, statement, params=None: cur.statements.append(
            (statement, params)
        ),
    )

    with pytest.raises(ValueError, match="Latest verified Veteran consent"):
        commit_internal_va_booking(
            lambda: connection,
            assertion=_assertion(request),
            verifier_secret=SECRET,
            request=request,
        )

    assert not any(
        statement.startswith(("UPDATE ", "INSERT "))
        for statement, _ in cursor.statements
    )


def test_idempotent_receipt_is_recovered_after_request_closure(monkeypatch):
    from veteran_access_bridge.services import pg_governed_va_commit as mod

    request = _request()
    appointment, transition, audit, _, _, decisions = _receipt_fixture(request)
    closed_case = (
        uuid4(),
        uuid4(),
        "PRIMARY_CARE",
        "CLOSED",
        "PRIMARY_CARE",
        True,
    )
    cursor = _ScriptedCursor(
        [closed_case, (appointment[0],), appointment, transition, audit, decisions]
    )
    connection = _ScriptedConnection([])
    connection.cur = cursor
    monkeypatch.setattr(
        mod,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )

    def execute(cur, schema, statement, params=None):
        assert schema == "vab_test"
        cur.statements.append((statement, params))

    monkeypatch.setattr(mod, "execute_scheduling_sql", execute)
    receipt = commit_internal_va_booking(
        lambda: connection,
        assertion=_assertion(request, veteran_confirmation_id=str(decisions[0][0])),
        verifier_secret=SECRET,
        request=request,
    )

    assert receipt.verified is True
    assert receipt.appointment_id == str(appointment[0])
    assert "WHERE a.idempotency_key=%s" in cursor.statements[2][0]
    assert not any(
        statement.startswith(("UPDATE ", "INSERT "))
        for statement, _ in cursor.statements
    )


def test_readback_only_confirms_complete_matching_va_receipt(monkeypatch):
    request = _request()
    appointment, transition, audit, starts, ends, decisions = _receipt_fixture(request)
    receipt, cursor = _readback_with_rows(
        monkeypatch,
        request,
        [appointment, transition, audit, decisions],
    )
    assert receipt.verified is True
    assert receipt.state == "BOOKED_SIMULATED"
    assert receipt.begins_at == starts
    assert receipt.ends_at == ends
    assert len(cursor.statements) == 4


def test_readback_rejects_policy_grant_bound_to_another_confirmation(monkeypatch):
    request = _request()
    appointment, transition, audit, _, _, decisions = _receipt_fixture(request)

    with pytest.raises(ValueError, match="atomic audit evidence"):
        _readback_with_rows(
            monkeypatch,
            request,
            [appointment, transition, audit, decisions],
            assertion=_assertion(request, veteran_confirmation_id=str(uuid4())),
        )


def test_readback_accepts_fresh_grant_with_same_confirmation_for_recovery(
    monkeypatch,
):
    request = _request()
    appointment, transition, audit, _, _, decisions = _receipt_fixture(request)
    assertion = _assertion(
        request,
        jti="recovery-assertion-2",
        veteran_confirmation_id=str(decisions[0][0]),
    )

    receipt, _ = _readback_with_rows(
        monkeypatch,
        request,
        [appointment, transition, audit, decisions],
        assertion=assertion,
    )

    assert receipt.verified is True
    assert receipt.appointment_id == str(appointment[0])


@pytest.mark.parametrize(
    "channel,with_transition,with_audit",
    [
        ("EPS", True, True),
        ("VISTA", False, True),
        ("VISTA", True, False),
    ],
)
def test_readback_rejects_non_va_or_missing_atomic_evidence(
    monkeypatch, channel, with_transition, with_audit
):
    request = _request()
    appointment, transition, audit, _, _, _ = _receipt_fixture(
        request,
        channel=channel,
        transition=with_transition,
        audit=with_audit,
    )
    with pytest.raises(ValueError):
        _readback_with_rows(monkeypatch, request, [appointment, transition, audit])


def test_no_record_is_not_a_booking(monkeypatch):
    request = _request()
    receipt, cursor = _readback_with_rows(monkeypatch, request, [None])
    assert receipt.verified is False
    assert receipt.appointment_id is None
    assert receipt.state == "NOT_FOUND_UNCONFIRMED"
    assert len(cursor.statements) == 1


@pytest.mark.parametrize(
    "call_id", [None, "", " ", " vs-call", "x" * 129, 42, "vs\ncall"]
)
def test_invalid_voice_grant_never_accesses_database(call_id):
    request = _request()
    with pytest.raises(PermissionError, match="voice session"):
        commit_internal_va_booking(
            lambda: pytest.fail("Invalid call reached the database"),
            assertion=_assertion(request, voice_session_id=call_id),
            verifier_secret=SECRET,
            request=request,
        )


@pytest.mark.parametrize(
    "correlations", [None, ("other",) * 3, ("vs-call", "other", "vs-call")]
)
def test_voice_readback_rejects_cross_call_evidence(monkeypatch, correlations):
    request = _request()
    row, transition, audit, _, _, decisions = _receipt_fixture(request)
    transition[0]["voice_session_id"] = "vs-call"
    assertion = _assertion(
        request,
        voice_session_id="vs-call",
        veteran_confirmation_id=str(decisions[0][0]),
    )
    with pytest.raises(PermissionError, match="signed call"):
        _readback_with_rows(
            monkeypatch,
            request,
            [row, transition, audit, decisions, correlations],
            assertion=assertion,
        )


def test_voice_readback_requires_original_call_and_returns_it(monkeypatch):
    request = _request()
    row, transition, audit, _, _, decisions = _receipt_fixture(request)
    transition[0]["voice_session_id"] = "vs-call"
    with pytest.raises(PermissionError, match="original signed call"):
        _readback_with_rows(monkeypatch, request, [row, transition, audit, decisions])
    assertion = _assertion(
        request,
        voice_session_id="vs-call",
        veteran_confirmation_id=str(decisions[0][0]),
    )
    receipt, cursor = _readback_with_rows(
        monkeypatch,
        request,
        [row, transition, audit, decisions, ("vs-call",) * 3],
        assertion=assertion,
    )
    assert receipt.verified and receipt.voice_session_id == "vs-call"
    assert all("FOR SHARE" not in sql for sql, _ in cursor.statements)
