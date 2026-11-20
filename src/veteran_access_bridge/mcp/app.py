"""Veteran Access MCP server entry point."""

from __future__ import annotations

from fastmcp import FastMCP

from veteran_access_bridge.mcp.config import settings
from veteran_access_bridge.mcp.routes import register_routes
from veteran_access_bridge.mcp.tools import register_tools

mcp = FastMCP(
    name="Veteran Access MCP",
    instructions=(
        "Governed synthetic interoperability layer for Veteran specialty "
        "access scheduling. Use deterministic workflow gates. Do not diagnose, "
        "invent consults or authorizations, or perform real booking."
    ),
)
register_tools(mcp)
register_routes(mcp)


def validate_transport(transport: str, api_key: str = "") -> None:
    """Validate the requested MCP transport and enforce the remote security gate.

    stdio is always allowed (local development).

    streamable-http requires a non-empty VAB_MCP_API_KEY.  This is a
    hackathon/demo service-authentication control — it is NOT production
    VA identity or session authentication.  Scheduler/Veteran authorization
    and case-scope enforcement are enforced separately by the service layer.

    All other transport values are rejected.

    Fails closed: any missing or invalid security configuration raises
    RuntimeError at startup before any tool is exposed.
    """
    if transport == "stdio":
        return

    if transport == "streamable-http":
        if not api_key or not api_key.strip():
            raise RuntimeError(
                "Remote MCP transport requires VAB_MCP_API_KEY to be set to a "
                "non-empty value. Set it via environment variable or IBM Code Engine "
                "secret. Do not commit secrets. "
                "(This is a demo service-auth control, not production VA identity.)"
            )
        return

    raise RuntimeError(
        f"Remote MCP transport is disabled for this synthetic MVP until "
        f"authentication, role authorization, and case scoping are enforced. "
        f"Unsupported transport: {transport!r}. Use 'stdio' or 'streamable-http'."
    )


def main() -> None:
    transport = settings.vab_mcp_transport
    validate_transport(transport, api_key=settings.vab_mcp_api_key)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
