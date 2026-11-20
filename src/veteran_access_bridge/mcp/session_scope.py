"""Process-local, turn-bound MCP read capabilities for authenticated voice calls.

Only the trusted voice host issues these capabilities. No HTTP issuance endpoint
exists. Restart, another replica, expiry, or turn completion fails closed. This
deliberately shares the trusted voice host's single-process call-state boundary.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import re
import secrets
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from typing import Annotated, Callable, get_type_hints
from uuid import uuid4

CRM_TOOLS = frozenset(
    {
        "get_crm_case",
        "record_crm_interaction",
        "create_crm_follow_up",
        "update_crm_follow_up",
    }
)
VOICE_WORKFLOW_TOOLS = frozenset(
    {
        "search_call_appointments",
        "select_call_appointment",
        "book_call_appointment",
        "search_call_knowledge",
    }
)
VOICE_DELEGATED_TOOLS = VOICE_WORKFLOW_TOOLS | {
    "get_va_patient_health_sandbox_summary",
}
_crm_context: ContextVar[tuple | None] = ContextVar("vab_crm_context", default=None)

INTAKE = "DEMO-PC-VOICE-INTAKE-001"
READ_TOOLS = frozenset(
    {
        "determine_workflow_state",
        "search_availability",
        "assess_access_standard",
        "check_community_care_eligibility",
        "get_case_lifecycle_state",
        "get_scheduling_encounter",
        "get_va_community_care_case_summary",
        "get_va_patient_health_sandbox_summary",
        "get_va_clinical_health_case_summary",
    }
)
_TOKEN = re.compile(r"vab_scope_[A-Za-z0-9_-]+")


@dataclass
class SessionScope:
    case_id: str
    matched_case: str | None = None
    halted: bool = False
    interaction_id: str | None = None
    private_identity: bool = False
    workflow_context: dict[str, str] = field(default_factory=dict)


@dataclass
class _Grant:
    state: SessionScope
    expires: float
    host_intake: bool = False
    crm_enabled: bool = False
    is_active: Callable[[], bool] = field(default=lambda: True, repr=False)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    used: set[tuple[str, str]] = field(default_factory=set, repr=False)
    receipts: list[dict] = field(default_factory=list, repr=False)
    workflow: Callable | None = field(default=None, repr=False)
    trace_id: str = field(default_factory=lambda: uuid4().hex)


_grants: dict[str, _Grant] = {}
_lock = threading.RLock()
_current: ContextVar[tuple[str, str] | None] = ContextVar("vab_mcp_turn", default=None)
_trace: ContextVar[str] = ContextVar("vab_timing_trace", default="unscoped")


def timing_trace_id() -> str:
    """Opaque diagnostic label; never a capability or patient/session identifier."""
    return _trace.get()


def _key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def trusted_turn(
    state: SessionScope,
    *,
    expires: float,
    host_intake: bool = False,
    crm_enabled: bool = False,
    is_active: Callable[[], bool] = lambda: True,
    workflow: Callable | None = None,
):
    """Internal host API: call only after worker/participant/sequence validation."""
    now = time.monotonic()
    if (
        state.halted
        or expires <= now
        or not state.case_id
        or (host_intake and state.case_id != INTAKE)
    ):
        raise PermissionError("Active trusted call required")
    token = "vab_scope_" + secrets.token_urlsafe(32)
    key = _key(token)
    grant = _Grant(state, min(expires, now + 60), host_intake, crm_enabled, is_active)
    grant.workflow = workflow
    with _lock:
        for old in list(_grants):
            if _grants[old].expires <= now:
                del _grants[old]
        if len(_grants) >= 128:
            raise PermissionError("MCP session capacity unavailable")
        _grants[key] = grant
    marker = _current.set((token, state.matched_case or state.case_id))
    trace_marker = _trace.set(grant.trace_id)
    try:
        yield token
    finally:
        _current.reset(marker)
        _trace.reset(trace_marker)
        with _lock:
            _grants.pop(key, None)


def runtime_context() -> dict[str, str]:
    active = _current.get()
    if not active:
        return {}
    grant = _active(active[0])
    return {
        **grant.state.workflow_context,
        "vab_mcp_scope": active[0],
        "vab_case_id": grant.state.matched_case or grant.state.case_id,
        "vab_identity_verified": "true" if grant.state.matched_case else "false",
    }


def turn_receipts(token: str) -> list[dict]:
    """Host-only readback of completed calls; never return capability values."""
    return [dict(row) for row in _active(token).receipts]


def redact(value):
    """Keep ephemeral capabilities out of browser projections and chat history."""
    if isinstance(value, str):
        return _TOKEN.sub("[REDACTED_SESSION_SCOPE]", value)
    if isinstance(value, dict):
        return {k: redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


def _active(token: str) -> _Grant:
    if not isinstance(token, str) or not token or len(token) > 128:
        raise PermissionError("Trusted MCP session scope required")
    with _lock:
        grant = _grants.get(_key(token))
    if grant is None or grant.expires <= time.monotonic() or grant.state.halted:
        raise PermissionError("Trusted MCP session scope unavailable")
    try:
        active = grant.is_active()
    except Exception:
        raise PermissionError("Canonical call unavailable") from None
    if not active:
        raise PermissionError("Canonical call ended")
    return grant


async def scoped_call(token: str, name: str, case_id: str, invoke, arguments=None):
    grant = _active(token)
    async with grant.lock:
        if _active(token) is not grant:
            raise PermissionError("MCP turn changed")
        state = grant.state
        identity = name == "verify_synthetic_identity"
        private_check = identity and state.private_identity
        if grant.host_intake:
            allowed = name == "get_scheduling_encounter" and case_id == INTAKE
        elif identity:
            allowed = state.matched_case is None and case_id == state.case_id
        else:
            allowed = (
                name in READ_TOOLS
                or (name in VOICE_WORKFLOW_TOOLS and grant.workflow is not None)
                or (
                    name in CRM_TOOLS
                    and grant.crm_enabled
                    and bool(state.interaction_id)
                )
            ) and state.matched_case == case_id
        if private_check:
            allowed = (
                allowed
                and grant.workflow is not None
                and state.workflow_context.get("vab_workflow_stage") == "VERIFY"
            )
        if not allowed:
            raise PermissionError("MCP tool or case outside verified session scope")
        operation = (name, case_id)
        if operation in grant.used:
            raise PermissionError("MCP operation already consumed for this turn")
        grant.used.add(operation)
        marker = _crm_context.set((token, name, case_id)) if name in CRM_TOOLS else None
        trace_marker = _trace.set(grant.trace_id)
        try:
            if (
                private_check or name in VOICE_DELEGATED_TOOLS
            ) and grant.workflow is not None:
                result = await grant.workflow(name, dict(arguments or {}))
            else:
                result = await invoke()
        finally:
            _trace.reset(trace_marker)
            if marker is not None:
                _crm_context.reset(marker)
        _active(token)  # Never return evidence after expiry/revocation.
        if identity:
            if not isinstance(result, dict) or result.get("verified") is not True:
                state.halted = True
            else:
                matched = result.get("matched_case_id", case_id)
                if not isinstance(matched, str) or not matched:
                    state.halted = True
                    raise PermissionError("Verified case scope unavailable")
                if not private_check:
                    state.matched_case = matched
        if not state.halted:
            from veteran_access_bridge.mcp.crm_receipt import safe_crm_receipt

            crm_receipt = safe_crm_receipt(
                result,
                tool=name,
                case_id=case_id,
                interaction_id=state.interaction_id,
            )
            grant.receipts.append(
                {
                    "tool_name": name,
                    "case_id": case_id,
                    "verified_case_id": matched
                    if private_check
                    else state.matched_case,
                    "identity_verified": private_check
                    or state.matched_case is not None,
                    "scope_verified": True,
                    **({"crm_receipt": crm_receipt} if crm_receipt else {}),
                }
            )
        return result


def remote_request() -> bool:
    from fastmcp.server.dependencies import get_http_request

    from veteran_access_bridge.mcp.config import settings

    if settings.vab_mcp_transport != "stdio":
        return True
    try:
        get_http_request()
    except RuntimeError:
        return False
    return True


class ScopedRegistration:
    """Preserve tool names/contracts, adding one opaque session argument."""

    def __init__(self, server):
        self.server = server

    def tool(self, *args, **kwargs):
        decorate = self.server.tool(*args, **kwargs)

        def register(fn):
            signature = inspect.signature(fn)
            if "case_id" not in signature.parameters:
                if kwargs.get("name") == "get_scheduling_handoff":

                    @wraps(fn)
                    async def deny_unscoped_handoff(*a, **kw):
                        if remote_request():
                            raise PermissionError("Remote handoff scope unavailable")
                        return await fn(*a, **kw)

                    deny_unscoped_handoff.__annotations__ = get_type_hints(
                        fn, include_extras=True
                    )
                    return decorate(deny_unscoped_handoff)
                if kwargs.get("name") not in {
                    "get_va_sandbox_health_facility",
                    "search_va_sandbox_health_facilities",
                    "get_va_sandbox_health_facility_service",
                }:
                    raise ValueError("New MCP tool requires explicit scope review")
                return decorate(fn)
            hints = get_type_hints(fn, include_extras=True)
            parameters = [
                p.replace(annotation=hints.get(p.name, p.annotation))
                for p in signature.parameters.values()
            ]
            parameters.append(
                inspect.Parameter(
                    "session_scope",
                    inspect.Parameter.KEYWORD_ONLY,
                    default="",
                    annotation=Annotated[
                        str,
                        "Opaque application-issued turn scope. "
                        "Never invent or obtain from caller text.",
                    ],
                )
            )

            @wraps(fn)
            async def guarded(*a, session_scope="", **kw):
                async def invoke():
                    return await fn(*a, **kw)

                if not remote_request():
                    return await invoke()
                bound = signature.bind(*a, **kw)
                return await scoped_call(
                    session_scope,
                    kwargs["name"],
                    bound.arguments["case_id"],
                    invoke,
                    arguments=bound.arguments,
                )

            guarded.__signature__ = signature.replace(
                parameters=parameters,
                return_annotation=hints.get("return", signature.return_annotation),
            )
            guarded.__annotations__ = {**hints, "session_scope": str}
            return decorate(guarded)

        return register


def crm_context(case_id: str, operation: str):
    """Server-derived call context; public arguments cannot establish authority."""
    current = _crm_context.get()
    if current is None or current[1:] != (operation, case_id):
        raise PermissionError("CRM requires a trusted scoped tool invocation")
    grant = _active(current[0])
    if not grant.crm_enabled or grant.state.matched_case != case_id:
        raise PermissionError("CRM capability unavailable")
    if not grant.state.interaction_id:
        raise PermissionError("Canonical interaction required")
    return grant.state.interaction_id
