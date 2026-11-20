"""Read one explicitly mapped VA sandbox Patient for an already verified call."""

import json
import os
from datetime import datetime, timezone

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.va_fhir_readers import (
    _PATIENT,
    _get_bundle,
    _search_resources,
)


def read_patient_summary(
    connect, case_id: str, *, http=None, approved_icn=None
) -> dict:
    manifest = json.loads(os.environ.get("VAB_APPROVED_VA_CASE_ICNS_JSON", "{}"))
    if approved_icn is None and manifest.get("synthetic") is not True:
        raise PermissionError("Approved VA sandbox case manifest required")
    matches = [
        p
        for p in manifest.get("cases", [])
        if p.get("case_id") == case_id and p.get("approved") is True
    ]
    if approved_icn is None and (
        len(matches) != 1 or not isinstance(matches[0].get("patient_icn"), str)
    ):
        raise PermissionError(
            "Exactly one approved VA sandbox patient mapping required"
        )
    # Internal host-only binding; the API's own approved-ICN gate still applies.
    icn = approved_icn if approved_icn is not None else matches[0]["patient_icn"]
    with connect() as conn, conn.cursor() as cur:
        if assert_synthetic_scheduling_database(cur, conn, write=False) != "vab_test":
            raise PermissionError("Isolated synthetic identity source required")
        cur.execute(
            "SELECT p.display_name,p.birth_date,p.synthetic FROM vab_test.patient p "
            "JOIN vab_test.appointment_request r ON r.patient_id=p.patient_id "
            "JOIN vab_test.scheduling_case_link l ON l.request_id=r.request_id "
            "WHERE l.case_id=%s AND l.synthetic",
            (case_id,),
        )
        stored = cur.fetchone()
    if not stored or stored[2] is not True:
        raise PermissionError("Verified synthetic case identity required")
    bundle = _get_bundle(
        _PATIENT,
        "Patient",
        icn,
        scope="system/Patient.read",
        params={"identifier": icn},
        launch={"patient": icn},
        http=http,
    )
    records = _search_resources(bundle, "Patient")
    if len(records) != 1:
        raise PermissionError("VA sandbox patient lookup was not unique")
    patient = records[0]
    identifiers = patient.get("identifier", [])
    names = {
        " ".join([*n.get("given", []), n.get("family", "")]).strip().casefold()
        for n in patient.get("name", [])
        if isinstance(n, dict)
    }
    if (
        not any(i.get("value") == icn for i in identifiers)
        or stored[0].strip().casefold() not in names
        or patient.get("birthDate") != stored[1].isoformat()
    ):
        raise PermissionError("VA sandbox identity did not match the verified caller")
    return {
        "case_id": case_id,
        "synthetic": True,
        "status": "VERIFIED",
        "source": "VA_PATIENT_HEALTH_API_SANDBOX",
        "source_verified": True,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "patient_name": stored[0],
        "identity_matches": True,
        "assigned_provider": None,
        "assigned_pact": None,
        "assignment_status": "NOT_SUPPLIED_BY_THIS_PATIENT_RESPONSE",
        "booking_authority": False,
    }
