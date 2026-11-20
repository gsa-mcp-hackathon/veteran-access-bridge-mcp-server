"""Recheck the authoritative test inventory; never attest to VA availability."""

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)


def verify_test_inventory(connect, *, identity, slot_id, option_id, host_subject):
    """Lock and verify a case-bound test slot, recording the source of the check.

    This is a fresh read of the demo's authoritative inventory, not a renewal
    of an external API observation. The existing consent/commit checks still
    run afterwards and the commit transaction locks the slot again.
    """
    now = datetime.now(timezone.utc)
    if (
        os.getenv("VAB_ENABLE_AGENT_SCHEDULING") != "true"
        or identity.verified is not True
        or identity.expires_at <= now
        or not host_subject
        or not option_id
    ):
        raise PermissionError("Current trusted test identity required")
    with connect() as conn, conn.cursor() as cur:
        if assert_synthetic_scheduling_database(cur, conn, write=True) != "vab_test":
            raise PermissionError("Isolated test inventory required")
        cur.execute(
            "SELECT 1 FROM vab_test.audit_event WHERE event_id=%s "
            "AND event_type='SYNTHETIC_IDENTITY_VERIFICATION' AND actor=%s "
            "AND correlation_id=%s AND details->>'case_id'=%s "
            "AND details->>'patient_id'=%s AND details->>'verified'='true' "
            "AND (details->>'expires_at')::timestamptz>clock_timestamp()",
            (
                identity.event_id,
                host_subject,
                identity.correlation_id,
                identity.case_id,
                str(identity.patient_id),
            ),
        )
        if cur.fetchone() is None:
            raise PermissionError("Recorded current call identity required")
        cur.execute(
            "SELECT s.slot_id FROM vab_test.slot s "
            "JOIN vab_test.clinic c ON c.clinic_id=s.clinic_id "
            "JOIN vab_test.data_source d ON d.source_id=s.source_id "
            "WHERE s.slot_id=%s AND s.status='AVAILABLE' "
            "AND s.channel IN ('VISTA','FEDERAL_EHR') "
            "AND s.begins_at>clock_timestamp() AND s.ends_at>s.begins_at "
            "AND c.active AND upper(c.specialty)='PRIMARY_CARE' "
            "AND d.source_kind='synthetic_fixture' "
            "AND d.provenance->>'synthetic'='true' "
            "AND d.provenance->>'not_live_va_slots'='true' "
            "AND d.provenance->>'fixture_batch'='VAB-DEMO-20261113' "
            "AND d.provenance->'slot_bindings'->(s.slot_id::text)->>'case_id'=%s "
            "AND d.provenance->'slot_bindings'->(s.slot_id::text)->>'option_id'=%s "
            "AND EXISTS(SELECT 1 FROM vab_test.scheduling_case_link l "
            "JOIN vab_test.appointment_request r ON r.request_id=l.request_id "
            "WHERE l.case_id=%s AND l.synthetic AND r.patient_id=%s "
            "AND r.request_kind='PRIMARY_CARE' AND r.requested_service='PRIMARY_CARE' "
            "AND r.status IN ('OPEN','OPTIONS') "
            "AND NOT EXISTS(SELECT 1 FROM vab_test.appointment a "
            "WHERE a.request_id=r.request_id AND a.status='BOOKED_SIMULATED')) "
            "FOR UPDATE OF s",
            (
                slot_id,
                identity.case_id,
                option_id,
                identity.case_id,
                identity.patient_id,
            ),
        )
        if cur.fetchone() is None:
            raise PermissionError("Current available case-bound test slot required")
        cur.execute(
            "UPDATE vab_test.slot SET verified_at=clock_timestamp() "
            "WHERE slot_id=%s RETURNING verified_at",
            (slot_id,),
        )
        checked_at = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO vab_test.audit_event"
            "(event_id,correlation_id,actor,event_type,details) "
            "VALUES(%s,%s,%s,'SYNTHETIC_SLOT_SOURCE_RECHECKED',%s::jsonb)",
            (
                uuid4(),
                identity.correlation_id,
                host_subject,
                json.dumps(
                    {
                        "case_id": identity.case_id,
                        "slot_id": str(slot_id),
                        "option_id": option_id,
                        "verified_at": checked_at.isoformat(),
                        "synthetic": True,
                        "source": "AUTHORITATIVE_VAB_TEST_INVENTORY",
                        "va_availability_verified": False,
                    }
                ),
            ),
        )
    return checked_at
