from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from veteran_access_bridge.services import booking_crm as mod


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("VAB_ENABLE_CRM", "true")
    now = datetime.now(timezone.utc)
    receipt = dict(
        verified=True,
        synthetic=True,
        state="BOOKED_SIMULATED",
        case_id="case",
        voice_session_id="vs-test",
        appointment_id=str(uuid4()),
        begins_at=now,
        ends_at=now + timedelta(minutes=30),
    )
    conn, cur = MagicMock(), MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.side_effect = [(1,), None]
    monkeypatch.setattr(mod, "connect_private_supabase_test_scheduling", lambda: conn)
    args = dict(
        case_id="case",
        interaction_id="int-test",
        voice_session_id="vs-test",
        verify=lambda: receipt,
    )
    return receipt, conn, cur, args


def test_note_uses_only_verified_receipt_and_labels_host(setup):
    receipt, conn, cur, args = setup
    result = mod.record_booking_note(**args)
    assert result["persisted"] and result["invoked_by"] == "host"
    assert result["appointment_id"] == receipt["appointment_id"]
    assert result["booking_created"] is False
    queries = cur.execute.call_args_list
    inserts = [x.args for x in queries if x.args[0].startswith("INSERT")]
    assert len(inserts) == 2
    assert "Automatic trusted booking-service" in inserts[0][1][3]
    assert "pg_advisory_xact_lock" in queries[2].args[0]
    assert conn.__exit__.call_args.args[0] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("verified", False),
        ("synthetic", False),
        ("state", "PENDING"),
        ("case_id", "other"),
        ("voice_session_id", "vs-other"),
    ],
)
def test_unverified_or_cross_call_cannot_write(setup, field, value):
    receipt, conn, cur, args = setup
    receipt[field] = value
    with pytest.raises(PermissionError):
        mod.record_booking_note(**args)
    cur.execute.assert_not_called()


def test_disabled_cannot_write(setup, monkeypatch):
    _, _, cur, args = setup
    monkeypatch.delenv("VAB_ENABLE_CRM")
    with pytest.raises(PermissionError):
        mod.record_booking_note(**args)
    cur.execute.assert_not_called()


def test_retry_returns_same_note_and_does_not_insert(setup):
    _, _, cur, args = setup
    first = mod.record_booking_note(**args)
    event_insert = cur.execute.call_args_list[-1].args[1]
    digest = event_insert[5]
    cur.reset_mock()
    cur.fetchone.side_effect = [(1,), (digest, first)]
    again = mod.record_booking_note(**args)
    assert again == {**first, "replayed": True}
    assert not any(x.args[0].startswith("INSERT") for x in cur.execute.call_args_list)


def test_changed_booking_or_revocation_rolls_back(setup):
    receipt, conn, _, args = setup
    checks = iter([receipt, {**receipt, "verified": False}])
    args["verify"] = lambda: next(checks)
    with pytest.raises(PermissionError):
        mod.record_booking_note(**args)
    assert conn.__exit__.call_args.args[0] is PermissionError


def test_conflicting_existing_summary_rejected(setup):
    _, _, cur, args = setup
    cur.fetchone.side_effect = [(1,), ("different", {})]
    with pytest.raises(ValueError, match="conflict"):
        mod.record_booking_note(**args)
    assert not any(x.args[0].startswith("INSERT") for x in cur.execute.call_args_list)
