"""Tests for Issue #82 Code Engine runtime configuration."""

import pytest
from starlette.testclient import TestClient

from veteran_access_bridge.app.asgi import app
from veteran_access_bridge.app.runtime_settings import ApplicationRuntimeSettings
from veteran_access_bridge.services import OrchestrateConfig


def _clear_runtime_env(monkeypatch):
    for name in (
        "APP_ENV",
        "VAB_ENV",
        "ORCHESTRATE_RUNTIME_MODE",
        "ORCHESTRATE_BASE_URL",
        "ORCHESTRATE_BEARER_TOKEN",
        "ORCHESTRATE_API_KEY",
        "ORCHESTRATE_AGENT_ID",
        "MSA_UI_ALLOWED_ORIGINS",
        "EVENT_STREAM_HEARTBEAT_SECONDS",
        "EVENT_STREAM_IDLE_TIMEOUT_SECONDS",
        "CODE_ENGINE_APPLICATION",
        "CODE_ENGINE_REVISION",
        "K_REVISION",
        "CE_APP",
        "REMOTE_MCP_URL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_local_runtime_settings_do_not_require_ibm_credentials(monkeypatch):
    _clear_runtime_env(monkeypatch)

    settings = ApplicationRuntimeSettings.from_env()

    assert settings.app_env == "local_synthetic"
    assert settings.orchestrate_runtime_mode == "fake"
    assert settings.orchestrate_base_url_configured is False
    assert settings.orchestrate_bearer_token_configured is False


def test_remote_runtime_requires_server_side_orchestrate_config(monkeypatch):
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("ORCHESTRATE_RUNTIME_MODE", "remote")

    with pytest.raises(ValueError) as exc:
        ApplicationRuntimeSettings.from_env()

    message = str(exc.value)
    assert "ORCHESTRATE_BASE_URL" in message
    assert "ORCHESTRATE_API_KEY or ORCHESTRATE_BEARER_TOKEN" in message


def test_readiness_reports_presence_without_exposing_secret_values(monkeypatch):
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "code-engine")
    monkeypatch.setenv("ORCHESTRATE_RUNTIME_MODE", "remote")
    monkeypatch.setenv(
        "ORCHESTRATE_BASE_URL",
        "https://orchestrate.example.invalid/instance",
    )
    monkeypatch.setenv("ORCHESTRATE_API_KEY", "super-secret-api-key")
    monkeypatch.setenv("ORCHESTRATE_AGENT_ID", "89801bbc-fa87-41f9-b9d7-d2a9b4cbf0c3")
    monkeypatch.setenv(
        "MSA_UI_ALLOWED_ORIGINS",
        "https://scheduler.example.invalid,https://backup.example.invalid",
    )
    monkeypatch.setenv("K_REVISION", "veteran-access-bridge-00042")

    payload = ApplicationRuntimeSettings.from_env().readiness_payload()
    serialized = str(payload)

    assert payload["ready"] is True
    assert payload["app_env"] == "code-engine"
    assert payload["orchestrate_runtime_mode"] == "remote"
    assert payload["orchestrate_base_url_configured"] is True
    assert payload["orchestrate_auth_mode"] == "iam_api_key"
    assert payload["orchestrate_api_key_configured"] is True
    assert payload["orchestrate_bearer_token_configured"] is False
    assert payload["msa_ui_origins_configured"] == 2
    assert payload["code_engine_revision"] == "veteran-access-bridge-00042"
    assert "super-secret-api-key" not in serialized
    assert "orchestrate.example.invalid" not in serialized


def test_readiness_endpoint_is_safe_in_local_mode(monkeypatch):
    _clear_runtime_env(monkeypatch)

    with TestClient(app) as client:
        response = client.get("/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["orchestrate_runtime_mode"] == "fake"
    assert payload["orchestrate_api_key_configured"] is False
    assert payload["orchestrate_bearer_token_configured"] is False
    assert "super-secret-token" not in response.text
    assert "orchestrate.example.invalid" not in response.text


def test_invalid_stream_timeout_configuration_fails_readiness(monkeypatch):
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("EVENT_STREAM_HEARTBEAT_SECONDS", "30")
    monkeypatch.setenv("EVENT_STREAM_IDLE_TIMEOUT_SECONDS", "10")

    with TestClient(app) as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json()["ready"] is False


def test_orchestrate_config_from_env_has_clear_missing_variable_error(monkeypatch):
    _clear_runtime_env(monkeypatch)

    with pytest.raises(ValueError) as exc:
        OrchestrateConfig.from_env()

    message = str(exc.value)
    assert "ORCHESTRATE_BASE_URL" in message
    assert "ORCHESTRATE_API_KEY or ORCHESTRATE_BEARER_TOKEN" in message


def test_remote_runtime_accepts_iam_api_key_without_static_bearer(monkeypatch):
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("ORCHESTRATE_RUNTIME_MODE", "remote")
    monkeypatch.setenv(
        "ORCHESTRATE_BASE_URL",
        "https://orchestrate.example.invalid/instances/demo",
    )
    monkeypatch.setenv("ORCHESTRATE_API_KEY", "server-side-api-key")

    settings = ApplicationRuntimeSettings.from_env()
    config = OrchestrateConfig.from_env()

    assert settings.orchestrate_api_key_configured is True
    assert settings.orchestrate_bearer_token_configured is False
    assert config.api_key == "server-side-api-key"
    assert config.bearer_token is None
    assert config.chat_path == "/v2/orchestrate/{agent_id}/chat/completions"
