from __future__ import annotations

import io
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

runner = SimpleNamespace(
    **runpy.run_path(
        str(
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "accept_synthetic_veteran_auth.py"
        )
    )
)


@pytest.fixture
def acceptance_environment():
    return {
        "VAB_RUN_SYNTHETIC_AUTH_ACCEPTANCE": "true",
        "VAB_ENABLE_SYNTHETIC_VETERAN_SESSIONS": "true",
        "VAB_SUPABASE_PROJECT_REF": runner.SUPABASE_PROJECT_REF,
        "VAB_SUPABASE_TEST_MODE": "true",
        "VAB_SUPABASE_TEST_DATABASE_URL": "restricted-test-url",
        "VAB_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test_key",
        "VAB_SYNTHETIC_AUTH_SUBJECT": str(runner.EXPECTED_SUBJECT),
        "VAB_SYNTHETIC_SESSION_PATIENT_ID": str(runner.EXPECTED_PATIENT),
        "VAB_SYNTHETIC_SESSION_IDENTITY_ID": str(runner.EXPECTED_IDENTITY_ID),
        "VAB_SYNTHETIC_SESSION_CASE_ID": runner.EXPECTED_CASE,
    }


def test_acceptance_requires_explicit_opt_in_and_safe_write_flags(
    acceptance_environment,
):
    runner._validate_opt_ins(acceptance_environment)

    for changed in (
        {"VAB_RUN_SYNTHETIC_AUTH_ACCEPTANCE": "false"},
        {"VAB_ENABLE_SYNTHETIC_VETERAN_SESSIONS": "false"},
        {"VAB_ENABLE_SUPABASE_TEST_WRITES": "true"},
        {"VAB_ENABLE_SUPABASE_SCHEDULING_WRITES": "true"},
        {"VAB_ENABLE_PRIVATE_PC_BOOKING_ENDPOINT": "true"},
        {"VAB_ENABLE_SYNTHETIC_SESSION_HOST_ISSUER": "true"},
    ):
        with pytest.raises(runner.AcceptanceBlocked):
            runner._validate_opt_ins(acceptance_environment | changed)


def test_acceptance_binding_must_match_reviewed_synthetic_case(
    acceptance_environment,
):
    binding = runner._binding_from_environment(acceptance_environment)
    assert binding.subject == runner.EXPECTED_SUBJECT
    assert binding.patient_id == runner.EXPECTED_PATIENT
    assert binding.identity_id == runner.EXPECTED_IDENTITY_ID
    assert binding.case_id == runner.EXPECTED_CASE

    with pytest.raises(runner.AcceptanceBlocked):
        runner._binding_from_environment(
            acceptance_environment | {"VAB_SYNTHETIC_SESSION_CASE_ID": "another-case"}
        )


def test_origin_uses_https_and_rejects_malformed_configured_origin():
    assert (
        runner._resolve_origin({"VAB_SYNTHETIC_SESSION_ORIGIN": "https://vab.example"})
        == "https://vab.example"
    )
    assert (
        runner._resolve_origin(
            {
                "VAB_SYNTHETIC_SESSION_ORIGIN": "https://<codespace-origin>",
                "CODESPACE_NAME": "vab",
                "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
            }
        )
        == "https://vab-4317.app.github.dev"
    )
    with pytest.raises(PermissionError):
        runner._resolve_origin(
            {
                "VAB_SYNTHETIC_SESSION_ORIGIN": "http://attacker.example",
                "CODESPACE_NAME": "vab",
                "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
            }
        )


def test_credentials_require_tty_when_restricted_secret_is_not_configured(
    monkeypatch,
):
    monkeypatch.setattr(runner.sys, "stdin", io.StringIO())
    monkeypatch.setattr(runner.sys, "stderr", io.StringIO())
    with pytest.raises(runner.AcceptanceBlocked, match="interactive terminal"):
        runner._credentials({})
