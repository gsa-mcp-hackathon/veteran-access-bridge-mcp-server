"""Private host provisioning for approved VA sandbox callers, never production ID."""

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from importlib.resources import files
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from veteran_access_bridge.adapters.pg_scheduling_database_boundary import (
    assert_synthetic_scheduling_database,
)
from veteran_access_bridge.adapters.va_fhir_readers import (
    _PATIENT,
    _get_bundle,
    _search_resources,
)
from veteran_access_bridge.services.call_patient_lookup import read_patient_summary
from veteran_access_bridge.services.demo_facility_context import configured_facilities
from veteran_access_bridge.services.trusted_primary_care import (
    CASE_PROVISION_SCOPE,
    _normalize_name,
)

SOURCE = "VAB-DEMO-SCHED-20261113"
PATIENT_SOURCE = "VAB-APPROVED-VA-VOICE-PATIENTS"


def approved_candidate(name, birth_date, *, roster=None):
    """Exact unique match against enabled personas; no fuzzy or guessed identity."""
    if roster is None:
        roster = json.loads(
            files("veteran_access_bridge.mcp")
            .joinpath("fixtures/synthetic-primary-care-caller-roster.json")
            .read_text(encoding="utf-8")
        )
    if roster.get("synthetic") is not True:
        raise PermissionError("Approved synthetic roster required")
    candidates = [
        p
        for p in roster.get("patients", [])
        if p.get("enabled_for_patient_match") is True
        and _normalize_name(p["first_name"] + " " + p["last_name"])
        == _normalize_name(name)
        and p.get("birthdate") == birth_date
    ]
    return dict(candidates[0]) if len(candidates) == 1 else None


class AdditionalIdentityMismatch(PermissionError):
    """A private test identity factor did not match; contains no values."""


def verify_candidate_source(candidate, *, http=None, last_four=None):
    """Use the real approved VA sandbox adapter before provisioning any record."""
    icn = candidate["icn"]
    bundle = _get_bundle(
        _PATIENT,
        "Patient",
        icn,
        scope="system/Patient.read",
        params={"identifier": icn},
        launch={"patient": icn},
        http=http,
    )
    rows = _search_resources(bundle, "Patient")
    expected = _normalize_name(candidate["first_name"] + " " + candidate["last_name"])
    if len(rows) != 1:
        raise PermissionError("Unique VA sandbox patient required")
    row = rows[0]
    names = {
        _normalize_name(" ".join([*n.get("given", []), n.get("family", "")]))
        for n in row.get("name", [])
        if isinstance(n, dict)
    }
    if (
        expected not in names
        or row.get("birthDate") != candidate["birthdate"]
        or not any(i.get("value") == icn for i in row.get("identifier", []))
    ):
        raise PermissionError("VA sandbox identity mismatch")

    if os.getenv("VAB_REQUIRE_MASKED_LAST_FOUR") == "true":
        from veteran_access_bridge.services.patient_last_four import (
            matches_patient_last_four,
        )

        if not matches_patient_last_four(row, last_four):
            raise AdditionalIdentityMismatch("Additional test identity check failed")


class SandboxCallerResolver:
    """Not an endpoint or MCP tool. Invoked only by the authenticated voice host."""

    def __init__(self, connect, read_connect, authenticator):
        self.connect, self.read_connect = connect, read_connect
        self.authenticator = authenticator
        self.bindings = {}

    @staticmethod
    def case_id(voice):
        if not voice.startswith("vs-"):
            raise PermissionError("Canonical voice session required")
        UUID(voice[3:])
        return "VAB-CALL-" + str(uuid5(NAMESPACE_URL, "vab-call:" + voice))

    def bound(self, case, voice):
        binding = self.bindings.get(voice)
        return bool(binding and binding[0] == case and binding[2] > time.monotonic())

    def read(self, case, voice):
        if not self.bound(case, voice):
            raise PermissionError("Current patient-call binding required")
        return read_patient_summary(
            self.read_connect, case, approved_icn=self.bindings[voice][1]
        )

    def resolve(self, *, name, birth_date, voice, assertion, last_four=None):
        case = self.case_id(voice)
        principal = self.authenticator.authenticate(
            assertion, required_scope=CASE_PROVISION_SCOPE
        )
        if set(principal.case_ids) != {case}:
            raise PermissionError("Exact provisioning scope required")
        candidate = approved_candidate(name, birth_date)
        if candidate is None:
            return None
        if os.getenv("VAB_REQUIRE_MASKED_LAST_FOUR") == "true":
            try:
                verify_candidate_source(candidate, last_four=last_four)
            except AdditionalIdentityMismatch:
                return None
        else:
            verify_candidate_source(candidate)
        self._provision(case, voice, candidate, principal.subject)
        self.bindings = {
            k: v for k, v in self.bindings.items() if v[2] > time.monotonic()
        }
        self.bindings[voice] = (case, candidate["icn"], time.monotonic() + 900)
        return case

    def renew(self, case, voice):
        """Keep the existing case lease while the host verifies live presence."""
        if not self.bound(case, voice):
            raise PermissionError("Current patient-call binding required")
        with self.connect() as conn, conn.cursor() as q:
            if assert_synthetic_scheduling_database(q, conn, write=True) != "vab_test":
                raise PermissionError("Isolated test database required")
            q.execute(
                "UPDATE vab_test.appointment_request r SET provenance="
                "jsonb_set(r.provenance,'{call_expires_at}',"
                "to_jsonb((clock_timestamp()+interval '15 minutes')::text)) FROM "
                "vab_test.scheduling_case_link l WHERE l.request_id=r.request_id "
                "AND l.case_id=%s AND r.provenance->>'voice_session_id'=%s "
                "AND (r.provenance->>'call_expires_at')::timestamptz>clock_timestamp()",
                (case, voice),
            )
            if q.rowcount != 1:
                raise PermissionError("Current call-owned request required")
        binding = self.bindings[voice]
        self.bindings[voice] = (binding[0], binding[1], time.monotonic() + 900)

    def finish(self, case, voice):
        """Release unused offers only after the trusted host has ended the call."""
        if not self.bound(case, voice):
            raise PermissionError("Current patient-call binding required")
        with self.connect() as conn, conn.cursor() as q:
            if assert_synthetic_scheduling_database(q, conn, write=True) != "vab_test":
                raise PermissionError("Isolated test database required")
            q.execute(
                "SELECT provenance FROM vab_test.data_source WHERE source_id=%s "
                "FOR UPDATE",
                (SOURCE,),
            )
            row = q.fetchone()
            if not row:
                raise PermissionError("Test inventory source required")
            source = dict(row[0])
            q.execute(
                "SELECT s.slot_id FROM vab_test.slot s WHERE s.source_id=%s "
                "AND s.status='AVAILABLE' AND NOT EXISTS(SELECT 1 FROM "
                "vab_test.appointment a WHERE a.slot_id=s.slot_id)",
                (SOURCE,),
            )
            available = {str(r[0]) for r in q.fetchall()}
            source["slot_bindings"] = {
                k: v
                for k, v in source.get("slot_bindings", {}).items()
                if v.get("case_id") != case or k not in available
            }
            q.execute(
                "UPDATE vab_test.appointment_request r SET provenance="
                "jsonb_set(r.provenance,'{call_expires_at}',"
                "to_jsonb(clock_timestamp()::text)) FROM "
                "vab_test.scheduling_case_link l WHERE l.request_id=r.request_id "
                "AND l.case_id=%s AND r.provenance->>'voice_session_id'=%s",
                (case, voice),
            )
            if q.rowcount != 1:
                raise PermissionError("Call-owned request required")
            q.execute(
                "UPDATE vab_test.data_source SET provenance=%s::jsonb "
                "WHERE source_id=%s",
                (json.dumps(source), SOURCE),
            )

    def _provision(self, case, voice, patient, actor):
        """Serialize enrollment and allocate only existing unbound demo slots."""
        icn = patient["icn"]
        name = patient["first_name"] + " " + patient["last_name"]
        birth = date.fromisoformat(patient["birthdate"])
        request_id = uuid5(NAMESPACE_URL, "vab-call-request:" + voice)
        with self.connect() as conn, conn.cursor() as q:
            if assert_synthetic_scheduling_database(q, conn, write=True) != "vab_test":
                raise PermissionError("Isolated test database required")
            q.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))", ("va-caller:" + icn,)
            )
            # Reuse an existing exact synthetic patient; never update demographics.
            q.execute(
                "SELECT patient_id FROM vab_test.patient WHERE synthetic "
                "AND lower(display_name)=lower(%s) AND birth_date=%s",
                (name, birth),
            )
            patients = q.fetchall()
            if len(patients) > 1:
                raise PermissionError("Ambiguous persisted patient")
            patient_id = (
                patients[0][0]
                if patients
                else uuid5(NAMESPACE_URL, "va-sandbox:" + icn)
            )
            q.execute(
                "SELECT l.request_id,r.patient_id,r.provenance FROM "
                "vab_test.scheduling_case_link l "
                "JOIN vab_test.appointment_request r ON r.request_id=l.request_id "
                "WHERE l.case_id=%s",
                (case,),
            )
            prior = q.fetchone()
            if prior:
                if (
                    prior[0] != request_id
                    or prior[1] != patient_id
                    or prior[2].get("voice_session_id") != voice
                ):
                    raise PermissionError("Case cannot be rebound")
                return
            q.execute(
                "SELECT 1 FROM vab_test.appointment_request WHERE patient_id=%s "
                "AND provenance->>'voice_session_id' IS NOT NULL "
                "AND (provenance->>'call_expires_at')::timestamptz>clock_timestamp() "
                "AND status IN ('OPEN','OPTIONS') LIMIT 1",
                (patient_id,),
            )
            if q.fetchone():
                raise PermissionError(
                    "Another scheduling call is active for this patient"
                )
            q.execute(
                "SELECT provenance FROM vab_test.data_source WHERE source_id=%s "
                "AND source_kind='synthetic_fixture' FOR UPDATE",
                (SOURCE,),
            )
            row = q.fetchone()
            if (
                not row
                or any(
                    row[0].get(k) is not True
                    for k in ("synthetic", "not_live_va_slots")
                )
                or row[0].get("fixture_batch") != "VAB-DEMO-20261113"
            ):
                raise PermissionError("Approved test inventory required")
            source = dict(row[0])
            bindings = dict(source.get("slot_bindings", {}))
            q.execute(
                "SELECT s.slot_id,s.clinic_id FROM vab_test.slot s JOIN "
                "vab_test.clinic c ON "
                "c.clinic_id=s.clinic_id "
                "WHERE s.source_id=%s AND s.status='AVAILABLE' AND "
                "s.begins_at>clock_timestamp() "
                "AND s.ends_at>s.begins_at AND s.channel IN ('VISTA','FEDERAL_EHR') "
                "AND c.active AND upper(c.specialty)='PRIMARY_CARE' "
                "ORDER BY s.begins_at,s.slot_id FOR UPDATE OF s",
                (SOURCE,),
            )
            mapping = configured_facilities()
            available = [
                r
                for r in q.fetchall()
                if str(r[0]) not in bindings and (not mapping or r[1] in mapping)
            ]
            # One offer set belongs to one clinic. This is demo inventory, not
            # evidence of an assigned PACT; the caller hears the clinic at readback.
            clinic = available[0][1] if available else None
            slots = [r[0] for r in available if r[1] == clinic][:2]
            if not slots:
                raise PermissionError("No unbound approved demo inventory available")
            if not patients:
                q.execute(
                    "INSERT INTO "
                    "vab_test.data_source(source_id,source_kind,description,provenance)"
                    " "
                    "VALUES(%s,'sandbox','Approved VA sandbox voice "
                    "identities',%s::jsonb) "
                    "ON CONFLICT(source_id) DO NOTHING",
                    (PATIENT_SOURCE, json.dumps({"synthetic": True})),
                )
                q.execute(
                    "INSERT INTO "
                    "vab_test.patient(patient_id,demo_patient_key,display_name,birth_da"
                    "te,"
                    "synthetic,source_id,source_patient_id,attributes) "
                    "VALUES(%s,%s,%s,%s,true,%s,%s,%s::jsonb)",
                    (
                        patient_id,
                        "va-voice:" + icn,
                        name,
                        birth,
                        PATIENT_SOURCE,
                        icn,
                        json.dumps(
                            {
                                "synthetic": True,
                                "source": "VA_PATIENT_HEALTH_API_SANDBOX",
                            }
                        ),
                    ),
                )
            provenance = {
                "synthetic": True,
                "voice_session_id": voice,
                "call_expires_at": (
                    datetime.now(timezone.utc) + timedelta(minutes=15)
                ).isoformat(),
                "purpose": "Approved VA sandbox caller scheduling",
            }
            q.execute(
                "INSERT INTO "
                "vab_test.appointment_request(request_id,patient_id,requested_service,r"
                "equest_kind,status,provenance) "
                "VALUES(%s,%s,'PRIMARY_CARE','PRIMARY_CARE','OPEN',%s::jsonb)",
                (request_id, patient_id, json.dumps(provenance)),
            )
            q.execute(
                "INSERT INTO "
                "vab_test.scheduling_case_link(case_id,request_id,source_request_id,sou"
                "rce_system,synthetic) "
                "VALUES(%s,%s,%s,'SYNTHETIC_VOICE_RESOLVER',true)",
                (case, request_id, voice),
            )
            for slot in slots:
                bindings[str(slot)] = {
                    "case_id": case,
                    "option_id": "VA-PC-VOICE-" + str(slot),
                }
            source["slot_bindings"] = bindings
            q.execute(
                "UPDATE vab_test.data_source SET provenance=%s::jsonb WHERE "
                "source_id=%s",
                (json.dumps(source), SOURCE),
            )
            q.execute(
                "INSERT INTO "
                "vab_test.audit_event(event_id,correlation_id,actor,event_type,details)"
                " "
                "VALUES(%s,%s,%s,'SYNTHETIC_CALL_CASE_PROVISIONED',%s::jsonb)",
                (
                    uuid4(),
                    voice,
                    actor,
                    json.dumps(
                        {
                            "synthetic": True,
                            "case_id": case,
                            "patient_id": str(patient_id),
                            "request_id": str(request_id),
                        }
                    ),
                ),
            )
