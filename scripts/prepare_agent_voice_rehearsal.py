"""Prepare one new Judy rehearsal case with two existing demo slots; no booking."""

import argparse
import json
from uuid import NAMESPACE_URL, uuid4, uuid5

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
)

CASE = "VAB-DEMO-20261113-CASE-047"
REFERENCE = "VAB-DEMO-20261113-CASE-046"
SOURCE = "VAB-DEMO-SCHED-20261113"
REQUEST = uuid5(NAMESPACE_URL, "vab-agent-led-20261116:request:047")


def prepare(*, apply=False):
    with connect_private_supabase_test_scheduling() as conn, conn.cursor() as cur:
        if assert_synthetic_scheduling_database(cur, conn, write=True) != "vab_test":
            raise PermissionError("Only the isolated test database is allowed")
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (CASE,))
        cur.execute("SELECT count(*) FROM vab_test.appointment")
        before = cur.fetchone()[0]
        cur.execute(
            "SELECT r.patient_id,p.display_name,p.birth_date,p.synthetic "
            "FROM vab_test.scheduling_case_link l "
            "JOIN vab_test.appointment_request r ON r.request_id=l.request_id "
            "JOIN vab_test.patient p ON p.patient_id=r.patient_id WHERE l.case_id=%s",
            (REFERENCE,),
        )
        patient = cur.fetchone()
        if (
            not patient
            or patient[1] != "Judy Morrison"
            or str(patient[2]) != "1945-05-05"
            or patient[3] is not True
        ):
            raise PermissionError(
                "Existing approved VA sandbox rehearsal identity required"
            )
        cur.execute(
            "SELECT request_id FROM vab_test.scheduling_case_link WHERE case_id=%s",
            (CASE,),
        )
        if cur.fetchone():
            raise PermissionError("Rehearsal case already exists; never reset it")
        cur.execute(
            "SELECT provenance FROM vab_test.data_source WHERE source_id=%s "
            "AND source_kind='synthetic_fixture' FOR UPDATE",
            (SOURCE,),
        )
        row = cur.fetchone()
        if (
            not row
            or row[0].get("synthetic") is not True
            or row[0].get("not_live_va_slots") is not True
            or row[0].get("fixture_batch") != "VAB-DEMO-20261113"
        ):
            raise PermissionError("Reviewed demo inventory source required")
        provenance = dict(row[0])
        bindings = dict(provenance.get("slot_bindings", {}))
        cur.execute(
            "SELECT s.slot_id,s.begins_at,s.ends_at,c.name,s.provider_id "
            "FROM vab_test.slot s JOIN vab_test.clinic c ON c.clinic_id=s.clinic_id "
            "WHERE s.source_id=%s AND s.status='AVAILABLE' "
            "AND s.channel IN ('VISTA','FEDERAL_EHR') AND c.active "
            "AND upper(c.specialty)='PRIMARY_CARE' "
            "AND s.clinic_id=(SELECT prior.clinic_id FROM vab_test.slot prior "
            "JOIN vab_test.appointment a ON a.slot_id=prior.slot_id "
            "JOIN vab_test.scheduling_case_link l ON l.request_id=a.request_id "
            "WHERE l.case_id=%s AND a.status='BOOKED_SIMULATED') "
            "AND s.begins_at>clock_timestamp() "
            "ORDER BY s.begins_at,s.slot_id FOR UPDATE OF s",
            (SOURCE, REFERENCE),
        )
        slots = [row for row in cur.fetchall() if str(row[0]) not in bindings][:2]
        if len(slots) != 2:
            raise PermissionError("Two unbound available demo slots required")
        cur.execute(
            "INSERT INTO vab_test.appointment_request"
            "(request_id,patient_id,requested_service,request_kind,status,provenance) "
            "VALUES(%s,%s,'PRIMARY_CARE','PRIMARY_CARE','OPEN',%s::jsonb)",
            (
                REQUEST,
                patient[0],
                json.dumps(
                    {
                        "synthetic": True,
                        "purpose": "Agent-led voice rehearsal",
                        "reference_case": REFERENCE,
                    }
                ),
            ),
        )
        cur.execute(
            "INSERT INTO vab_test.scheduling_case_link"
            "(case_id,request_id,source_request_id,source_system,synthetic) "
            "VALUES(%s,%s,%s,'SYNTHETIC_VOICE_REHEARSAL',true)",
            (CASE, REQUEST, CASE),
        )
        for slot in slots:
            bindings[str(slot[0])] = {
                "case_id": CASE,
                "option_id": "VA-PC-VOICE-" + str(slot[0]),
            }
        provenance["slot_bindings"] = bindings
        cur.execute(
            "UPDATE vab_test.data_source SET provenance=%s::jsonb WHERE source_id=%s",
            (json.dumps(provenance), SOURCE),
        )
        report = {
            "case_id": CASE,
            "patient_id": str(patient[0]),
            "synthetic": True,
            "slots": [
                {
                    "slot_id": str(s[0]),
                    "begins_at": s[1].isoformat(),
                    "ends_at": s[2].isoformat(),
                    "clinic_name": s[3],
                    "provider_id": s[4],
                }
                for s in slots
            ],
            "applied": apply,
            "appointments_before": before,
        }
        cur.execute(
            "INSERT INTO vab_test.audit_event"
            "(event_id,correlation_id,actor,event_type,details) "
            "VALUES(%s,%s,'synthetic-fixture-operator','SYNTHETIC_VOICE_FIXTURE_PREPARED',%s::jsonb)",
            (uuid4(), CASE, json.dumps(report)),
        )
        cur.execute("SELECT count(*) FROM vab_test.appointment")
        if cur.fetchone()[0] != before:
            raise AssertionError("Fixture preparation changed appointments")
        if not apply:
            conn.rollback()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    print(json.dumps(prepare(apply=parser.parse_args().apply)))
