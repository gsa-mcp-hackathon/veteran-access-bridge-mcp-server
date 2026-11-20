"""Offline tests for private host auth, identity evidence, and policy evaluation."""

import json
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4, uuid5

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from veteran_access_bridge.adapters.synthetic_ids import (
    VAB_SYNTHETIC_NAMESPACE,
    resolve_case_identifiers,
)
from veteran_access_bridge.mcp.cases import load_demo_encounter_case
from veteran_access_bridge.services import trusted_primary_care as trusted
from veteran_access_bridge.services.pg_governed_va_commit import SCOPE, VABookingRequest
from veteran_access_bridge.services.private_va_booking_grant_issuer import (
    AuthenticatedService,
)

ISSUER = "https://issuer.example.test"
AUDIENCE = "vab-primary-care-test"
SUBJECT = "trusted-vab-host"
CASE_ID = "TEST-VA-PC-001"


class FakeCursor:
    def __init__(self, *, values=None):
        self.values = values or {}
        self.last_statement = ""
        self.last_params = None
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        self.last_statement = statement
        self.last_params = params
        self.statements.append((statement, params))

    def fetchone(self):
        for prefix, value in self.values.items():
            if self.last_statement.startswith(prefix):
                return value
        raise AssertionError(f"Unexpected query: {self.last_statement}")


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


def _key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return private_pem, public_key


class FakeReplayGuard(trusted.PostgresHostAssertionReplayGuard):
    def __init__(self):
        self.consumed = set()

    def consume(self, *, issuer, subject, token_id, expires_at):
        key = (issuer, subject, token_id)
        if key in self.consumed:
            raise PermissionError("Host assertion expired or already consumed")
        self.consumed.add(key)


def _authenticator(public_key, replay_guard=None):
    return trusted.TrustedHostAuthenticator(
        issuer=ISSUER,
        audience=AUDIENCE,
        subject=SUBJECT,
        public_key_pem=public_key,
        replay_guard=replay_guard or FakeReplayGuard(),
    )


def _host_assertion(private_key, *, scope=trusted.IDENTITY_SCOPE, **overrides):
    now = int(datetime.now(timezone.utc).timestamp())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": SUBJECT,
        "scope": scope,
        "case_ids": [CASE_ID],
        "jti": "host-token-" + str(uuid4()),
        "iat": now,
        "exp": now + 240,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def _request():
    return VABookingRequest(
        case_id=CASE_ID,
        option_id="OPTION-1",
        slot_id=uuid4(),
        idempotency_key="book-idempotency-1",
    )


def _decision_row(*, status="ACCEPTED", option_id="OPTION-1", kind="VETERAN_CONFIRMED"):
    decision_id = uuid4()
    evidence = {"service_evidence_reference": "VA-PC-SOURCE"}
    return (
        decision_id,
        status,
        option_id,
        kind,
        "VETERAN",
        "synthetic-veteran",
        7,
        evidence,
        uuid4(),
        "VETERAN_CONFIRMATION_RECORDED",
        "VETERAN",
        "synthetic-veteran",
        evidence,
    )


def _policy_cursor(
    request,
    now,
    *,
    case=None,
    identity=None,
    decision=None,
    slot=None,
    conflict=False,
):
    patient_id = uuid4()
    identity_id = uuid4()
    verified_at = now - timedelta(seconds=30)
    if case is None:
        case = (uuid4(), patient_id, "PRIMARY_CARE", "OPEN", "PRIMARY_CARE", True)
    if identity is None:
        identity = (
            identity_id,
            "identity-correlation-1",
            SUBJECT,
            verified_at,
            {
                "identity_verification_id": str(identity_id),
                "case_id": request.case_id,
                "patient_id": str(patient_id),
                "synthetic": True,
                "verification_method": trusted.IDENTITY_METHOD,
                "verification_source": "PERSISTED_SYNTHETIC_CASE",
                "verified": True,
                "outcome": "VERIFIED",
                "verifying_principal": SUBJECT,
                "verified_at": verified_at.isoformat(),
                "expires_at": (verified_at + trusted.IDENTITY_TTL).isoformat(),
            },
        )
    if decision is None:
        decision = _decision_row()
    if slot is None:
        slot = (
            "VISTA",
            "AVAILABLE",
            now + timedelta(days=2),
            now + timedelta(days=2, minutes=30),
            now - timedelta(seconds=15),
            "VA-PC-SOURCE",
            "PRIMARY_CARE",
            True,
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
    values = {
        "SELECT l.request_id": case,
        "SELECT event_id,correlation_id": identity,
        "SELECT d.decision_id": decision,
        "SELECT s.channel": slot,
        "SELECT EXISTS": (conflict,),
    }
    return FakeCursor(values=values)


def _patch_db(monkeypatch, cursor):
    monkeypatch.setattr(
        trusted,
        "assert_synthetic_scheduling_database",
        lambda *_args, **_kwargs: "vab_test",
    )
    monkeypatch.setattr(
        trusted,
        "execute_scheduling_sql",
        lambda cur, _schema, statement, params=None: cur.execute(statement, params),
    )
    return lambda: FakeConnection(cursor)


def test_trusted_host_authenticator_verifies_subject_scope_and_case_scope():
    private_key, public_key = _key_pair()
    authenticator = _authenticator(public_key)
    principal = authenticator.authenticate_identity(_host_assertion(private_key))

    assert principal == AuthenticatedService(
        subject=SUBJECT,
        authenticated=True,
        scope=trusted.IDENTITY_SCOPE,
        case_ids=frozenset({CASE_ID}),
    )


def test_trusted_host_authenticator_rejects_replayed_assertion():
    private_key, public_key = _key_pair()
    authenticator = _authenticator(public_key)
    assertion = _host_assertion(private_key)

    authenticator.authenticate_identity(assertion)
    with pytest.raises(PermissionError, match="already consumed"):
        authenticator.authenticate_identity(assertion)


def test_trusted_host_authenticator_accepts_fractional_numeric_dates():
    private_key, public_key = _key_pair()
    now = datetime.now(timezone.utc).timestamp()
    assertion = _host_assertion(private_key, iat=now - 1, exp=now + 60)

    assert _authenticator(public_key).authenticate_identity(assertion).authenticated


def test_postgres_replay_guard_uses_atomic_unique_insert(monkeypatch):
    class ReplayCursor(FakeCursor):
        def __init__(self):
            super().__init__()
            self.consumed = set()

        def fetchone(self):
            if self.last_statement.startswith("SELECT clock_timestamp()"):
                return (True,)
            event_id = self.last_params[0]
            if event_id in self.consumed:
                return None
            self.consumed.add(event_id)
            return (event_id,)

    cursor = ReplayCursor()
    guard = trusted.PostgresHostAssertionReplayGuard(_patch_db(monkeypatch, cursor))
    args = {
        "issuer": ISSUER,
        "subject": SUBJECT,
        "token_id": "test-token-id",
        "expires_at": int(datetime.now(timezone.utc).timestamp()) + 60,
    }

    guard.consume(**args)
    restarted_guard = trusted.PostgresHostAssertionReplayGuard(
        _patch_db(monkeypatch, cursor)
    )
    with pytest.raises(PermissionError, match="already consumed"):
        restarted_guard.consume(**args)
    insert_statement, insert_params = cursor.statements[-1]
    assert "ON CONFLICT (event_id) DO NOTHING RETURNING event_id" in insert_statement
    assert "clock_timestamp() < to_timestamp(%s)" in insert_statement
    assert "test-token-id" not in json.dumps(insert_params[-2])


def test_replay_guard_rechecks_expiry_after_insert(monkeypatch):
    cursor = FakeCursor(
        values={
            "INSERT INTO vab.audit_event": (uuid4(),),
            "SELECT clock_timestamp()": (False,),
        }
    )
    guard = trusted.PostgresHostAssertionReplayGuard(_patch_db(monkeypatch, cursor))

    with pytest.raises(PermissionError, match="expired while being consumed"):
        guard.consume(issuer=ISSUER, subject=SUBJECT, token_id="token", expires_at=1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "https://untrusted.example.test"},
        {"aud": "wrong-audience"},
        {"sub": "other-host"},
        {"scope": SCOPE},
        {"exp": int(datetime.now(timezone.utc).timestamp()) - 1},
        {"exp": int(datetime.now(timezone.utc).timestamp()) + 600},
        {"jti": ""},
        {"jti": "x" * 257},
        {"iat": True},
    ],
)
def test_trusted_host_authenticator_rejects_mismatched_or_expired_claims(overrides):
    private_key, public_key = _key_pair()
    replay_guard = FakeReplayGuard()
    authenticator = _authenticator(public_key, replay_guard)

    with pytest.raises(PermissionError):
        authenticator.authenticate_identity(_host_assertion(private_key, **overrides))
    assert not replay_guard.consumed


def test_trusted_host_authenticator_fails_closed_when_runtime_config_missing(
    monkeypatch,
):
    for key in (
        "VAB_TRUSTED_HOST_ISSUER",
        "VAB_TRUSTED_HOST_AUDIENCE",
        "VAB_TRUSTED_HOST_SUBJECT",
        "VAB_TRUSTED_HOST_PUBLIC_KEY_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(PermissionError, match="incomplete"):
        trusted.TrustedHostAuthenticator.from_environment()


def test_replay_guard_rejects_non_test_schema(monkeypatch):
    cursor = FakeCursor()
    connect = _patch_db(monkeypatch, cursor)
    monkeypatch.setattr(
        trusted, "assert_synthetic_scheduling_database", lambda *_a, **_kw: "vab"
    )
    guard = trusted.PostgresHostAssertionReplayGuard(connect)

    with pytest.raises(PermissionError, match="isolated test schema"):
        guard.consume(issuer=ISSUER, subject=SUBJECT, token_id="token", expires_at=1)
    assert not cursor.statements


def test_replay_guard_database_failure_does_not_authenticate(monkeypatch):
    class FailingConnection(FakeConnection):
        def __exit__(self, *_args):
            raise RuntimeError("replay storage unavailable")

    cursor = FakeCursor()
    _patch_db(monkeypatch, cursor)
    cursor.values["INSERT INTO vab.audit_event"] = (uuid4(),)
    cursor.values["SELECT clock_timestamp()"] = (True,)
    private_key, public_key = _key_pair()
    authenticator = trusted.TrustedHostAuthenticator(
        issuer=ISSUER,
        audience=AUDIENCE,
        subject=SUBJECT,
        public_key_pem=public_key,
        replay_guard=trusted.PostgresHostAssertionReplayGuard(
            lambda: FailingConnection(cursor)
        ),
    )

    with pytest.raises(RuntimeError, match="replay storage unavailable"):
        authenticator.authenticate_identity(_host_assertion(private_key))


def test_case_provisioning_uses_existing_fixture_patient_without_creating_one(
    monkeypatch,
):
    case_id = "DEMO-PC-5000335-001"
    identifiers = resolve_case_identifiers(case_id)
    patient, _ = load_demo_encounter_case(case_id)
    cursor = FakeCursor(
        values={
            "SELECT p.display_name": (
                patient.display_name,
                date.fromisoformat(patient.birth_date),
                True,
                patient.patient_id,
                "sandbox",
            ),
            "SELECT l.request_id": None,
        }
    )
    connect = _patch_db(monkeypatch, cursor)
    private_key, public_key = _key_pair()
    assertion = _host_assertion(
        private_key, scope=trusted.CASE_PROVISION_SCOPE, case_ids=[case_id]
    )

    receipt = trusted.ensure_existing_synthetic_primary_care_case(
        connect, _authenticator(public_key), assertion=assertion, case_id=case_id
    )

    assert receipt.created
    assert receipt.patient_id == identifiers.patient_uuid
    assert receipt.request_id == identifiers.request_uuid
    statements = [sql for sql, _params in cursor.statements]
    assert any(
        sql.startswith("INSERT INTO vab.appointment_request") for sql in statements
    )
    assert any(
        sql.startswith("INSERT INTO vab.scheduling_case_link") for sql in statements
    )
    assert any(sql.startswith("INSERT INTO vab.audit_event") for sql in statements)
    assert not any(sql.startswith("INSERT INTO vab.patient") for sql in statements)


@pytest.mark.parametrize(
    "patient_row", [None, ("Wrong", date(2000, 1, 1), True, "x", "sandbox")]
)
def test_case_provisioning_rejects_missing_or_mismatched_patient(
    monkeypatch, patient_row
):
    case_id = "DEMO-PC-5000335-001"
    cursor = FakeCursor(values={"SELECT p.display_name": patient_row})
    connect = _patch_db(monkeypatch, cursor)
    private_key, public_key = _key_pair()
    assertion = _host_assertion(
        private_key, scope=trusted.CASE_PROVISION_SCOPE, case_ids=[case_id]
    )

    with pytest.raises(ValueError, match="fixture patient required"):
        trusted.ensure_existing_synthetic_primary_care_case(
            connect, _authenticator(public_key), assertion=assertion, case_id=case_id
        )
    assert not any(sql.startswith("INSERT") for sql, _params in cursor.statements)


def test_case_provisioning_requires_exact_host_case_scope(monkeypatch):
    cursor = FakeCursor()
    connect = _patch_db(monkeypatch, cursor)
    private_key, public_key = _key_pair()
    assertion = _host_assertion(private_key, scope=trusted.CASE_PROVISION_SCOPE)

    with pytest.raises(PermissionError, match="not scoped"):
        trusted.ensure_existing_synthetic_primary_care_case(
            connect,
            _authenticator(public_key),
            assertion=assertion,
            case_id="DEMO-PC-5000335-001",
        )
    assert not cursor.statements


@pytest.mark.parametrize("audit_matches", [True, False])
def test_case_provisioning_requires_existing_case_provenance(
    monkeypatch, audit_matches
):
    case_id = "DEMO-PC-5000335-001"
    ids = resolve_case_identifiers(case_id)
    patient, _ = load_demo_encounter_case(case_id)
    provenance = {
        "synthetic": True,
        "fixture_case_id": case_id,
        "fixture_request_id": ids.request_external_id,
    }
    audit = (
        "case-provision:" + case_id,
        "SYNTHETIC_CASE_PROVISIONED",
        {
            **provenance,
            "request_id": str(ids.request_uuid),
            "patient_id": str(ids.patient_uuid),
        },
    )
    cursor = FakeCursor(
        values={
            "SELECT p.display_name": (
                patient.display_name,
                date.fromisoformat(patient.birth_date),
                True,
                patient.patient_id,
                "sandbox",
            ),
            "SELECT l.request_id": (
                ids.request_uuid,
                ids.request_external_id,
                "SYNTHETIC_MCP",
                True,
                ids.patient_uuid,
                "PRIMARY_CARE",
                "PRIMARY_CARE",
                "OPEN",
                provenance,
            ),
            "SELECT correlation_id,event_type,details": audit
            if audit_matches
            else None,
        }
    )
    connect = _patch_db(monkeypatch, cursor)
    private_key, public_key = _key_pair()
    assertion = _host_assertion(
        private_key, scope=trusted.CASE_PROVISION_SCOPE, case_ids=[case_id]
    )
    if audit_matches:
        receipt = trusted.ensure_existing_synthetic_primary_care_case(
            connect, _authenticator(public_key), assertion=assertion, case_id=case_id
        )
        assert not receipt.created
        assert receipt.audit_event_id == uuid5(
            VAB_SYNTHETIC_NAMESPACE, "case-provision:" + case_id
        )
    else:
        with pytest.raises(ValueError, match="matching provenance"):
            trusted.ensure_existing_synthetic_primary_care_case(
                connect,
                _authenticator(public_key),
                assertion=assertion,
                case_id=case_id,
            )
    assert not any(sql.startswith("INSERT") for sql, _params in cursor.statements)


def test_coordinator_builder_fails_closed_without_trusted_host_config(monkeypatch):
    for key in (
        "VAB_TRUSTED_HOST_ISSUER",
        "VAB_TRUSTED_HOST_AUDIENCE",
        "VAB_TRUSTED_HOST_SUBJECT",
        "VAB_TRUSTED_HOST_PUBLIC_KEY_PATH",
        "VAB_PRIVATE_VA_BOOKING_SIGNING_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(PermissionError, match="incomplete"):
        trusted.build_trusted_primary_care_coordinator(object())


def test_identity_verification_is_persisted_without_raw_answers(monkeypatch):
    private_key, public_key = _key_pair()
    authenticator = _authenticator(public_key)
    now = datetime.now(timezone.utc)
    patient_id = uuid4()
    cursor = FakeCursor(
        values={
            "SELECT p.patient_id": (
                patient_id,
                "Ms Ada Lovelace",
                date(1980, 9, 10),
                True,
            )
        }
    )
    connect = _patch_db(monkeypatch, cursor)

    receipt = trusted.verify_and_record_synthetic_identity(
        connect,
        authenticator,
        assertion=_host_assertion(private_key),
        case_id=CASE_ID,
        full_name="Ada Lovelace",
        birth_date="9/10/1980",
        correlation_id="identity-correlation-1",
        now=now,
    )

    assert receipt.verified is True
    assert receipt.patient_id == patient_id
    assert receipt.expires_at == now + trusted.IDENTITY_TTL
    insert, params = next(
        item for item in cursor.statements if item[0].startswith("INSERT INTO")
    )
    assert "vab.audit_event" in insert
    details = json.loads(params[-1])
    assert details["identity_verification_id"] == str(receipt.event_id)
    assert details["verifying_principal"] == SUBJECT
    assert details["verified"] is True
    assert "Ada" not in params[-1]
    assert "1980-09-10" not in params[-1]


def test_identity_mismatch_is_recorded_but_untrusted_case_is_not_written(monkeypatch):
    private_key, public_key = _key_pair()
    authenticator = _authenticator(public_key)
    patient_id = uuid4()
    cursor = FakeCursor(
        values={
            "SELECT p.patient_id": (
                patient_id,
                "Ms Ada Lovelace",
                date(1980, 9, 10),
                True,
            )
        }
    )
    connect = _patch_db(monkeypatch, cursor)
    receipt = trusted.verify_and_record_synthetic_identity(
        connect,
        authenticator,
        assertion=_host_assertion(private_key),
        case_id=CASE_ID,
        full_name="Different Synthetic Person",
        birth_date="9/10/1980",
        correlation_id="identity-correlation-2",
        now=datetime.now(timezone.utc),
    )
    assert receipt.verified is False
    details = json.loads(cursor.statements[-1][1][-1])
    assert details["outcome"] == "NO_MATCH"

    out_of_scope = _authenticator(public_key)
    wrong_case_assertion = _host_assertion(private_key, case_ids=["ANOTHER-CASE"])

    def no_database_call():
        pytest.fail("database must not be accessed")

    with pytest.raises(PermissionError, match="not scoped"):
        trusted.verify_and_record_synthetic_identity(
            no_database_call,
            out_of_scope,
            assertion=wrong_case_assertion,
            case_id=CASE_ID,
            full_name="Ada Lovelace",
            birth_date="1980-09-10",
            correlation_id="identity-correlation-3",
        )


def test_policy_evaluator_allows_only_current_persisted_evidence(monkeypatch):
    request = _request()
    now = datetime.now(timezone.utc)
    cursor = _policy_cursor(request, now)
    connect = _patch_db(monkeypatch, cursor)
    evaluator = trusted.PostgresPrimaryCarePolicyEvaluator(
        connect,
        clock=lambda: now,
    )
    actor = AuthenticatedService(
        SUBJECT,
        True,
        SCOPE,
        frozenset({request.case_id}),
    )

    policy = evaluator(request, actor)

    assert policy.decision == "ALLOW"
    assert policy.human_review_required is False
    assert policy.identity_verification_id
    assert policy.identity_verification_expires_at > now
    assert policy.veteran_confirmation_id
    assert policy.policy_evidence_reference.startswith("va-pc-policy:")
    assert all(
        not statement.startswith(("INSERT ", "UPDATE ", "DELETE "))
        for statement, _ in cursor.statements
    )


@pytest.mark.parametrize(
    ("case", "identity", "decision", "slot", "conflict", "expected"),
    [
        ("missing_case", None, None, None, False, "REVIEW"),
        (None, "missing", None, None, False, "REVIEW"),
        (None, "expired", None, None, False, "REVIEW"),
        (None, "failed_match", None, None, False, "REVIEW"),
        (None, "wrong_principal", None, None, False, "REVIEW"),
        (None, None, "rejected", None, False, "DENY"),
        (None, None, "wrong_option", None, False, "REVIEW"),
        (None, None, "new_selection", None, False, "REVIEW"),
        (None, None, "wrong_evidence_reference", None, False, "REVIEW"),
        (None, None, None, "eps", False, "DENY"),
        (None, None, None, "missing", False, "REVIEW"),
        (None, None, None, "stale", False, "REVIEW"),
        (None, None, None, "bad_provenance", False, "DENY"),
        (None, None, None, "wrong_binding", False, "DENY"),
        (None, None, None, None, True, "DENY"),
        ("specialty", None, None, None, False, "DENY"),
        ("closed", None, None, None, False, "DENY"),
        ("non_synthetic", None, None, None, False, "DENY"),
    ],
)
def test_policy_evaluator_fails_closed_for_invalid_persisted_evidence(
    monkeypatch, case, identity, decision, slot, conflict, expected
):
    request = _request()
    now = datetime.now(timezone.utc)
    patient_id = uuid4()
    case_row = (
        uuid4(),
        patient_id,
        "PRIMARY_CARE",
        "OPEN",
        "PRIMARY_CARE",
        True,
    )
    if case == "missing_case":
        case_row = None
    elif case == "specialty":
        case_row = (*case_row[:2], "SPECIALTY", *case_row[3:])
    elif case == "closed":
        case_row = (*case_row[:3], "CLOSED", *case_row[4:])
    elif case == "non_synthetic":
        case_row = (*case_row[:5], False)
    identity_row = None
    if identity != "missing":
        verified_at = now - timedelta(seconds=30)
        details = {
            "identity_verification_id": "",
            "case_id": request.case_id,
            "patient_id": str(patient_id),
            "synthetic": True,
            "verification_method": trusted.IDENTITY_METHOD,
            "verification_source": "PERSISTED_SYNTHETIC_CASE",
            "verified": True,
            "outcome": "VERIFIED",
            "verifying_principal": SUBJECT,
            "verified_at": verified_at.isoformat(),
            "expires_at": (verified_at + trusted.IDENTITY_TTL).isoformat(),
        }
        event_id = uuid4()
        details["identity_verification_id"] = str(event_id)
        if identity == "expired":
            details["expires_at"] = (now - timedelta(seconds=1)).isoformat()
        identity_row = (
            event_id,
            "identity-correlation",
            SUBJECT,
            verified_at,
            details,
        )
        if identity == "failed_match":
            identity_row[-1]["verified"] = False
            identity_row[-1]["outcome"] = "NO_MATCH"
        elif identity == "wrong_principal":
            identity_row = (*identity_row[:2], "different-principal", *identity_row[3:])
    decision_row = _decision_row()
    if decision == "rejected":
        decision_row = _decision_row(status="REJECTED")
    elif decision == "wrong_option":
        decision_row = _decision_row(option_id="OTHER-OPTION")
    elif decision == "new_selection":
        decision_row = _decision_row(kind="OPTION_SELECTED")
    elif decision == "wrong_evidence_reference":
        decision_values = list(decision_row)
        decision_evidence = dict(decision_values[7])
        decision_evidence["service_evidence_reference"] = "another-source"
        decision_values[7] = decision_evidence
        decision_values[12] = decision_evidence
        decision_row = tuple(decision_values)
    slot_row = None
    if slot != "missing":
        cursor = _policy_cursor(request, now)
        slot_row = cursor.values["SELECT s.channel"]
        if slot == "eps":
            slot_row = ("EPS", *slot_row[1:])
        elif slot == "missing":
            slot_row = None
        elif slot == "stale":
            slot_row = (
                *slot_row[:4],
                now - trusted.SLOT_FRESHNESS - timedelta(seconds=1),
                *slot_row[5:],
            )
        elif slot == "bad_provenance":
            slot_row = (*slot_row[:-2], "sandbox", slot_row[-1])
        elif slot == "wrong_binding":
            slot_row = (
                *slot_row[:-1],
                {
                    "slot_bindings": {
                        str(request.slot_id): {
                            "case_id": request.case_id,
                            "option_id": "OTHER-OPTION",
                        }
                    }
                },
            )
    values = {
        "SELECT l.request_id": case_row,
        "SELECT event_id,correlation_id": identity_row,
        "SELECT d.decision_id": decision_row,
        "SELECT s.channel": slot_row,
        "SELECT EXISTS": (conflict,),
    }
    fake_cursor = FakeCursor(values=values)
    connect = _patch_db(monkeypatch, fake_cursor)
    actor = AuthenticatedService(SUBJECT, True, SCOPE, frozenset({request.case_id}))
    policy = trusted.PostgresPrimaryCarePolicyEvaluator(
        connect,
        clock=lambda: now,
    )(request, actor)

    assert policy.decision == expected


def test_policy_evaluator_rejects_actor_without_case_scope_before_db_access():
    request = _request()
    actor = AuthenticatedService(SUBJECT, True, SCOPE, frozenset({"OTHER-CASE"}))
    evaluator = trusted.PostgresPrimaryCarePolicyEvaluator(
        lambda: pytest.fail("database must not be accessed")
    )

    with pytest.raises(PermissionError, match="case scope"):
        evaluator(request, actor)


def test_private_identity_and_policy_adapters_are_not_public_routes():
    import inspect

    source = inspect.getsource(trusted)
    assert "@mcp.tool" not in source
    assert "@app.post" not in source
