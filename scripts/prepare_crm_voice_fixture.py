"""Link one existing synthetic voice persona to CRM, without a slot or booking."""

import json
import os
from uuid import NAMESPACE_URL, uuid5

from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
)
from veteran_access_bridge.mcp.voice_demo_patients import list_voice_demo_patients

CASE = "DEMO-PC-P114-001"
SOURCE_CASE = "VAB-DEMO-20261113-CASE-005"


def main():
    if os.getenv("VAB_PREPARE_CRM_VOICE_FIXTURE") != CASE:
        raise PermissionError("Explicit synthetic CRM fixture opt-in required")
    persona = next(p for p in list_voice_demo_patients() if p["case_id"] == CASE)
    request = uuid5(NAMESPACE_URL, "vab:crm-voice-fixture:" + CASE)
    with connect_private_supabase_test_scheduling() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (CASE,))
            cur.execute(
                "SELECT p.patient_id,p.display_name,p.birth_date,p.synthetic "
                "FROM vab_test.patient p JOIN vab_test.appointment_request r "
                "ON r.patient_id=p.patient_id JOIN vab_test.scheduling_case_link l "
                "ON l.request_id=r.request_id WHERE l.case_id=%s AND l.synthetic",
                (SOURCE_CASE,),
            )
            patient = cur.fetchone()
            if not patient or (
                patient[1] != persona["name"]
                or patient[2].isoformat() != persona["birthdate"]
                or patient[3] is not True
            ):
                raise ValueError("Existing synthetic identity must match exactly")
            cur.execute("SELECT count(*) FROM vab_test.appointment")
            before = cur.fetchone()[0]
            cur.execute(
                "SELECT request_id FROM vab_test.scheduling_case_link WHERE case_id=%s",
                (CASE,),
            )
            existing = cur.fetchone()
            if existing:
                if existing[0] != request:
                    raise ValueError("Existing case must not be rebound")
            else:
                cur.execute(
                    "INSERT INTO vab_test.appointment_request "
                    "(request_id,patient_id,requested_service,request_kind,status,"
                    "provenance) VALUES (%s,%s,%s,'PRIMARY_CARE','CLOSED',%s::jsonb)",
                    (
                        request,
                        patient[0],
                        "CRM_ONLY_NO_BOOKING",
                        json.dumps(
                            {
                                "synthetic": True,
                                "purpose": "CRM voice acceptance",
                                "source_case": SOURCE_CASE,
                            }
                        ),
                    ),
                )
                cur.execute(
                    "INSERT INTO vab_test.scheduling_case_link "
                    "(case_id,request_id,source_request_id,source_system,synthetic) "
                    "VALUES (%s,%s,%s,'SYNTHETIC_CRM_ACCEPTANCE',true)",
                    (CASE, request, "crm-voice:" + CASE),
                )
            cur.execute("SELECT count(*) FROM vab_test.appointment")
            after = cur.fetchone()[0]
            if before != after:
                raise AssertionError("Appointment count changed")
    print(
        json.dumps(
            {
                "case_id": CASE,
                "existing": bool(existing),
                "appointment_count_unchanged": before == after,
                "appointments": after,
                "request_status": "CLOSED",
            }
        )
    )


if __name__ == "__main__":
    main()
