"""Inspect, then attest one existing synthetic fixture slot for the approved call.

This is an operator fixture-preparation command, never an MCP tool or caller API.
It does not create slots, patients, identity, consent, appointments, or VA evidence.
--apply requires an explicit slot UUID and the existing restricted write opt-in.
"""

from __future__ import annotations

import argparse
import json
import re
from uuid import UUID, uuid4

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.supabase_scheduling_connection import (
    connect_private_supabase_test_scheduling,
    connect_private_supabase_test_scheduling_readonly,
)
from veteran_access_bridge.app.private_primary_care_booking import APPROVED_CASE

SOURCE = "VAB-DEMO-SCHED-20261113"
PATIENT = UUID("fe0defc2-1ead-0eb7-2156-7eb36606e742")


def verify(*, slot_id=None, apply=False, case_id=APPROVED_CASE, patient_id=PATIENT):
    if not re.fullmatch(r"VAB-DEMO-20261113-CASE-\d{3}", case_id):
        raise ValueError("An explicit synthetic fixture case is required")
    patient_id = UUID(str(patient_id))
    if apply and slot_id is None:
        raise ValueError("Review the dry run and supply its exact slot UUID")
    connect = (
        connect_private_supabase_test_scheduling
        if apply
        else connect_private_supabase_test_scheduling_readonly
    )
    with connect() as conn:
        with conn.cursor() as cur:
            if (
                assert_synthetic_scheduling_database(cur, conn, write=apply)
                != "vab_test"
            ):
                raise PermissionError("Only isolated vab_test is allowed")
            cur.execute(
                "SELECT r.patient_id,r.status,r.requested_service,p.synthetic "
                "FROM vab_test.scheduling_case_link l "
                "JOIN vab_test.appointment_request r ON r.request_id=l.request_id "
                "JOIN vab_test.patient p ON p.patient_id=r.patient_id "
                "WHERE l.case_id=%s AND l.synthetic=true AND r.re"
                "quest_kind='PRIMARY_CARE'" + (" FOR SHARE OF l,r,p" if apply else ""),
                (case_id,),
            )
            case = cur.fetchone()
            if (
                case is None
                or case[0] != patient_id
                or case[1] not in ("OPEN", "OPTIONS")
                or case[2] != "PRIMARY_CARE"
                or case[3] is not True
            ):
                raise PermissionError("Approved open synthetic case required")
            cur.execute(
                "SELECT s.slot_id,s.status,s.channel,s.begins_at,s.ends_at,"
                "c.specialty,c.active,d.source_kind,d.provenance,clock_timestamp() "
                "FROM vab_test.slot s JOIN vab_test.clinic c ON c"
                ".clinic_id=s.clinic_id "
                "JOIN vab_test.data_source d ON d.source_id=s.source_id "
                "WHERE s.source_id=%s AND s.status='AVAILABLE' "
                "AND s.channel IN ('VISTA','FEDERAL_EHR') AND c.active=true "
                "AND upper(c.specialty)='PRIMARY_CARE' AND s.begi"
                "ns_at>clock_timestamp() "
                "AND (%s::uuid IS NULL OR s.slot_id=%s::uuid) "
                "ORDER BY s.begins_at,s.slot_id LIMIT 1"
                + (" FOR UPDATE OF s,d" if apply else ""),
                (SOURCE, slot_id, slot_id),
            )
            row = cur.fetchone()
            if row is None:
                raise PermissionError("No eligible existing synthetic slot")
            (
                selected,
                status,
                channel,
                begins,
                ends,
                specialty,
                active,
                kind,
                provenance,
                now,
            ) = row
            if (
                kind != "synthetic_fixture"
                or not isinstance(provenance, dict)
                or provenance.get("synthetic") is not True
                or provenance.get("not_live_va_slots") is not True
                or provenance.get("fixture_batch") != "VAB-DEMO-20261113"
                or begins <= now
                or ends <= begins
            ):
                raise PermissionError("Reviewed synthetic fixture provenance required")
            option = "VA-PC-VOICE-" + str(selected)
            bindings = provenance.get("slot_bindings", {})
            if not isinstance(bindings, dict):
                raise PermissionError("Malformed slot provenance")
            expected = {"case_id": case_id, "option_id": option}
            if str(selected) in bindings and bindings[str(selected)] != expected:
                raise PermissionError("Slot already bound to another case or option")
            report = {
                "synthetic": True,
                "not_live_va_slots": True,
                "case_id": case_id,
                "slot_id": str(selected),
                "option_id": option,
                "source_id": SOURCE,
                "begins_at": begins.isoformat(),
                "ends_at": ends.isoformat(),
                "verification_method": "PERSISTED_SYNTHETIC_FIXTURE_CHECK",
                "applied": apply,
            }
            if apply:
                bindings = dict(bindings)
                bindings[str(selected)] = expected
                provenance = dict(provenance)
                provenance["slot_bindings"] = bindings
                cur.execute(
                    "UPDATE vab_test.data_source SET provenance=%s::j"
                    "sonb WHERE source_id=%s",
                    (json.dumps(provenance), SOURCE),
                )
                cur.execute(
                    "UPDATE vab_test.slot SET verified_at=%s WHERE sl"
                    "ot_id=%s AND status='AVAILABLE'",
                    (now, selected),
                )
                if cur.rowcount != 1:
                    raise PermissionError("Slot changed during verification")
                cur.execute(
                    "INSERT INTO vab_test.audit_event (event_id,corre"
                    "lation_id,actor,event_type,details) VALUES (%s,%"
                    "s,%s,%s,%s::jsonb)",
                    (
                        uuid4(),
                        "slot-verification:" + str(selected),
                        "synthetic-fixture-operator",
                        "SYNTHETIC_SLOT_VERIFIED",
                        json.dumps(report | {"verified_at": now.isoformat()}),
                    ),
                )
    if apply:
        with connect_private_supabase_test_scheduling_readonly() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT s.verified_at,d.provenance->'slot_binding"
                    "s'->(s.slot_id::text) "
                    "FROM vab_test.slot s JOIN vab_test.data_source d"
                    " ON d.source_id=s.source_id WHERE s.slot_id=%s",
                    (selected,),
                )
                verified = cur.fetchone()
                if verified is None or verified[0] != now or verified[1] != expected:
                    raise RuntimeError("Synthetic slot verification readback failed")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot-id", type=UUID)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--case-id", default=APPROVED_CASE)
    parser.add_argument("--patient-id", type=UUID, default=PATIENT)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                slot_id=args.slot_id,
                apply=args.apply,
                case_id=args.case_id,
                patient_id=args.patient_id,
            ),
            indent=2,
        )
    )
