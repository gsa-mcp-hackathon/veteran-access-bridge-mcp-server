from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from veteran_access_bridge.services import sandbox_callers as mod


def test_enabled_roster_matches_exactly_and_never_guesses():
    assert mod.approved_candidate("Judy Morrison", "1945-05-05")["icn"]
    assert mod.approved_candidate("Ruben Moreno", "1949-12-30")["icn"]
    assert mod.approved_candidate("One Zztest", "1949-12-30")["icn"]
    assert mod.approved_candidate("Judy Morris", "1945-05-05") is None
    assert mod.approved_candidate("Judy Morrison", "1945-05-06") is None
    assert mod.approved_candidate("Sheba703 Harris789", "1926-01-08") is None
    p = mod.approved_candidate("Judy Morrison", "1945-05-05")
    assert (
        mod.approved_candidate(
            "Judy Morrison",
            "1945-05-05",
            roster={"synthetic": True, "patients": [p, p]},
        )
        is None
    )


def test_va_source_requires_unique_matching_name_birth_and_identifier(monkeypatch):
    p = mod.approved_candidate("Judy Morrison", "1945-05-05")
    row = {
        "name": [{"given": ["Judy"], "family": "Morrison"}],
        "birthDate": "1945-05-05",
        "identifier": [{"value": p["icn"]}],
    }
    monkeypatch.setattr(mod, "_get_bundle", lambda *a, **k: {})
    monkeypatch.setattr(mod, "_search_resources", lambda *a: [row])
    mod.verify_candidate_source(p)
    row["birthDate"] = "1945-05-06"
    with pytest.raises(PermissionError):
        mod.verify_candidate_source(p)
    monkeypatch.setattr(mod, "_search_resources", lambda *a: [])
    with pytest.raises(PermissionError):
        mod.verify_candidate_source(p)


def test_host_scope_and_source_failure_prevent_provisioning(monkeypatch):
    voice = "vs-" + str(uuid4())
    resolver = mod.SandboxCallerResolver(None, None, MagicMock())
    resolver._provision = MagicMock()
    resolver.authenticator.authenticate.return_value = SimpleNamespace(
        case_ids={"other"}
    )
    with pytest.raises(PermissionError):
        resolver.resolve(
            name="Judy Morrison", birth_date="1945-05-05", voice=voice, assertion="x"
        )
    resolver._provision.assert_not_called()
    resolver.authenticator.authenticate.return_value = SimpleNamespace(
        case_ids={resolver.case_id(voice)}, subject="trusted-host"
    )
    monkeypatch.setattr(
        mod, "verify_candidate_source", MagicMock(side_effect=PermissionError)
    )
    with pytest.raises(PermissionError):
        resolver.resolve(
            name="Judy Morrison", birth_date="1945-05-05", voice=voice, assertion="x"
        )
    resolver._provision.assert_not_called()
    assert not resolver.bindings


def test_two_callers_keep_separate_case_and_patient_bindings(monkeypatch):
    resolver = mod.SandboxCallerResolver(None, None, MagicMock())
    resolver._provision = MagicMock()
    monkeypatch.setattr(mod, "verify_candidate_source", lambda p: None)
    voices = ["vs-" + str(uuid4()), "vs-" + str(uuid4())]
    cases = []
    for voice, name, dob in zip(
        voices, ["Judy Morrison", "Ruben Moreno"], ["1945-05-05", "1949-12-30"]
    ):
        resolver.authenticator.authenticate.return_value = SimpleNamespace(
            case_ids={resolver.case_id(voice)}, subject="trusted-host"
        )
        cases.append(
            resolver.resolve(name=name, birth_date=dob, voice=voice, assertion="x")
        )
    assert cases[0] != cases[1]
    assert resolver.bindings[voices[0]][1] != resolver.bindings[voices[1]][1]
    with pytest.raises(PermissionError):
        resolver.read(cases[0], voices[1])
    resolver.bindings[voices[0]] = (cases[0], "test", 0)
    assert not resolver.bound(cases[0], voices[0])


def test_provision_rejects_ambiguous_database_patient_before_any_write(monkeypatch):
    conn = MagicMock()
    q = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
    q.fetchall.return_value = [(uuid4(),), (uuid4(),)]
    monkeypatch.setattr(
        mod, "assert_synthetic_scheduling_database", lambda *a, **k: "vab_test"
    )
    resolver = mod.SandboxCallerResolver(lambda: conn, None, None)
    with pytest.raises(PermissionError, match="Ambiguous"):
        resolver._provision(
            "case",
            "voice",
            mod.approved_candidate("Judy Morrison", "1945-05-05"),
            "host",
        )
    assert all(
        "INSERT" not in args[0][0] and "UPDATE " not in args[0][0]
        for args in q.execute.call_args_list
    )


def test_dynamic_flag_requires_authenticated_agent_browser_flow(monkeypatch):
    from veteran_access_bridge.app.trusted_voice_booking import (
        build_trusted_voice_booking,
    )

    monkeypatch.setenv("VAB_ENABLE_DYNAMIC_SANDBOX_CALLERS", "true")
    with pytest.raises(PermissionError, match="authenticated IBM"):
        build_trusted_voice_booking()


def test_offers_use_one_clinic_even_when_inventory_interleaves_locations(monkeypatch):
    import json

    conn = MagicMock()
    q = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
    patient = uuid4()
    slots = [uuid4() for _ in range(3)]
    q.fetchall.side_effect = [
        [(patient,)],
        [(slots[0], "clinic-A"), (slots[1], "clinic-B"), (slots[2], "clinic-A")],
    ]
    q.fetchone.side_effect = [
        None,
        None,
        (
            {
                "synthetic": True,
                "not_live_va_slots": True,
                "fixture_batch": "VAB-DEMO-20261113",
                "slot_bindings": {},
            },
        ),
    ]
    monkeypatch.setattr(
        mod, "assert_synthetic_scheduling_database", lambda *a, **k: "vab_test"
    )
    resolver = mod.SandboxCallerResolver(lambda: conn, None, None)
    resolver._provision(
        "case", "voice", mod.approved_candidate("Judy Morrison", "1945-05-05"), "host"
    )
    updates = [
        a[0]
        for a in q.execute.call_args_list
        if a[0][0].startswith("UPDATE vab_test.data_source")
    ]
    bindings = json.loads(updates[0][1][0])["slot_bindings"]
    assert set(bindings) == {str(slots[0]), str(slots[2])}


def test_end_releases_only_this_calls_unbooked_offers(monkeypatch):
    import json

    conn = MagicMock()
    q = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
    q.fetchone.return_value = (
        {
            "slot_bindings": {
                "available": {"case_id": "case"},
                "booked": {"case_id": "case"},
                "other": {"case_id": "other-case"},
            }
        },
    )
    q.fetchall.return_value = [("available",), ("other",)]
    q.rowcount = 1
    monkeypatch.setattr(
        mod, "assert_synthetic_scheduling_database", lambda *a, **k: "vab_test"
    )
    resolver = mod.SandboxCallerResolver(lambda: conn, None, None)
    monkeypatch.setattr(resolver, "bound", lambda case, voice: True)
    resolver.finish("case", "voice")
    args = q.execute.call_args_list[-1][0][1]
    bindings = json.loads(args[0])["slot_bindings"]
    assert set(bindings) == {"booked", "other"}
    assert all("DELETE" not in a[0][0] for a in q.execute.call_args_list)
    q.rowcount = 0
    with pytest.raises(PermissionError, match="Call-owned"):
        resolver.finish("case", "wrong-voice")


@pytest.mark.parametrize("blocker", ["active_call", "no_slots", "wrong_source"])
def test_database_preflight_failures_create_no_case_or_slot_binding(
    monkeypatch, blocker
):
    conn = MagicMock()
    q = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
    patient = uuid4()
    source = {
        "synthetic": True,
        "not_live_va_slots": True,
        "fixture_batch": "VAB-DEMO-20261113",
        "slot_bindings": {},
    }
    q.fetchall.side_effect = [[(patient,)], []]
    q.fetchone.side_effect = [
        None,
        (1,) if blocker == "active_call" else None,
        ({**source, "synthetic": blocker != "wrong_source"},),
    ]
    monkeypatch.setattr(
        mod, "assert_synthetic_scheduling_database", lambda *a, **k: "vab_test"
    )
    resolver = mod.SandboxCallerResolver(lambda: conn, None, None)
    with pytest.raises(PermissionError):
        resolver._provision(
            "case",
            "voice",
            mod.approved_candidate("Judy Morrison", "1945-05-05"),
            "host",
        )
    statements = [a[0][0] for a in q.execute.call_args_list]
    assert "pg_advisory_xact_lock" in statements[0]
    assert all(not s.startswith(("INSERT", "UPDATE")) for s in statements)


def test_private_factor_matches_va_source_before_provision(monkeypatch):
    monkeypatch.setenv("VAB_REQUIRE_MASKED_LAST_FOUR", "true")
    p = mod.approved_candidate("Judy Morrison", "1945-05-05")
    row = {
        "resourceType": "Patient",
        "name": [{"given": ["Judy"], "family": "Morrison"}],
        "birthDate": "1945-05-05",
        "identifier": [
            {"value": p["icn"]},
            {"system": "http://hl7.org/fhir/sid/us-ssn", "value": "123-45-0067"},
        ],
    }
    monkeypatch.setattr(mod, "_get_bundle", lambda *a, **k: {})
    monkeypatch.setattr(mod, "_search_resources", lambda *a: [row])
    mod.verify_candidate_source(p, last_four="0067")
    with pytest.raises(mod.AdditionalIdentityMismatch):
        mod.verify_candidate_source(p, last_four="0068")
    with pytest.raises(mod.AdditionalIdentityMismatch):
        mod.verify_candidate_source(p)
    voice = "vs-" + str(uuid4())
    resolver = mod.SandboxCallerResolver(None, None, MagicMock())
    resolver.authenticator.authenticate.return_value = SimpleNamespace(
        case_ids={resolver.case_id(voice)}, subject="host"
    )
    resolver._provision = MagicMock()
    assert (
        resolver.resolve(
            name="Judy Morrison",
            birth_date="1945-05-05",
            voice=voice,
            assertion="test",
            last_four="0068",
        )
        is None
    )
    resolver._provision.assert_not_called()
    assert not resolver.bindings
