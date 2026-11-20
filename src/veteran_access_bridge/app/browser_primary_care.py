"""Private helpers for the existing browser intake; never an MCP mutation tool."""

import json
import re
from urllib.parse import urlsplit

INTAKE_CASE = "DEMO-PC-VOICE-INTAKE-001"


def primary_care_requested(text: str) -> bool:
    """A request starts verification only; it never constitutes booking consent."""
    clean = re.sub(r"[^a-z ]", " ", text.lower())
    if re.search(r"\b(no|not|don|cancel|emergency|urgent|chest|suicide)\b", clean):
        return False
    return bool(
        re.search(r"\bprimary\s+care\b", clean)
        and re.search(r"\b(schedule|book|appointment)\b", clean)
    )


async def read_intake_via_mcp(issuer: str, api_key: str) -> dict:
    """Use the existing authenticated 21-tool server for intake context only.

    This fixture response is not patient verification, slot evidence or a grant.
    Those checks continue against independently read persisted vab_test records.
    """
    from fastmcp import Client

    from veteran_access_bridge.mcp.session_scope import runtime_context

    parsed = urlsplit(issuer)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or not api_key
    ):
        raise PermissionError("Pinned MCP origin and service credential required")
    token = runtime_context().get("vab_mcp_scope")
    if not token:
        raise PermissionError("Authenticated host turn required for MCP intake")
    async with Client(issuer.rstrip("/") + "/mcp", auth=api_key) as client:
        result = await client.call_tool(
            "get_scheduling_encounter", {"case_id": INTAKE_CASE, "session_scope": token}
        )
    if len(result.content) != 1 or not hasattr(result.content[0], "text"):
        raise PermissionError("Structured MCP intake result required")
    payload = json.loads(result.content[0].text)
    if (
        not isinstance(payload, dict)
        or payload.get("case_id") != INTAKE_CASE
        or payload.get("synthetic") is not True
        or payload.get("read_only") is not True
    ):
        raise PermissionError("MCP intake result has unexpected scope")
    return payload
