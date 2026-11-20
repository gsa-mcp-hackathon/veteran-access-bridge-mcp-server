"""Prepare one pronounceable synthetic caller; never book or issue consent."""

import argparse
import json
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
)

CASE = "VAB-DEMO-20261113-CASE-046"
SOURCE = "VAB-SIMPLE-VOICE-20261116"
NAME = "Judy Morrison"
DOB = date(1945, 5, 5)
PATIENT = uuid5(NAMESPACE_URL, SOURCE + ":patient")
REQUEST = uuid5(NAMESPACE_URL, SOURCE + ":request")


def prepare(*, apply=False):
    provenance = {
        "synthetic": True,
        "purpose": "Pronounceable voice rehearsal",
        "not_live_va_data": True,
        "roster_reference": "DEMO-PC-P219-001",
    }
    with connect_private_supabase_test_scheduling() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (CASE,))
            cur.execute("SELECT count(*) FROM vab_test.appointment")
            before = cur.fetchone()[0]
            cur.execute(
                "SELECT patient_id,display_name,birth_date,synthetic,source_id "
                "FROM vab_test.patient WHERE patient_id=%s",
                (PATIENT,),
            )
            patient = cur.fetchone()
            if patient and patient != (PATIENT, NAME, DOB, True, SOURCE):
                raise ValueError("Existing patient must not be altered")
            cur.execute(
                "SELECT l.request_id,r.patient_id,r.request_kind,r.requested_service "
                "FROM vab_test.scheduling_case_link l "
                "JOIN vab_test.appointment_request r "
                "ON r.request_id=l.request_id WHERE l.case_id=%s",
                (CASE,),
            )
            existing = cur.fetchone()
            if existing and existing != (
                REQUEST,
                PATIENT,
                "PRIMARY_CARE",
                "PRIMARY_CARE",
            ):
                raise ValueError("Existing case must not be rebound")
            if not patient:
                cur.execute(
                    "INSERT INTO vab_test.data_source "
                    "(source_id,source_kind,description,provenance) "
                    "VALUES (%s,'synthetic_fixture',%s,%s::jsonb)",
                    (
                        SOURCE,
                        "Fictional voice rehearsal identity",
                        json.dumps(provenance),
                    ),
                )
                cur.execute(
                    "INSERT INTO vab_test.patient "
                    "(patient_id,demo_patient_key,display_name,birth_date,synthetic,"
                    "source_id,source_patient_id,attributes) "
                    "VALUES (%s,%s,%s,%s,true,%s,%s,%s::jsonb)",
                    (
                        PATIENT,
                        SOURCE,
                        NAME,
                        DOB,
                        SOURCE,
                        SOURCE,
                        json.dumps(provenance),
                    ),
                )
            if not existing:
                cur.execute(
                    "INSERT INTO vab_test.appointment_request "
                    "(request_id,patient_id,requested_service,request_kind,"
                    "status,provenance) "
                    "VALUES (%s,%s,'PRIMARY_CARE','PRIMARY_CARE','OPEN',%s::jsonb)",
                    (REQUEST, PATIENT, json.dumps(provenance)),
                )
                cur.execute(
                    "INSERT INTO vab_test.scheduling_case_link "
                    "(case_id,request_id,source_request_id,source_system,synthetic) "
                    "VALUES (%s,%s,%s,'SYNTHETIC_VOICE_REHEARSAL',true)",
                    (CASE, REQUEST, SOURCE),
                )
            cur.execute("SELECT count(*) FROM vab_test.appointment")
            if cur.fetchone()[0] != before:
                raise AssertionError("Fixture preparation changed appointments")
        if not apply:
            conn.rollback()
    return {
        "case_id": CASE,
        "patient_id": str(PATIENT),
        "name": NAME,
        "birth_date": DOB.isoformat(),
        "applied": apply,
        "appointment_count_unchanged": True,
        "appointments": before,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    print(json.dumps(prepare(apply=parser.parse_args().apply)))
