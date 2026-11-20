"""Guardrails for six registered VA sandbox contracts."""
import asyncio
import pytest

from veteran_access_bridge.mcp.tools import va_sandbox_readonly as sandbox


EXPECTED = (
    "get_va_sandbox_health_facility",
    "search_va_sandbox_health_facilities",
    "get_va_sandbox_health_facility_service",
    "get_va_community_care_case_summary",
    "get_va_patient_health_sandbox_summary",
    "get_va_clinical_health_case_summary",
)


def test_all_six_fail_closed_without_verified_source():
    for name in EXPECTED:
        result = sandbox._unavailable(name, "synthetic-test-key")
        assert result["status"] == "UNAVAILABLE"
        assert result["source_verified"] is False
        assert result["authorization_granted"] is False
        assert result["booking_created"] is False
        assert result["community_care_eligibility_status"] == "UNVERIFIED"


@pytest.mark.parametrize("lookup", ["", "  ", None])
def test_missing_lookup_rejected(lookup):
    with pytest.raises(ValueError, match="Non-empty"):
        sandbox._unavailable(EXPECTED[0], lookup)


def test_all_six_are_registered_with_read_only_annotations():
    class Recorder:
        def __init__(self):
            self.tools = {}

        def tool(self, *, name, annotations):
            def decorate(fn):
                self.tools[name] = (fn, annotations)
                return fn
            return decorate

    recorder = Recorder()
    sandbox.register(recorder)
    assert set(recorder.tools) == set(EXPECTED)
    for name, (fn, annotations) in recorder.tools.items():
        assert annotations["readOnlyHint"] is True
        assert annotations["destructiveHint"] is False
        assert annotations["idempotentHint"] is True
        key = "query" if name == "search_va_sandbox_health_facilities" else (
            "facility_id" if name == "get_va_sandbox_health_facility" else (
                "facility_service_id" if name == "get_va_sandbox_health_facility_service" else "case_id"
            )
        )
        result = asyncio.run(fn(**{key: "synthetic-test-key"}))
        assert result["status"] == "UNAVAILABLE"


@pytest.mark.parametrize(
    "tool,key",
    [
        ("get_va_sandbox_health_facility", "DEMO-FACILITY-001"),
        ("search_va_sandbox_health_facilities", "primary care"),
        ("get_va_sandbox_health_facility_service", "DEMO-SERVICE-001"),
        ("get_va_community_care_case_summary", "DEMO-CASE-001"),
        ("get_va_patient_health_sandbox_summary", "DEMO-CASE-001"),
        ("get_va_clinical_health_case_summary", "DEMO-CASE-001"),
    ],
)
def test_explicit_demo_fixtures_are_non_authoritative(monkeypatch, tool, key):
    monkeypatch.setenv("VAB_VA_SANDBOX_SOURCE_MODE", "demo_fixture")
    result = sandbox._lookup(tool, key)
    assert result["status"] == "DEMO_FIXTURE"
    assert result["source"] == "local_fictional_fixture"
    assert result["source_verified"] is False
    assert result["authoritative_va_result"] is False
    assert result["authorization_granted"] is False
    assert result["booking_created"] is False
    assert result["community_care_eligibility_status"] == "UNVERIFIED"


def test_demo_mode_unknown_lookup_fails_closed(monkeypatch):
    monkeypatch.setenv("VAB_VA_SANDBOX_SOURCE_MODE", "demo_fixture")
    result = sandbox._lookup(EXPECTED[0], "unknown-facility")
    assert result["status"] == "UNAVAILABLE"


def test_default_mode_does_not_expose_fictional_fixture(monkeypatch):
    monkeypatch.delenv("VAB_VA_SANDBOX_SOURCE_MODE", raising=False)
    result = sandbox._lookup(EXPECTED[0], "DEMO-FACILITY-001")
    assert result["status"] == "UNAVAILABLE"
