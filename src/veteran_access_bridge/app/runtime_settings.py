"""Application deployment/runtime configuration for IBM Code Engine.

Issue #82.

This module validates structure only. It never serializes secret values into
health/readiness responses.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicationRuntimeSettings:
    app_env: str
    orchestrate_runtime_mode: str
    orchestrate_agent_id: str
    msa_ui_allowed_origins: tuple[str, ...]
    event_stream_heartbeat_seconds: float
    event_stream_idle_timeout_seconds: float
    code_engine_revision: str | None
    code_engine_application: str | None
    remote_mcp_url: str | None
    orchestrate_base_url_configured: bool
    orchestrate_api_key_configured: bool
    orchestrate_bearer_token_configured: bool

    @classmethod
    def from_env(cls) -> "ApplicationRuntimeSettings":
        app_env = os.getenv("APP_ENV", os.getenv("VAB_ENV", "local_synthetic")).strip()
        runtime_mode = os.getenv("ORCHESTRATE_RUNTIME_MODE", "fake").strip().lower()
        if runtime_mode not in {"fake", "remote"}:
            raise ValueError("ORCHESTRATE_RUNTIME_MODE must be 'fake' or 'remote'.")

        origins = tuple(
            item.strip()
            for item in os.getenv("MSA_UI_ALLOWED_ORIGINS", "").split(",")
            if item.strip()
        )
        heartbeat = float(os.getenv("EVENT_STREAM_HEARTBEAT_SECONDS", "15"))
        idle_timeout = float(os.getenv("EVENT_STREAM_IDLE_TIMEOUT_SECONDS", "300"))
        if heartbeat <= 0:
            raise ValueError("EVENT_STREAM_HEARTBEAT_SECONDS must be positive.")
        if idle_timeout <= 0:
            raise ValueError("EVENT_STREAM_IDLE_TIMEOUT_SECONDS must be positive.")
        if idle_timeout < heartbeat:
            raise ValueError(
                "EVENT_STREAM_IDLE_TIMEOUT_SECONDS must be greater than or "
                "equal to EVENT_STREAM_HEARTBEAT_SECONDS."
            )

        base_url = os.getenv("ORCHESTRATE_BASE_URL", "").strip()
        api_key = os.getenv("ORCHESTRATE_API_KEY", "").strip()
        bearer = os.getenv("ORCHESTRATE_BEARER_TOKEN", "").strip()

        if runtime_mode == "remote":
            missing = []
            if not base_url:
                missing.append("ORCHESTRATE_BASE_URL")
            if not api_key and not bearer:
                missing.append("ORCHESTRATE_API_KEY or ORCHESTRATE_BEARER_TOKEN")
            if missing:
                raise ValueError(
                    "Remote watsonx Orchestrate runtime requires: " + ", ".join(missing)
                )

        remote_mcp_url = os.getenv("REMOTE_MCP_URL", "").strip() or None

        return cls(
            app_env=app_env,
            orchestrate_runtime_mode=runtime_mode,
            orchestrate_agent_id=os.getenv(
                "ORCHESTRATE_AGENT_ID",
                "veteran_access_agent",
            ).strip()
            or "veteran_access_agent",
            msa_ui_allowed_origins=origins,
            event_stream_heartbeat_seconds=heartbeat,
            event_stream_idle_timeout_seconds=idle_timeout,
            code_engine_revision=(
                os.getenv("K_REVISION", "").strip()
                or os.getenv("CODE_ENGINE_REVISION", "").strip()
                or None
            ),
            code_engine_application=(
                os.getenv("CE_APP", "").strip()
                or os.getenv("CODE_ENGINE_APPLICATION", "").strip()
                or None
            ),
            remote_mcp_url=remote_mcp_url,
            orchestrate_base_url_configured=bool(base_url),
            orchestrate_api_key_configured=bool(api_key),
            orchestrate_bearer_token_configured=bool(bearer),
        )

    def readiness_payload(self) -> dict[str, object]:
        return {
            "ready": True,
            "synthetic": True,
            "production_writes_enabled": False,
            "app_env": self.app_env,
            "orchestrate_runtime_mode": self.orchestrate_runtime_mode,
            "orchestrate_agent_id": self.orchestrate_agent_id,
            "orchestrate_base_url_configured": self.orchestrate_base_url_configured,
            "orchestrate_auth_mode": (
                "iam_api_key"
                if self.orchestrate_api_key_configured
                else "bearer_token"
                if self.orchestrate_bearer_token_configured
                else "none"
            ),
            "orchestrate_api_key_configured": self.orchestrate_api_key_configured,
            "orchestrate_bearer_token_configured": (
                self.orchestrate_bearer_token_configured
            ),
            "msa_ui_origins_configured": len(self.msa_ui_allowed_origins),
            "event_stream_heartbeat_seconds": self.event_stream_heartbeat_seconds,
            "event_stream_idle_timeout_seconds": (
                self.event_stream_idle_timeout_seconds
            ),
            "code_engine_revision": self.code_engine_revision,
            "code_engine_application": self.code_engine_application,
            "remote_mcp_url_configured": self.remote_mcp_url is not None,
        }
