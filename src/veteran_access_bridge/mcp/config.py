"""Configuration for the Veteran Access MCP server."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------------------------------------------------------------------------
    # MCP transport
    #
    # VAB_MCP_TRANSPORT=stdio        — local development (default)
    # VAB_MCP_TRANSPORT=streamable-http — remote deployment (requires VAB_MCP_API_KEY)
    # ---------------------------------------------------------------------------
    vab_mcp_transport: str = "stdio"

    # Backward-compatible alias: settings.mcp_transport still works.
    @property
    def mcp_transport(self) -> str:
        return self.vab_mcp_transport

    # ---------------------------------------------------------------------------
    # Remote transport security gate
    #
    # VAB_MCP_API_KEY must be a non-empty shared secret when using streamable-http.
    # Supply via environment variable or IBM Code Engine secret — never committed.
    #
    # This is a hackathon/demo service-authentication control.
    # It is NOT production VA identity or session authentication.
    # ---------------------------------------------------------------------------
    vab_mcp_api_key: str = ""

    # ---------------------------------------------------------------------------
    # HTTP binding (used when transport != stdio)
    # ---------------------------------------------------------------------------
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000

    # ---------------------------------------------------------------------------
    # Safety flag — production writes must remain disabled
    # ---------------------------------------------------------------------------
    synthetic_only: bool = True


settings = Settings()
