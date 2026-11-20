"""Case-scoped read-only projection of imported synthetic EPS/HSRM SQL evidence.

This is a catalog view, not an availability refresh or booking authorization.
"""

from __future__ import annotations

import os

from veteran_access_bridge.adapters.synthetic_ids import resolve_case_identifiers

SOURCE = "vab-eps-hsrm-fixture-v1"


def read_scheduling_options(case_id: str, *, connect=None) -> dict:
    if os.getenv("VAB_ENABLE_PG_SCHEDULING_READ") != "true":
        raise PermissionError("PostgreSQL scheduling reads disabled")
    if os.getenv("VAB_MCP_TRANSPORT", "stdio") != "stdio":
        raise PermissionError("Only local stdio transport is allowed")
    ids = resolve_case_identifiers(case_id)
    if connect is None:
        import psycopg

        dsn = os.environ["VAB_DATABASE_URL"]

        def connect():
            return psycopg.connect(dsn)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            if cur.fetchone()[0] != "veteran_access_bridge_dev":
                raise ValueError("Only isolated development PostgreSQL allowed")
            cur.execute(
                "SELECT r.request_id,r.patient_id,r.requested_service,"
                "r.request_kind,r.status FROM vab.scheduling_case_link l "
                "JOIN vab.appointment_request r ON r.request_id=l.request_id "
                "WHERE l.case_id=%s AND l.synthetic=true",
                (case_id,),
            )
            request = cur.fetchone()
            if request is None or str(request[0]) != str(ids.request_uuid):
                raise ValueError("Canonical synthetic case mapping mismatch")
            request_id, patient_id, service, kind, request_status = request
            if patient_id != ids.patient_uuid:
                raise ValueError("Canonical patient mapping mismatch")
            cur.execute(
                "SELECT specialty,status FROM vab.consult "
                "WHERE request_id=%s ORDER BY ordered_at",
                (request_id,),
            )
            consults = [
                {"specialty": specialty, "status": status}
                for specialty, status in cur.fetchall()
            ]
            cur.execute(
                "SELECT source_kind,provenance FROM vab.data_source WHERE source_id=%s",
                (SOURCE,),
            )
            source_row = cur.fetchone()
            if source_row is None or source_row[0] != "synthetic_fixture":
                raise ValueError("Synthetic EPS source provenance missing")
            source_metadata = source_row[1]
            slot_bindings = source_metadata.get("slot_bindings", {})
            if not isinstance(slot_bindings, dict):
                raise ValueError("Invalid persisted EPS ownership metadata")
            cur.execute(
                "SELECT s.slot_id,s.provider_id,s.begins_at,s.ends_at,"
                "s.status,s.verified_at "
                "FROM vab.slot s WHERE s.channel='EPS' AND s.source_id=%s "
                "ORDER BY s.begins_at,s.slot_id",
                (SOURCE,),
            )
            slots = cur.fetchall()
            cur.execute(
                "SELECT a.authorization_id,a.status,a.service_scope,"
                "a.valid_from,a.valid_until,a.evidence "
                "FROM vab.authorization a "
                "JOIN vab.referral f ON f.referral_id=a.referral_id "
                "WHERE a.source_id=%s AND f.patient_id=%s "
                "AND f.evidence->>'case_id'=%s "
                "ORDER BY a.authorization_id",
                (SOURCE, patient_id, case_id),
            )
            auths = cur.fetchall()
            cur.execute(
                "SELECT a.appointment_id,a.slot_id,a.status "
                "FROM vab.appointment a WHERE a.request_id=%s "
                "ORDER BY a.confirmed_at,a.appointment_id",
                (request_id,),
            )
            booked = cur.fetchall()

    authorizations = [
        {
            "authorization_id": str(auth_id),
            "status": status,
            "service_scope": scope,
            "valid_from": valid_from.isoformat() if valid_from else None,
            "valid_until": valid_until.isoformat() if valid_until else None,
            "option_id": evidence.get("option_id"),
            "source_authorization_id": evidence.get("source_authorization_id"),
            "provider_id": evidence.get("authorized_provider_id"),
            "slot_id": evidence.get("slot_id"),
            "synthetic": evidence.get("synthetic") is True,
        }
        for auth_id, status, scope, valid_from, valid_until, evidence in auths
    ]
    options = []
    for slot_id, provider, start, end, status, verified_at in slots:
        binding = slot_bindings.get(str(slot_id))
        if not isinstance(binding, dict):
            raise ValueError("Imported EPS slot missing persisted ownership")
        if binding.get("case_id") != case_id:
            continue
        option_id = binding.get("option_id")
        if not isinstance(option_id, str) or not option_id:
            raise ValueError("Imported EPS slot missing option ID")
        matches = []
        for authorization in authorizations:
            if (
                authorization["option_id"] != option_id
                or authorization["provider_id"] != provider
                or not authorization["synthetic"]
            ):
                continue
            exact = authorization["slot_id"] == str(slot_id)
            if authorization["slot_id"] is not None and not exact:
                continue
            matches.append(
                {
                    **authorization,
                    "association": ("EXACT_SLOT" if exact else "OPTION_PROVIDER_ONLY"),
                    "slot_bound": exact,
                }
            )
        options.append(
            {
                "slot_id": str(slot_id),
                "source_slot_id": binding.get("source_slot_id"),
                "option_id": option_id,
                "provider_id": provider,
                "starts_at": start.isoformat(),
                "ends_at": end.isoformat(),
                "fixture_status": status,
                "initial_consult_eligible": (
                    binding.get("initial_consult_eligible") is True
                ),
                "verified_at": verified_at.isoformat() if verified_at else None,
                "authorizations": matches,
                "booking_ready": False,
                "readiness_reason": "No fresh EPS verification or actor-bound approval",
            }
        )
    return {
        "case_id": case_id,
        "request_id": str(request_id),
        "requested_service": service,
        "request_kind": kind,
        "request_status": request_status,
        "consults": consults,
        "eps_options": options,
        "hsrm_authorizations": authorizations,
        "appointments": [
            {"appointment_id": str(a), "slot_id": str(s), "status": st}
            for a, s, st in booked
        ],
        "synthetic": True,
        "read_only": True,
        "booking_writes_enabled": False,
        "source": "postgresql_dev_fixture_catalog",
    }
