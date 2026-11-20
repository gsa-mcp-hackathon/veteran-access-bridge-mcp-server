"""Dependency-free HTTP health/version routes for remote MCP transports."""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from veteran_access_bridge import __version__
from veteran_access_bridge.mcp.config import settings


def health_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "veteran-access-mcp",
        "synthetic_only": settings.synthetic_only,
    }


def version_payload() -> dict[str, str]:
    return {"version": __version__}


def register_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse(health_payload())

    @mcp.custom_route("/version", methods=["GET"])
    async def version(request: Request) -> JSONResponse:
        return JSONResponse(version_payload())
