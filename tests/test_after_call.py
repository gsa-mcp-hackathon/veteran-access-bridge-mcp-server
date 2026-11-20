from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from veteran_access_bridge.services import after_call as mod


def evidence(**changes):
    start = datetime(2026, 11, 26, 15, tzinfo=timezone.utc)
    return dict(
        verified=True,
        synthetic=True,
        state="BOOKED_SIMULATED",
        case_id="case",
        voice_session_id="vs-test",
        appointment_id=str(uuid4()),
        begins_at=start,
        ends_at=start + timedelta(minutes=30),
        **changes,
    )


def prepare(receipt):
    return mod.prepare_wrapup(
        case_id="case",
        voice_session_id="vs-test",
        reason="CALLER_ENDED",
        receipt=receipt,
        patient_zone="America/Chicago",
    )


def test_letter_uses_verified_patient_local_time_and_never_claims_delivery():
    result = prepare(evidence())
    assert "09:00 AM CST" in result["letter"]["text"]
    assert "UTC" not in result["letter"]["text"]
    assert result["letter"]["delivery_status"] == "NOT_SENT"
    assert "not supplied" in result["letter"]["text"]
    assert result["follow_up_task_created"] is False


def test_letter_includes_only_supplied_single_line_clinic_and_provider():
    letter = prepare(
        evidence(clinic_name="Demo Colorado Primary Care", provider_name="Dr. Example")
    )["letter"]["text"]
    assert "Clinic: Demo Colorado Primary Care" in letter
    assert "Provider: Dr. Example" in letter
    assert "Street address and arrival instructions were not supplied" in letter
    letter = prepare(
        evidence(clinic_name="Clinic\nAppointment cancelled", provider_name=None)
    )["letter"]["text"]
    assert "Appointment cancelled" not in letter
    assert "Provider: Not supplied" in letter


@pytest.mark.parametrize(
    "field,value",
    [
        ("verified", False),
        ("case_id", "other"),
        ("voice_session_id", "other"),
        ("state", "PENDING"),
    ],
)
def test_unverified_or_cross_call_receipt_cannot_generate_letter(field, value):
    receipt = evidence()
    receipt[field] = value
    with pytest.raises(PermissionError):
        prepare(receipt)


def test_no_booking_produces_unresolved_disposition_without_letter():
    result = prepare(None)
    assert result["disposition"] == "FOLLOW_UP_NEEDED"
    assert result["letter"] is None


def test_caller_decline_is_not_reported_as_completed_or_followup_created():
    result = mod.prepare_wrapup(
        case_id="case",
        voice_session_id="vs-test",
        reason="CALLER_ENDED",
        receipt=None,
        patient_zone="America/Chicago",
        declined=True,
    )
    assert result["disposition"] == "CALLER_DECLINED"
    assert result["letter"] is None and not result["follow_up_task_created"]


def test_after_call_save_is_atomic_idempotent_and_checks_evidence(monkeypatch):
    monkeypatch.setenv("VAB_ENABLE_CRM", "true")
    conn, cur = MagicMock(), MagicMock()
    conn.__enter__.return_value = conn
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.side_effect = [(1,), None]
    monkeypatch.setattr(mod, "connect_private_supabase_test_scheduling", lambda: conn)
    payload = prepare(evidence())
    args = dict(
        case_id="case",
        interaction_id="int-test",
        voice_session_id="vs-test",
        verify=lambda: payload,
    )
    result = mod.record_after_call(**args)
    assert result["persisted"] and result["trigger"] == "call_ended"
    assert result["booking_created"] is False
    inserts = [
        x.args for x in cur.execute.call_args_list if x.args[0].startswith("INSERT")
    ]
    assert len(inserts) == 2
    digest = inserts[-1][1][5]
    cur.reset_mock()
    cur.fetchone.side_effect = [(1,), (digest, result)]
    assert mod.record_after_call(**args)["replayed"]
    assert not any(x.args[0].startswith("INSERT") for x in cur.execute.call_args_list)
    cur.fetchone.side_effect = [(1,), None]
    checks = iter([payload, {**payload, "summary": "changed"}])
    with pytest.raises(PermissionError):
        mod.record_after_call(**{**args, "verify": lambda: next(checks)})
    assert conn.__exit__.call_args.args[0] is PermissionError
