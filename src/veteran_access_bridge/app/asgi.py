"""Unified ASGI application for Veteran Access Bridge.

Uses FastAPI/Uvicorn so the demo HTTP application and the FastMCP MCP endpoint
can share a single process and a single port while preserving the existing
request handlers, SSE behavior, and governed business services.

The business logic (facade, auth, telemetry, services, adapters) is unchanged.
Only the HTTP server transport layer is replaced.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import time
from datetime import timedelta
from hmac import compare_digest
from http import HTTPStatus
from importlib.resources import files
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import (
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from livekit import api as livekit_api
from starlette.types import ASGIApp, Receive, Scope, Send

from veteran_access_bridge.app.auth import (
    AuthorizationError,
    DemoRole,
    authorize,
    principal_from_headers,
)
from veteran_access_bridge.app.calendar_projection import project_calendar_slots
from veteran_access_bridge.app.embed_auth import (
    EmbedAuthConfigurationError,
    create_embed_identity_token,
)
from veteran_access_bridge.app.facade import DEMO_CASE_ID, DemoApplication
from veteran_access_bridge.app.handoff_projection import (
    build_apparent_conflict,
    build_handoff_projection,
)
from veteran_access_bridge.app.live_interactions import (
    LiveInteractionService,
    LiveInteractionStatus,
    MsaInteractionAction,
)
from veteran_access_bridge.app.primary_care_demo import (
    PrimaryCareDemoLifecycle,
    apply_calendar_overlay,
    next_permitted_action,
)
from veteran_access_bridge.app.primary_care_demo import (
    to_dict as primary_care_demo_to_dict,
)
from veteran_access_bridge.app.runtime_settings import ApplicationRuntimeSettings
from veteran_access_bridge.app.telemetry import TelemetryStore
from veteran_access_bridge.domain import (
    ApplyVoiceEventRequest,
    CreateVoiceSessionRequest,
    InteractionChannel,
    event_to_dict,
)
from veteran_access_bridge.integrations.contracts import integration_readiness_report
from veteran_access_bridge.integrations.ibm_phone import (
    cdr_to_terminal_event,
    context_to_event,
    parse_cdr_webhook,
    verify_log_webhook_jwt,
)
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.tools.get_scheduling_encounter import (
    run as get_scheduling_encounter,
)
from veteran_access_bridge.services.voice_sessions import VoiceSessionRegistry
from veteran_access_bridge.services.voice_tts import (
    VoiceTTSService,
    VoiceTTSUnavailable,
)
from veteran_access_bridge.voice.dispatch_name import voice_agent_name
from veteran_access_bridge.voice.observer_readiness import (
    ObserverRoomNotReady,
    require_observer_room_ready,
)

APP = DemoApplication()
TELEMETRY = TelemetryStore()
LIVE_INTERACTIONS = LiveInteractionService()
PRIMARY_CARE_DEMO = PrimaryCareDemoLifecycle()
VOICE_TTS = VoiceTTSService()
VOICE_SESSIONS = VoiceSessionRegistry()


class MCPBearerAuthMiddleware:
    """Require the configured demo service key for remote MCP HTTP requests.

    This protects only the MCP sub-application. It is a hackathon/demo
    service-authentication control and is not production VA identity,
    session authentication, or authorization.
    """

    def __init__(self, app: ASGIApp, api_key: str) -> None:
        self.app = app
        self.api_key = api_key

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        authorization = headers.get("authorization", "")
        scheme, separator, credential = authorization.partition(" ")

        valid = (
            separator == " "
            and scheme.lower() == "bearer"
            and bool(credential)
            and compare_digest(credential, self.api_key)
        )
        if not valid:
            response = JSONResponse(
                {
                    "error": "Unauthorized",
                    "detail": "Remote MCP requires a valid Bearer service credential.",
                    "synthetic": True,
                },
                status_code=HTTPStatus.UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _static_bytes(name: str) -> bytes:
    return files("veteran_access_bridge.app.static").joinpath(name).read_bytes()


def _principal(request: Request):
    return principal_from_headers(
        request.headers.get("x-demo-role"),
        request.headers.get("x-demo-actor"),
        request.headers.get("x-demo-case"),
    )


def _json_resp(status: int, payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=payload, status_code=status)


def _record(
    *,
    action: str,
    role: str,
    success: bool,
    started: float,
    case_id: str,
    metadata: dict[str, Any] | None = None,
    interaction_id: str | None = None,
    correlation_id: str | None = None,
    orchestrate_run_id: str | None = None,
) -> None:
    TELEMETRY.record(
        action=action,
        actor_role=role,
        success=success,
        duration_ms=int((time.perf_counter() - started) * 1000),
        case_ref=case_id,
        metadata=metadata,
        interaction_id=interaction_id,
        correlation_id=correlation_id,
        orchestrate_run_id=orchestrate_run_id,
    )


def _runtime_observability_metadata(
    *,
    failure_code: str | None = None,
    normalized_event_type: str | None = None,
    terminal_status: str | None = None,
    recoverable: bool | None = None,
    tool_outcome: str | None = None,
) -> dict[str, Any]:
    settings = ApplicationRuntimeSettings.from_env()
    metadata: dict[str, Any] = {
        "runtime_mode": settings.orchestrate_runtime_mode,
        "app_env": settings.app_env,
        "retry_count": int(getattr(LIVE_INTERACTIONS.runtime, "last_retry_count", 0)),
    }
    if settings.code_engine_revision is not None:
        metadata["revision"] = settings.code_engine_revision
    if failure_code is not None:
        metadata["failure_code"] = failure_code
    if normalized_event_type is not None:
        metadata["normalized_event_type"] = normalized_event_type
    if terminal_status is not None:
        metadata["terminal_status"] = terminal_status
    if recoverable is not None:
        metadata["recoverable"] = recoverable
    if tool_outcome is not None:
        metadata["tool_outcome"] = tool_outcome
    return metadata


async def index(request: Request) -> Response:
    web_url = os.getenv("VAB_WEB_UI_URL", "").strip()
    if web_url:
        from urllib.parse import urlsplit

        parsed = urlsplit(web_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            return _json_resp(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "Invalid VAB_WEB_UI_URL.", "synthetic": True},
            )
        return RedirectResponse(web_url.rstrip("/") + "/", status_code=307)
    body = _static_bytes("index.html")
    return Response(
        content=body,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def legacy_index(request: Request) -> Response:
    return Response(
        content=_static_bytes("index.html"),
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def app_js(request: Request) -> Response:
    body = _static_bytes("app.js")
    return Response(
        content=body,
        media_type="text/javascript; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def styles_css(request: Request) -> Response:
    body = _static_bytes("styles.css")
    return Response(
        content=body,
        media_type="text/css; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


async def health(request: Request) -> JSONResponse:
    return _json_resp(
        HTTPStatus.OK,
        {
            "status": "ok",
            "synthetic": True,
            "production_writes_enabled": False,
            "milestones": ["M3", "M4", "M5", "M6"],
        },
    )


async def readiness(request: Request) -> JSONResponse:
    try:
        settings = ApplicationRuntimeSettings.from_env()
        return _json_resp(HTTPStatus.OK, settings.readiness_payload())
    except (KeyError, ValueError) as exc:
        return _json_resp(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "ready": False,
                "synthetic": True,
                "production_writes_enabled": False,
                "error": str(exc),
            },
        )


def _require_embed_issuer_service_key(request: Request) -> None:
    """Protect JWT signing from public clients and forged X-Demo-* headers.

    IBM Embed Security validates tokens but does not authorize who can mint
    them. Only a trusted application gateway with this distinct service secret
    may request an identity token; the private signing key stays in VAB.
    """
    expected = os.getenv("VAB_EMBED_TOKEN_SERVICE_KEY", "")
    supplied = request.headers.get("authorization", "")
    if len(expected) < 32 or not compare_digest(supplied, "Bearer " + expected):
        raise AuthorizationError("Embed token issuer access denied.")


async def api_orchestrate_embed_token(request: Request) -> JSONResponse:
    """Legacy server-to-server synthetic token; demo headers are not authentication."""

    try:
        _require_embed_issuer_service_key(request)
        principal = _principal(request)
        case_id = request.headers.get("x-demo-case", "").split(",")[0].strip()
        authorize(principal, case_id, "view_case")
        ttl = int(os.getenv("ORCHESTRATE_EMBED_TOKEN_TTL_SECONDS", "3600"))
        token, expires_at = create_embed_identity_token(
            subject=f"synthetic-veteran:{case_id}",
            lifetime_seconds=ttl,
        )
        return _json_resp(
            HTTPStatus.OK,
            {
                "identityToken": token,
                "expiresAt": expires_at,
                "synthetic": True,
            },
        )
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except (EmbedAuthConfigurationError, ValueError) as exc:
        return _json_resp(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {"error": str(exc), "synthetic": True},
        )


async def api_orchestrate_guest_embed_token(request: Request) -> JSONResponse:
    """Issue a signed, session-stable JWT only to the trusted guest BFF.

    No unauthenticated caller or browser may select case/actor/tool scope.
    A random opaque guest ID is not a verified Veteran identity and grants
    no authority for real scheduling actions or protected patient data.
    """
    try:
        _require_embed_issuer_service_key(request)
        if os.getenv("VAB_EMBED_GUEST_ENABLED", "false").lower() != "true":
            raise AuthorizationError("Guest embed token issuance is disabled.")
        body = await _post_body(request)
        if set(body) != {"guest_session_id"}:
            raise ValueError("Only guest_session_id is accepted.")
        guest_id = body["guest_session_id"]
        if not isinstance(guest_id, str) or not re.fullmatch(r"[0-9a-f]{32}", guest_id):
            raise ValueError("Invalid guest session.")
        ttl = int(os.getenv("VAB_EMBED_GUEST_TOKEN_TTL_SECONDS", "600"))
        if not 60 <= ttl <= 900:
            raise EmbedAuthConfigurationError("Invalid guest embed token lifetime.")
        token, expires_at = create_embed_identity_token(
            subject=f"synthetic-guest:{guest_id}",
            lifetime_seconds=ttl,
        )
        response = _json_resp(
            HTTPStatus.OK,
            {"identityToken": token, "expiresAt": expires_at, "synthetic": True},
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc), "synthetic": True})
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": "Invalid guest token request.", "synthetic": True},
        )
    except EmbedAuthConfigurationError:
        return _json_resp(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {"error": "Embed signing unavailable.", "synthetic": True},
        )


async def api_case_snapshot(request: Request) -> JSONResponse:
    started = time.perf_counter()
    case_id = request.path_params["case_id"]
    try:
        principal = _principal(request)
        authorize(principal, case_id, "view_case")
        include_audit = principal.role == DemoRole.SCHEDULER
        payload = APP.snapshot(case_id, include_audit=include_audit)
        _record(
            action="view_case",
            role=principal.role.value,
            success=True,
            started=started,
            case_id=case_id,
            metadata={
                "lifecycle_state": (payload.get("lifecycle") or {}).get("current_state")
            },
        )
        return _json_resp(HTTPStatus.OK, payload)
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_metrics(request: Request) -> JSONResponse:
    try:
        principal = _principal(request)
        authorize(principal, DEMO_CASE_ID, "view_metrics")
        return _json_resp(HTTPStatus.OK, TELEMETRY.summary())
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_observability(request: Request) -> JSONResponse:
    try:
        principal = _principal(request)
        if principal.role != DemoRole.SCHEDULER:
            raise AuthorizationError(
                "Operational observability requires SCHEDULER role."
            )
        return _json_resp(
            HTTPStatus.OK,
            {
                "summary": TELEMETRY.summary(),
                "recent": TELEMETRY.operational_snapshot(limit=50),
            },
        )
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )


async def api_integrations(request: Request) -> JSONResponse:
    try:
        principal = _principal(request)
        authorize(principal, DEMO_CASE_ID, "view_integrations")
        return _json_resp(HTTPStatus.OK, integration_readiness_report())
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def _post_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw:
        return {}
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON request body must be an object.")
    return payload


async def api_scheduler_select(request: Request) -> JSONResponse:
    started = time.perf_counter()
    action, case_id, role = "select_option", DEMO_CASE_ID, "UNKNOWN"
    try:
        principal = _principal(request)
        role = principal.role.value
        body = await _post_body(request)
        case_id = str(body.get("case_id", DEMO_CASE_ID))
        authorize(principal, case_id, action)
        result = APP.select_option(
            case_id=case_id,
            option_id=str(body["option_id"]),
            actor_id=principal.actor_id,
            idempotency_key=str(body["idempotency_key"]),
        )
        _record(
            action=action,
            role=role,
            success=True,
            started=started,
            case_id=case_id,
            metadata={"result": "ok"},
        )
        return _json_resp(HTTPStatus.OK, {"ok": True, "result": result})
    except AuthorizationError as exc:
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "authorization"},
        )
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "workflow"},
        )
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_scheduler_verify(request: Request) -> JSONResponse:
    started = time.perf_counter()
    action, case_id, role = "verify_option", DEMO_CASE_ID, "UNKNOWN"
    try:
        principal = _principal(request)
        role = principal.role.value
        body = await _post_body(request)
        case_id = str(body.get("case_id", DEMO_CASE_ID))
        authorize(principal, case_id, action)
        result = APP.verify_selected_option(
            case_id=case_id,
            actor_id=principal.actor_id,
            evidence_ref=str(body["evidence_ref"]),
            outcome=str(body.get("outcome", "VERIFIED")),
            idempotency_key=str(body["idempotency_key"]),
        )
        _record(
            action=action,
            role=role,
            success=True,
            started=started,
            case_id=case_id,
            metadata={"result": "ok"},
        )
        return _json_resp(HTTPStatus.OK, {"ok": True, "result": result})
    except AuthorizationError as exc:
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "authorization"},
        )
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "workflow"},
        )
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_scheduler_request_confirmation(request: Request) -> JSONResponse:
    started = time.perf_counter()
    action, case_id, role = "request_confirmation", DEMO_CASE_ID, "UNKNOWN"
    try:
        principal = _principal(request)
        role = principal.role.value
        body = await _post_body(request)
        case_id = str(body.get("case_id", DEMO_CASE_ID))
        authorize(principal, case_id, action)
        result = APP.request_veteran_confirmation(case_id=case_id)
        _record(
            action=action,
            role=role,
            success=True,
            started=started,
            case_id=case_id,
            metadata={"result": "ok"},
        )
        return _json_resp(HTTPStatus.OK, {"ok": True, "result": result})
    except AuthorizationError as exc:
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "authorization"},
        )
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "workflow"},
        )
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_veteran_respond(request: Request) -> JSONResponse:
    started = time.perf_counter()
    action, case_id, role = "respond_confirmation", DEMO_CASE_ID, "UNKNOWN"
    try:
        principal = _principal(request)
        role = principal.role.value
        body = await _post_body(request)
        case_id = str(body.get("case_id", DEMO_CASE_ID))
        authorize(principal, case_id, action)
        response_val = str(body["response"])
        result = APP.record_veteran_response(
            case_id=case_id,
            actor_id=principal.actor_id,
            response=response_val,
            idempotency_key=str(body["idempotency_key"]),
        )
        if response_val == "DECLINED":
            action = "veteran_decline"
        elif response_val == "REQUESTED_CHANGE":
            action = "request_change"
        _record(
            action=action,
            role=role,
            success=True,
            started=started,
            case_id=case_id,
            metadata={"result": "ok"},
        )
        return _json_resp(HTTPStatus.OK, {"ok": True, "result": result})
    except AuthorizationError as exc:
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "authorization"},
        )
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "workflow"},
        )
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_scheduler_commit(request: Request) -> JSONResponse:
    started = time.perf_counter()
    action, case_id, role = "commit_booking", DEMO_CASE_ID, "UNKNOWN"
    try:
        principal = _principal(request)
        role = principal.role.value
        body = await _post_body(request)
        case_id = str(body.get("case_id", DEMO_CASE_ID))
        authorize(principal, case_id, action)
        result = APP.commit_selected_booking(
            case_id=case_id,
            actor_id=principal.actor_id,
            idempotency_key=str(body["idempotency_key"]),
            appointment_intent=str(body.get("appointment_intent", "INITIAL_CONSULT")),
        )
        _record(
            action=action,
            role=role,
            success=True,
            started=started,
            case_id=case_id,
            metadata={"result": "ok"},
        )
        return _json_resp(HTTPStatus.OK, {"ok": True, "result": result})
    except AuthorizationError as exc:
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "authorization"},
        )
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        code = (
            "slot_unavailable"
            if "slot" in msg.lower()
            else (
                "authorization"
                if "authorization" in msg.lower() or "hsrm" in msg.lower()
                else "workflow"
            )
        )
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": code},
        )
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": msg, "synthetic": True},
        )


def _require_scheduler_case(request: Request, case_id: str):
    principal = _principal(request)
    if principal.role != DemoRole.SCHEDULER:
        raise AuthorizationError(
            "MSA live interaction endpoints require SCHEDULER role."
        )
    if case_id not in principal.case_ids:
        raise AuthorizationError(
            f"Actor {principal.actor_id!r} is not scoped to case {case_id!r}."
        )
    return principal


def _interaction_snapshot_payload(snapshot) -> dict[str, Any]:
    correlation = snapshot.correlation
    runtime = snapshot.runtime_interaction
    return {
        "synthetic": True,
        "interaction_id": correlation.interaction_id,
        "case_id": correlation.case_id,
        "scheduling_encounter_id": correlation.scheduling_encounter_id,
        "correlation_id": correlation.correlation_id,
        "channel": correlation.channel.value,
        "orchestrate_run_id": correlation.orchestrate_run_id,
        "orchestrate_session_id": correlation.orchestrate_session_id,
        "agent_id": runtime.agent_id if runtime else None,
        "event_count": snapshot.event_count,
        "status": snapshot.status.value,
        "human_control_mode": snapshot.human_control_mode.value,
        "runtime_failure_code": snapshot.runtime_failure_code,
    }


async def api_scheduling_encounter(request: Request) -> JSONResponse:
    try:
        case_id = request.path_params["case_id"]
        _require_scheduler_case(request, case_id)
        encounter = get_scheduling_encounter(case_id)
        calendar = [to_jsonable(item) for item in project_calendar_slots(encounter)]
        scheduling_encounter_id = f"SE-{case_id}-{encounter['request']['request_id']}"
        demo = PRIMARY_CARE_DEMO.get(case_id, scheduling_encounter_id)
        calendar = apply_calendar_overlay(calendar, demo)
        handoff = build_handoff_projection(encounter, calendar)
        handoff["next_permitted_action"] = next_permitted_action(demo)
        return _json_resp(
            HTTPStatus.OK,
            {
                "synthetic": True,
                "case_id": case_id,
                "scheduling_encounter_id": scheduling_encounter_id,
                "encounter": encounter,
                "calendar": calendar,
                "handoff": handoff,
                "demo_a": primary_care_demo_to_dict(demo),
            },
        )
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except (KeyError, ValueError) as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_voice_session_create(request: Request) -> JSONResponse:
    """Create canonical call state before a provider transport is attached."""
    try:
        body = await _post_body(request)
        case_id = str(body["case_id"])
        _require_scheduler_case(request, case_id)
        session = VOICE_SESSIONS.create(CreateVoiceSessionRequest.model_validate(body))
        return _json_resp(
            HTTPStatus.CREATED,
            session.model_dump(mode="json"),
        )
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except (KeyError, ValueError) as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_voice_session_get(request: Request) -> JSONResponse:
    try:
        voice_session_id = request.path_params["voice_session_id"]
        session = VOICE_SESSIONS.get(voice_session_id)
        _require_scheduler_case(request, session.case_id)
        return _json_resp(HTTPStatus.OK, session.model_dump(mode="json"))
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except KeyError as exc:
        return _json_resp(
            HTTPStatus.NOT_FOUND,
            {"error": str(exc), "synthetic": True},
        )


async def api_voice_session_renew(request: Request) -> JSONResponse:
    try:
        session = VOICE_SESSIONS.get(request.path_params["voice_session_id"])
        _require_scheduler_case(request, session.case_id)
        host = getattr(request.app.state, "trusted_voice_booking", None)
        if host is None:
            raise PermissionError("Voice host unavailable")
        return _json_resp(HTTPStatus.OK, await host.renew_call(session))
    except (AuthorizationError, PermissionError, KeyError):
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": "call_renewal_denied"})
    except Exception:
        return _json_resp(
            HTTPStatus.SERVICE_UNAVAILABLE, {"error": "call_renewal_unavailable"}
        )


async def api_voice_session_event(request: Request) -> JSONResponse:
    """Apply one normalized provider-independent voice event."""
    try:
        voice_session_id = request.path_params["voice_session_id"]
        session = VOICE_SESSIONS.get(voice_session_id)
        _require_scheduler_case(request, session.case_id)
        body = await _post_body(request)
        updated, event = VOICE_SESSIONS.apply_event(
            voice_session_id,
            ApplyVoiceEventRequest.model_validate(body),
        )
        after_call = None
        host = getattr(request.app.state, "trusted_voice_booking", None)
        if updated.state.value in {"ENDED", "FAILED"} and host is not None:
            reason = event.payload.get("end_reason", "CALLER_ENDED")
            if reason not in {"CALLER_ENDED", "DISCONNECTED", "TIME_LIMIT"}:
                reason = "DISCONNECTED"
            after_call = await host.finalize_call(updated, reason)
        return _json_resp(
            HTTPStatus.OK,
            {
                "session": updated.model_dump(mode="json"),
                "event": event.model_dump(mode="json"),
                **({"after_call": after_call} if after_call is not None else {}),
            },
        )
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except KeyError as exc:
        return _json_resp(
            HTTPStatus.NOT_FOUND,
            {"error": str(exc), "synthetic": True},
        )
    except ValueError as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_ibm_phone_context(
    request: Request,
) -> JSONResponse:
    """Apply documented IBM voice_telephony context to a canonical session.

    This endpoint is intended for a trusted Orchestrate/tool bridge, not as a
    claim that IBM Phone posts live call context directly to this URL.
    """
    try:
        voice_session_id = request.path_params["voice_session_id"]
        session = VOICE_SESSIONS.get(voice_session_id)
        _require_scheduler_case(request, session.case_id)
        body = await _post_body(request)
        updated, event = VOICE_SESSIONS.apply_event(
            voice_session_id,
            context_to_event(body),
        )
        return _json_resp(
            HTTPStatus.OK,
            {
                "session": updated.model_dump(mode="json"),
                "event": event.model_dump(mode="json"),
            },
        )
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except KeyError as exc:
        return _json_resp(
            HTTPStatus.NOT_FOUND,
            {"error": str(exc), "synthetic": True},
        )
    except ValueError as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_ibm_phone_cdr_webhook(request: Request) -> JSONResponse:
    """Receive IBM's supported post-call CDR log webhook."""
    secret = os.getenv("IBM_PHONE_LOG_WEBHOOK_SECRET", "")
    if not secret:
        return _json_resp(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "IBM phone log webhook secret is not configured.",
                "synthetic": True,
            },
        )

    try:
        verify_log_webhook_jwt(request.headers.get("authorization"), secret)
        body = await _post_body(request)
        cdr = parse_cdr_webhook(body)
        session = None
        if cdr.sip_call_id:
            session = VOICE_SESSIONS.find_by_provider_call_id(cdr.sip_call_id)
        if session is None and cdr.global_session_id:
            session = VOICE_SESSIONS.find_by_provider_session_id(cdr.global_session_id)

        if session is None:
            return _json_resp(
                HTTPStatus.ACCEPTED,
                {
                    "accepted": True,
                    "correlated": False,
                    "provider": "IBM_PHONE",
                },
            )

        if session.state.value in {"ENDED", "FAILED"}:
            return _json_resp(
                HTTPStatus.OK,
                {
                    "accepted": True,
                    "correlated": True,
                    "already_terminal": True,
                    "voice_session_id": session.voice_session_id,
                    "state": session.state.value,
                },
            )

        updated, event = VOICE_SESSIONS.apply_event(
            session.voice_session_id,
            cdr_to_terminal_event(body),
        )
        return _json_resp(
            HTTPStatus.OK,
            {
                "accepted": True,
                "correlated": True,
                "voice_session_id": updated.voice_session_id,
                "state": updated.state.value,
                "event_id": event.event_id,
                "transfer_occurred": cdr.transfer_occurred,
            },
        )
    except ValueError as exc:
        return _json_resp(
            HTTPStatus.UNAUTHORIZED,
            {"error": str(exc), "synthetic": True},
        )


async def api_voice_status(request: Request) -> JSONResponse:
    """Return non-secret provider-neutral voice transport readiness."""
    provider = os.getenv("IBM_PHONE_PROVIDER", "UNCONFIGURED").strip().upper()
    phone_configured = os.getenv(
        "IBM_PHONE_CHANNEL_CONFIGURED", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    webrtc_gateway = os.getenv("VAB_WEBRTC_GATEWAY", "UNCONFIGURED").strip().upper()
    webrtc_gateway_configured = os.getenv(
        "VAB_WEBRTC_GATEWAY_CONFIGURED", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    webrtc_signaling_configured = bool(
        os.getenv("VAB_WEBRTC_SIGNALING_URL", "").strip()
    )
    browser_softphone_requested = os.getenv(
        "VAB_WEBRTC_SOFTPHONE_ENABLED", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    browser_softphone_enabled = (
        browser_softphone_requested
        and webrtc_gateway_configured
        and webrtc_signaling_configured
    )

    if browser_softphone_enabled:
        mode = "BROWSER_WEBRTC"
        active_provider = webrtc_gateway
        configured = True
    else:
        mode = "IBM_PHONE"
        active_provider = provider
        configured = phone_configured

    return _json_resp(
        HTTPStatus.OK,
        {
            "synthetic": True,
            "transport": {
                "mode": mode,
                "provider": active_provider,
                "configured": configured,
                "browser_softphone_enabled": browser_softphone_enabled,
                "embedded_ui_enabled": False,
                "ibm_phone": {
                    "provider": provider,
                    "configured": phone_configured,
                },
                "webrtc": {
                    "gateway": webrtc_gateway,
                    "configured": webrtc_gateway_configured,
                    "signaling_configured": webrtc_signaling_configured,
                    "requested": browser_softphone_requested,
                    "media_owner": "VAB_EXTERNAL_GATEWAY",
                },
            },
            "tts": VOICE_TTS.readiness(),
        },
    )


def _require_msa_monitor_gateway(request: Request, case_id: str) -> None:
    """Require a server-only key AND synthetic case scope; never use demo headers alone.

    This local sandbox gateway is disabled by default. The service key must not
    appear in JavaScript, browser requests, logs, or public Lovable settings.
    A production integration requires independently verified MSA identity.
    """
    enabled = os.getenv("VAB_MSA_MONITOR_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    expected = os.getenv("VAB_MSA_MONITOR_SERVICE_KEY", "")
    provided = request.headers.get("authorization", "")
    if not enabled or len(expected) < 32:
        raise AuthorizationError("MSA monitor gateway is disabled.")
    if not compare_digest(provided, "Bearer " + expected):
        raise AuthorizationError("MSA monitor gateway access denied.")
    _require_scheduler_case(request, case_id)


def _safe_monitor_value(value: Any) -> str | None:
    """Only emit small opaque identifiers; never raw tool args or result objects."""
    if not isinstance(value, str) or not 1 <= len(value) <= 100:
        return None
    if not all(char.isalnum() or char in "._:-" for char in value):
        return None
    return value


def _structured_identity_verified(result: Any, depth: int = 0) -> bool | None:
    """Extract only an explicit bool from an observed identity MCP result.

    IBM tool content may be JSON text or a small structured content envelope.
    No free-text inference, extraction from speech, or arbitrary recursive
    scanning of tool output is allowed.
    """
    if depth > 2:
        return None
    if isinstance(result, str):
        if len(result) > 4096:
            return None
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            return None
    if not isinstance(result, dict):
        return None
    verified = result.get("verified")
    if type(verified) is bool:
        return verified
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        verified = structured.get("verified")
        if type(verified) is bool:
            return verified
    content = result.get("content")
    if isinstance(content, list) and len(content) == 1:
        item = content[0]
        if (
            isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        ):
            return _structured_identity_verified(item["text"], depth + 1)
    return None


def _msa_monitor_event(event: Any) -> dict[str, Any]:
    """Minimum-necessary source event metadata for the browser.

    Speech content (which may contain verification inputs) and MCP
    arguments/results stay on the backend. A voice transcript is NOT
    considered verified merely because a speech event exists.
    """
    raw = event_to_dict(event)
    kind = str(raw.get("event_type", ""))
    payload = raw.get("payload", {})
    safe_payload: dict[str, Any] = {}
    if isinstance(payload, dict) and kind in {"mcp_tool_called", "mcp_tool_result"}:
        for key in ("tool_name", "tool_call_id", "status", "error_code"):
            safe = _safe_monitor_value(payload.get(key))
            if safe is not None:
                safe_payload[key] = safe
        if (
            kind == "mcp_tool_result"
            and raw.get("source") == "application"
            and payload.get("evidence") == "server_scope_receipt"
            and payload.get("scope_verified") is True
            and payload.get("invoked_by") == "agent"
        ):
            operation = _safe_monitor_value(payload.get("server_operation_id"))
            if (
                payload.get("tool_name") == "verify_synthetic_identity"
                and operation
                and re.fullmatch(r"identity-[0-9a-f]{32}", operation)
            ):
                safe_payload["server_operation_id"] = operation
            safe_payload["scope_verified"] = True
            safe_payload["invoked_by"] = "agent"
            safe_payload["evidence"] = "server_scope_receipt"
            voice = _safe_monitor_value(payload.get("voice_session_id"))
            if voice is not None:
                safe_payload["voice_session_id"] = voice
            verified_case = _safe_monitor_value(payload.get("verified_case_id"))
            if verified_case is not None:
                safe_payload["verified_case_id"] = verified_case
            from veteran_access_bridge.mcp.crm_receipt import safe_crm_receipt

            crm = safe_crm_receipt(
                payload.get("crm_receipt"),
                tool=payload.get("tool_name"),
                case_id=verified_case,
                interaction_id=raw.get("interaction_id"),
            )
            voice = _safe_monitor_value(payload.get("voice_session_id"))
            if crm and voice and payload.get("status") == "succeeded":
                safe_payload["crm_receipt"] = crm
                safe_payload["voice_session_id"] = voice
        # A completed identity tool call is NOT identity verification. Only
        # expose a literal boolean outcome from the actual governed result.
        # Never parse or forward arbitrary tool text or result dictionaries.
        if (
            kind == "mcp_tool_result"
            and payload.get("tool_name") == "verify_synthetic_identity"
        ):
            verified = _structured_identity_verified(payload.get("result"))
            if verified is not None:
                safe_payload["verified"] = verified
    elif kind == "options_presented" and raw.get("source") == "application":
        from veteran_access_bridge.app.voice_booking_projection import (
            project_voice_options,
        )

        safe_payload = (
            project_voice_options(payload) if isinstance(payload, dict) else {}
        )
    elif kind in {"veteran_utterance", "agent_answered"}:
        safe_payload["transcript_available"] = False
    elif (
        kind in {"slot_verified", "simulated_booking_recorded"}
        and raw.get("source") == "application"
        and isinstance(payload, dict)
    ):
        from veteran_access_bridge.app.voice_booking_projection import (
            project_voice_booking,
        )

        safe_payload = project_voice_booking(
            payload,
            booked=kind == "simulated_booking_recorded",
        )
    # No arbitrary payload contents, raw patient identifiers, tool arguments,
    # returned appointment inventory or voice transcript are forwarded.
    return {
        key: raw[key]
        for key in (
            "event_id",
            "event_type",
            "interaction_id",
            "case_id",
            "scheduling_encounter_id",
            "correlation_id",
            "source",
            "occurred_at",
            "synthetic",
        )
        if key in raw
    } | {"payload": safe_payload}


async def api_msa_monitor_events(request: Request) -> JSONResponse:
    """Read-only, case-scoped, sanitized canonical event projection."""
    try:
        interaction_id = request.path_params["interaction_id"]
        snapshot = LIVE_INTERACTIONS.snapshot(interaction_id)
        _require_msa_monitor_gateway(request, snapshot.correlation.case_id)
        cursor = request.query_params.get("cursor") or None
        events = LIVE_INTERACTIONS.events.get_events_after(interaction_id, cursor)[:100]
        projected = [_msa_monitor_event(event) for event in events]
        return _json_resp(
            HTTPStatus.OK,
            {
                "interaction_id": interaction_id,
                "case_id": snapshot.correlation.case_id,
                "scheduling_encounter_id": snapshot.correlation.scheduling_encounter_id,
                "correlation_id": snapshot.correlation.correlation_id,
                "status": snapshot.status.value,
                "human_control_mode": snapshot.human_control_mode.value,
                "events": projected,
                "next_cursor": events[-1].event_id if events else cursor,
                "synthetic": True,
                "transcript_verified": False,
                # Room connection must be observed separately.
                "media_connected": False,
            },
        )
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc), "synthetic": True})
    except KeyError as exc:
        return _json_resp(HTTPStatus.NOT_FOUND, {"error": str(exc), "synthetic": True})
    except ValueError as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST, {"error": str(exc), "synthetic": True}
        )


# A separate service-to-service read path for the *current synthetic caller*.
# This never issues LiveKit observer JWTs and never reuses MSA staff authorization.
_CALL_ACTIVITY_CASE = "DEMO-PC-VOICE-INTAKE-001"
_CALL_ACTIVITY_CURSOR = re.compile(r"^[A-Za-z0-9_.:=-]{1,256}$")


async def api_caller_activity_events(request: Request) -> JSONResponse:
    """Return minimal, canonical events for an existing synthetic voice session.

    The public browser never calls this endpoint directly with credentials:
    the trusted frontend BFF validates its own per-call guest capability and
    forwards a separate server-only service key. Disabled by default.
    """
    try:
        enabled = os.getenv("VAB_CALL_ACTIVITY_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        expected = os.getenv("VAB_CALL_ACTIVITY_SERVICE_KEY", "")
        if not enabled or len(expected) < 32:
            raise AuthorizationError("Caller activity is disabled.")
        if not compare_digest(
            request.headers.get("authorization", ""), "Bearer " + expected
        ):
            raise AuthorizationError("Caller activity access denied.")

        voice_session_id = request.path_params["voice_session_id"]
        session = VOICE_SESSIONS.get(voice_session_id)
        # Guest capability is *only* for this fixed, unidentified synthetic
        # voice intake case; other patient/scheduler cases remain inaccessible.
        if session.case_id != _CALL_ACTIVITY_CASE:
            raise AuthorizationError("Caller activity case not permitted.")
        _require_scheduler_case(request, session.case_id)

        snapshot = LIVE_INTERACTIONS.snapshot(session.interaction_id)
        scope = snapshot.correlation
        if (
            scope.case_id != session.case_id
            or scope.scheduling_encounter_id != session.scheduling_encounter_id
            or scope.interaction_id != session.interaction_id
            or scope.correlation_id != session.correlation_id
        ):
            raise AuthorizationError("Caller activity session scope mismatch.")
        cursor = request.query_params.get("cursor") or None
        if cursor is not None and not _CALL_ACTIVITY_CURSOR.fullmatch(cursor):
            raise ValueError("Invalid event cursor.")
        events = LIVE_INTERACTIONS.events.get_events_after(
            session.interaction_id, cursor
        )[:100]
        return _json_resp(
            HTTPStatus.OK,
            {
                "synthetic": True,
                "voice_session_id": voice_session_id,
                "interaction_id": session.interaction_id,
                "case_id": session.case_id,
                "correlation_id": scope.correlation_id,
                "scheduling_encounter_id": session.scheduling_encounter_id,
                "status": snapshot.status.value,
                "human_control_mode": snapshot.human_control_mode.value,
                "events": [_msa_monitor_event(event) for event in events],
                "next_cursor": events[-1].event_id if events else cursor,
                "transcript_verified": False,
                "media_connected": False,
            },
        )
    except AuthorizationError:
        return _json_resp(
            HTTPStatus.FORBIDDEN, {"error": "forbidden", "synthetic": True}
        )
    except KeyError:
        return _json_resp(
            HTTPStatus.NOT_FOUND, {"error": "not_found", "synthetic": True}
        )
    except ValueError:
        return _json_resp(
            HTTPStatus.BAD_REQUEST, {"error": "invalid_request", "synthetic": True}
        )


async def api_msa_monitor_token(request: Request) -> JSONResponse:
    """Issue read-only room subscriber credentials to the trusted local MSA gateway.

    Not a Veteran token, not a publishing participant, and not a handoff
    acceptance. Deployment to a public interface requires a separate
    actor-bound application authentication gate.
    """
    try:
        voice_session_id = request.path_params["voice_session_id"]
        session = VOICE_SESSIONS.get(voice_session_id)
        _require_msa_monitor_gateway(request, session.case_id)
        snapshot = LIVE_INTERACTIONS.snapshot(session.interaction_id)
        if (
            snapshot.correlation.case_id != session.case_id
            or snapshot.correlation.scheduling_encounter_id
            != session.scheduling_encounter_id
        ):
            raise AuthorizationError("Voice session / encounter scope mismatch.")
        if session.state.value in {"ENDED", "FAILED"}:
            raise ValueError("Cannot monitor a terminal voice session.")
        gateway = os.getenv("VAB_WEBRTC_GATEWAY", "").strip().upper()
        configured = os.getenv("VAB_WEBRTC_GATEWAY_CONFIGURED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        server_url = os.getenv("VAB_WEBRTC_SIGNALING_URL", "").strip()
        api_key = os.getenv("LIVEKIT_API_KEY", "").strip()
        api_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
        if gateway != "LIVEKIT" or not configured or not server_url:
            raise ValueError("LiveKit gateway not configured.")
        if not api_key or not api_secret:
            raise ValueError("LiveKit credentials are not configured.")
        # An observer must never create the first room: that would suppress
        # the Veteran token's room-creation-only Avery agent dispatch. Read the
        # authoritative room, caller and dispatch state before issuing a JWT.
        room_name = "vab-" + voice_session_id
        try:
            async with livekit_api.LiveKitAPI(
                url=server_url, api_key=api_key, api_secret=api_secret
            ) as lk:
                await require_observer_room_ready(
                    api=lk,
                    room_name=room_name,
                    voice_session_id=voice_session_id,
                    interaction_id=session.interaction_id,
                    case_id=session.case_id,
                    scheduling_encounter_id=session.scheduling_encounter_id,
                )
        except ObserverRoomNotReady:
            return _json_resp(
                HTTPStatus.CONFLICT,
                {"error": "voice_room_not_ready", "synthetic": True},
            )
        except Exception:
            # Fail closed on LiveKit API outages without exposing credentials
            # or allowing observers to become room-creating participants.
            return _json_resp(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "voice_room_readiness_unavailable", "synthetic": True},
            )
        ttl_seconds = 120
        participant_identity = "msa-observer-" + secrets.token_hex(8)
        token = (
            livekit_api.AccessToken(api_key, api_secret)
            .with_identity(participant_identity)
            .with_metadata(
                json.dumps(
                    {
                        "role": "msa_observer",
                        "voice_session_id": voice_session_id,
                        "interaction_id": session.interaction_id,
                        "case_id": session.case_id,
                    },
                    separators=(",", ":"),
                )
            )
            .with_grants(
                livekit_api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=False,
                    can_subscribe=True,
                    can_publish_data=False,
                )
            )
            .with_ttl(timedelta(seconds=ttl_seconds))
            .to_jwt()
        )
        return _json_resp(
            HTTPStatus.OK,
            {
                "server_url": server_url,
                "participant_token": token,
                "voice_session_id": voice_session_id,
                "interaction_id": session.interaction_id,
                "case_id": session.case_id,
                "room_name": room_name,
                "capability": "subscribe_only",
                "synthetic": True,
                "expires_in_seconds": ttl_seconds,
            },
        )
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc), "synthetic": True})
    except KeyError as exc:
        return _json_resp(HTTPStatus.NOT_FOUND, {"error": str(exc), "synthetic": True})
    except ValueError as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST, {"error": str(exc), "synthetic": True}
        )


async def api_webrtc_token(request: Request) -> JSONResponse:
    """Issue a short-lived LiveKit room token for one canonical VoiceSession."""
    try:
        voice_session_id = request.path_params["voice_session_id"]
        session = VOICE_SESSIONS.get(voice_session_id)
        _require_scheduler_case(request, session.case_id)

        gateway = os.getenv("VAB_WEBRTC_GATEWAY", "UNCONFIGURED").strip().upper()
        configured = os.getenv(
            "VAB_WEBRTC_GATEWAY_CONFIGURED", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
        server_url = os.getenv("VAB_WEBRTC_SIGNALING_URL", "").strip()
        api_key = os.getenv("LIVEKIT_API_KEY", "").strip()
        api_secret = os.getenv("LIVEKIT_API_SECRET", "").strip()
        ttl_seconds = int(os.getenv("VAB_WEBRTC_TOKEN_TTL_SECONDS", "300"))

        if gateway != "LIVEKIT" or not configured or not server_url:
            raise ValueError("LiveKit WebRTC gateway is not configured.")
        if not api_key or not api_secret:
            raise ValueError("LiveKit server credentials are not configured.")
        if ttl_seconds < 30 or ttl_seconds > 3600:
            raise ValueError(
                "VAB_WEBRTC_TOKEN_TTL_SECONDS must be between 30 and 3600."
            )

        room_name = f"vab-{voice_session_id}"
        participant_identity = f"veteran-{secrets.token_hex(8)}"
        participant_metadata = json.dumps(
            {
                "vab_role": "veteran_caller",
                "voice_session_id": voice_session_id,
                "interaction_id": session.interaction_id,
                "case_id": session.case_id,
                "scheduling_encounter_id": session.scheduling_encounter_id,
            },
            separators=(",", ":"),
        )
        token = (
            livekit_api.AccessToken(api_key, api_secret)
            .with_identity(participant_identity)
            .with_metadata(participant_metadata)
            .with_grants(
                livekit_api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    # Same-room accessibility replies are still untrusted input;
                    # only the worker bound to this caller can process the topic.
                    can_publish_data=True,
                )
            )
            .with_room_config(
                livekit_api.RoomConfiguration(
                    agents=[
                        livekit_api.RoomAgentDispatch(
                            agent_name=voice_agent_name(),
                        )
                    ]
                )
            )
            .with_ttl(timedelta(seconds=ttl_seconds))
            .to_jwt()
        )
        trusted_voice = getattr(request.app.state, "trusted_voice_booking", None)
        if trusted_voice is not None:
            trusted_voice.bind(
                voice_session_id=voice_session_id,
                case_id=session.case_id,
                room_name=room_name,
                participant_identity=participant_identity,
                interaction_id=session.interaction_id,
            )
        return _json_resp(
            HTTPStatus.OK,
            {
                "server_url": server_url,
                "participant_token": token,
                "room_name": room_name,
                "participant_identity": participant_identity,
                "voice_session_id": voice_session_id,
                "expires_in_seconds": ttl_seconds,
                "synthetic": True,
            },
        )
    except (AuthorizationError, PermissionError) as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except KeyError as exc:
        return _json_resp(
            HTTPStatus.NOT_FOUND,
            {"error": str(exc), "synthetic": True},
        )
    except (ValueError, TypeError) as exc:
        return _json_resp(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {"error": str(exc), "synthetic": True},
        )


async def api_voice_synthesize(request: Request) -> Response:
    try:
        body = await _post_body(request)
        case_id = str(body["case_id"])
        _require_scheduler_case(request, case_id)
        text = str(body["text"])
        audio, media_type = await VOICE_TTS.synthesize(text)
        return Response(
            content=audio,
            media_type=media_type,
            headers={
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except (KeyError, ValueError) as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )
    except VoiceTTSUnavailable as exc:
        return _json_resp(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": str(exc),
                "fallback": "browser",
                "synthetic": True,
            },
        )


async def api_interactions_create(request: Request) -> JSONResponse:
    started = time.perf_counter()
    try:
        body = await _post_body(request)
        case_id = str(body["case_id"])
        _require_scheduler_case(request, case_id)
        encounter_id = str(body["scheduling_encounter_id"])
        embedded_channel = bool(body.get("embedded_channel", False))
        if case_id.startswith("DEMO-PC-") and not embedded_channel:
            PRIMARY_CARE_DEMO.reset(case_id, encounter_id)
        channel = InteractionChannel(str(body.get("channel", "PHONE")).upper())
        initial_message = body.get("initial_message")
        agent_opening = bool(body.get("agent_opening", False))
        snapshot = await LIVE_INTERACTIONS.create_interaction(
            case_id=case_id,
            scheduling_encounter_id=encounter_id,
            channel=channel,
            initial_message=(
                str(initial_message) if initial_message is not None else None
            ),
            agent_opening=agent_opening,
            invoke_runtime=not embedded_channel,
        )
        payload = _interaction_snapshot_payload(snapshot)
        payload["embedded_channel"] = embedded_channel
        failed = snapshot.runtime_failure_code is not None
        _record(
            action="interaction_create",
            role="SCHEDULER",
            success=not failed,
            started=started,
            case_id=case_id,
            metadata=_runtime_observability_metadata(
                failure_code=snapshot.runtime_failure_code,
                normalized_event_type=(
                    "human_attention_recommended" if failed else "interaction_received"
                ),
                terminal_status=(
                    "RECOVERABLE_FAILURE" if failed else "INTERACTION_ACTIVE"
                ),
                recoverable=failed,
            ),
            interaction_id=snapshot.correlation.interaction_id,
            correlation_id=snapshot.correlation.correlation_id,
            orchestrate_run_id=snapshot.correlation.orchestrate_run_id,
        )
        if failed:
            payload.update(
                {
                    "recoverable": True,
                    "state_preserved": True,
                    "error": (
                        "Avery runtime unavailable: "
                        + str(snapshot.runtime_failure_code or "ORCHESTRATE_FAILURE")
                    ),
                }
            )
            return _json_resp(HTTPStatus.SERVICE_UNAVAILABLE, payload)
        return _json_resp(HTTPStatus.CREATED, payload)
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc), "synthetic": True})
    except (KeyError, ValueError) as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_interaction_get(request: Request) -> JSONResponse:
    try:
        interaction_id = request.path_params["interaction_id"]
        snapshot = LIVE_INTERACTIONS.snapshot(interaction_id)
        _require_scheduler_case(request, snapshot.correlation.case_id)
        return _json_resp(HTTPStatus.OK, _interaction_snapshot_payload(snapshot))
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc), "synthetic": True})
    except KeyError as exc:
        return _json_resp(HTTPStatus.NOT_FOUND, {"error": str(exc), "synthetic": True})


async def api_primary_care_demo_action(request: Request) -> JSONResponse:
    started = time.perf_counter()
    interaction_id = request.path_params["interaction_id"]
    interaction = None
    action = "UNKNOWN"
    try:
        interaction = LIVE_INTERACTIONS.snapshot(interaction_id)
        _require_scheduler_case(request, interaction.correlation.case_id)
        body = await _post_body(request)
        action = str(body["action"]).upper()

        case_id = interaction.correlation.case_id
        encounter_id = interaction.correlation.scheduling_encounter_id
        correlation_id = interaction.correlation.correlation_id
        encounter = get_scheduling_encounter(case_id)
        eligible_ids = {
            str(option["option_id"]) for option in encounter.get("eligible_options", ())
        }

        if action == "SELECT":
            record = PRIMARY_CARE_DEMO.select(
                case_id=case_id,
                scheduling_encounter_id=encounter_id,
                option_id=str(body["option_id"]),
                eligible_option_ids=eligible_ids,
                event_store=LIVE_INTERACTIONS.events,
                interaction_id=interaction_id,
                correlation_id=correlation_id,
            )
        elif action == "VERIFY":
            record = PRIMARY_CARE_DEMO.verify(
                case_id=case_id,
                scheduling_encounter_id=encounter_id,
                option_id=str(body["option_id"]),
                event_store=LIVE_INTERACTIONS.events,
                interaction_id=interaction_id,
                correlation_id=correlation_id,
            )
        elif action == "CONFIRM":
            record = PRIMARY_CARE_DEMO.confirm(
                case_id=case_id,
                scheduling_encounter_id=encounter_id,
                event_store=LIVE_INTERACTIONS.events,
                interaction_id=interaction_id,
                correlation_id=correlation_id,
            )
        elif action == "APPROVE":
            record = PRIMARY_CARE_DEMO.approve(
                case_id=case_id,
                scheduling_encounter_id=encounter_id,
                event_store=LIVE_INTERACTIONS.events,
                interaction_id=interaction_id,
                correlation_id=correlation_id,
            )
        elif action == "BOOK":
            record = PRIMARY_CARE_DEMO.book(
                case_id=case_id,
                scheduling_encounter_id=encounter_id,
                event_store=LIVE_INTERACTIONS.events,
                interaction_id=interaction_id,
                correlation_id=correlation_id,
            )
        else:
            raise ValueError(f"Unsupported Demo A action {action!r}.")

        _record(
            action=f"primary_care_{action.lower()}",
            role="SCHEDULER",
            success=True,
            started=started,
            case_id=case_id,
            metadata=_runtime_observability_metadata(
                normalized_event_type=f"primary_care_{action.lower()}",
                terminal_status=record.state.value,
                recoverable=False,
                tool_outcome=record.state.value,
            ),
            interaction_id=interaction_id,
            correlation_id=correlation_id,
            orchestrate_run_id=interaction.correlation.orchestrate_run_id,
        )
        return _json_resp(
            HTTPStatus.OK,
            {
                "synthetic": True,
                "production_write": False,
                "demo_a": primary_care_demo_to_dict(record),
            },
        )
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except (KeyError, ValueError) as exc:
        if interaction is not None:
            _record(
                action=f"primary_care_{action.lower()}",
                role="SCHEDULER",
                success=False,
                started=started,
                case_id=interaction.correlation.case_id,
                metadata=_runtime_observability_metadata(
                    failure_code="DETERMINISTIC_ACTION_REJECTED",
                    normalized_event_type=f"primary_care_{action.lower()}",
                    terminal_status="STATE_PRESERVED",
                    recoverable=True,
                    tool_outcome="REJECTED",
                ),
                interaction_id=interaction_id,
                correlation_id=interaction.correlation.correlation_id,
                orchestrate_run_id=interaction.correlation.orchestrate_run_id,
            )
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {
                "error": str(exc),
                "synthetic": True,
                "recoverable": True,
                "state_preserved": True,
            },
        )


async def api_interaction_action(request: Request) -> JSONResponse:
    try:
        interaction_id = request.path_params["interaction_id"]
        snapshot = LIVE_INTERACTIONS.snapshot(interaction_id)
        _require_scheduler_case(request, snapshot.correlation.case_id)
        body = await _post_body(request)
        action = MsaInteractionAction(str(body["action"]).upper())
        updated = LIVE_INTERACTIONS.record_msa_action(
            interaction_id=interaction_id,
            action=action,
        )
        return _json_resp(
            HTTPStatus.OK,
            _interaction_snapshot_payload(updated),
        )
    except AuthorizationError as exc:
        return _json_resp(
            HTTPStatus.FORBIDDEN,
            {"error": str(exc), "synthetic": True},
        )
    except KeyError as exc:
        return _json_resp(
            HTTPStatus.NOT_FOUND,
            {"error": str(exc), "synthetic": True},
        )
    except ValueError as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_embedded_interaction_event(request: Request) -> JSONResponse:
    """Mirror observable IBM embedded-chat messages into the MSA event stream."""

    try:
        interaction_id = request.path_params["interaction_id"]
        snapshot = LIVE_INTERACTIONS.snapshot(interaction_id)
        _require_scheduler_case(request, snapshot.correlation.case_id)
        body = await _post_body(request)
        event = LIVE_INTERACTIONS.record_embedded_message(
            interaction_id=interaction_id,
            direction=str(body["direction"]),
            text=str(body["text"]),
            thread_id=(
                str(body["thread_id"]) if body.get("thread_id") is not None else None
            ),
        )
        return _json_resp(HTTPStatus.OK, event_to_dict(event))
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc), "synthetic": True})
    except KeyError as exc:
        return _json_resp(HTTPStatus.NOT_FOUND, {"error": str(exc), "synthetic": True})
    except ValueError as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_veteran_secure_demo_message(request: Request) -> JSONResponse:
    """Synthetic-only Veteran chat entrypoint; never a production secure inbox.

    A separate route prevents the MSA's monitoring persona from impersonating
    a Veteran through the conversational write path.
    """
    try:
        interaction_id = request.path_params["interaction_id"]
        snapshot = LIVE_INTERACTIONS.snapshot(interaction_id)
        authorize(
            _principal(request),
            snapshot.correlation.case_id,
            "send_secure_demo_message",
        )
        if snapshot.correlation.channel is not InteractionChannel.CHAT:
            raise ValueError("Secure demo messages require a CHAT interaction.")
        if snapshot.status is LiveInteractionStatus.CALL_ENDED:
            raise ValueError("This interaction has ended.")
        body = await _post_body(request)
        message = body.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("A nonempty message is required.")
        if len(message) > 4000:
            raise ValueError("Message exceeds the 4000-character demo limit.")
        event = await LIVE_INTERACTIONS.send_message(
            interaction_id=interaction_id,
            message=message.strip(),
        )
        payload = event_to_dict(event)
        if event.payload.get("failure_code"):
            payload.update({"recoverable": True, "state_preserved": True})
            return _json_resp(HTTPStatus.SERVICE_UNAVAILABLE, payload)
        return _json_resp(HTTPStatus.OK, payload)
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc), "synthetic": True})
    except KeyError as exc:
        return _json_resp(HTTPStatus.NOT_FOUND, {"error": str(exc), "synthetic": True})
    except ValueError as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


async def api_interaction_message(request: Request) -> JSONResponse:
    started = time.perf_counter()
    try:
        interaction_id = request.path_params["interaction_id"]
        snapshot = LIVE_INTERACTIONS.snapshot(interaction_id)
        _require_scheduler_case(request, snapshot.correlation.case_id)
        body = await _post_body(request)
        message = str(body["message"])

        event = None
        if "earliest" in message.lower() and snapshot.correlation.case_id.startswith(
            "DEMO-PC-"
        ):
            encounter = get_scheduling_encounter(snapshot.correlation.case_id)
            calendar = [to_jsonable(item) for item in project_calendar_slots(encounter)]
            conflict = build_apparent_conflict(calendar)
            if conflict is not None:
                event = LIVE_INTERACTIONS.append_grounded_agent_explanation(
                    interaction_id=interaction_id,
                    text=str(conflict["explanation"]),
                    evidence_type="SCHEDULING_ENCOUNTER_ELIGIBILITY",
                )

        if event is None:
            event = await LIVE_INTERACTIONS.send_message(
                interaction_id=interaction_id,
                message=message,
            )

        updated = LIVE_INTERACTIONS.snapshot(interaction_id)
        failure_code = event.payload.get("failure_code")
        failed = bool(failure_code)
        _record(
            action="interaction_message",
            role="SCHEDULER",
            success=not failed,
            started=started,
            case_id=updated.correlation.case_id,
            metadata=_runtime_observability_metadata(
                failure_code=(str(failure_code) if failure_code else None),
                normalized_event_type=event.event_type.value,
                terminal_status=(
                    "RECOVERABLE_FAILURE" if failed else "MESSAGE_COMPLETED"
                ),
                recoverable=failed,
            ),
            interaction_id=interaction_id,
            correlation_id=updated.correlation.correlation_id,
            orchestrate_run_id=updated.correlation.orchestrate_run_id,
        )
        response_payload = event_to_dict(event)
        if failed:
            response_payload["recoverable"] = True
            response_payload["state_preserved"] = True
            return _json_resp(HTTPStatus.SERVICE_UNAVAILABLE, response_payload)
        return _json_resp(HTTPStatus.OK, response_payload)
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc), "synthetic": True})
    except KeyError as exc:
        return _json_resp(
            HTTPStatus.NOT_FOUND,
            {"error": str(exc), "synthetic": True},
        )
    except ValueError as exc:
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


def _sse_frame(event) -> str:
    payload = json.dumps(event_to_dict(event), separators=(",", ":"))
    return f"id: {event.event_id}\nevent: {event.event_type.value}\ndata: {payload}\n\n"


async def api_interaction_events(request: Request) -> StreamingResponse | JSONResponse:
    try:
        interaction_id = request.path_params["interaction_id"]
        snapshot = LIVE_INTERACTIONS.snapshot(interaction_id)
        _require_scheduler_case(request, snapshot.correlation.case_id)
    except AuthorizationError as exc:
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc), "synthetic": True})
    except KeyError as exc:
        return _json_resp(HTTPStatus.NOT_FOUND, {"error": str(exc), "synthetic": True})

    cursor = request.headers.get("last-event-id") or request.query_params.get("cursor")
    once = request.query_params.get("once", "").lower() in {"1", "true", "yes"}
    runtime_settings = ApplicationRuntimeSettings.from_env()
    poll_seconds = 0.25
    heartbeat_ticks_max = max(
        1,
        int(runtime_settings.event_stream_heartbeat_seconds / poll_seconds),
    )

    async def stream():
        last_id = cursor
        heartbeat_ticks = 0
        idle_started = time.monotonic()
        stream_started = time.perf_counter()
        while True:
            events = LIVE_INTERACTIONS.events.get_events_after(interaction_id, last_id)
            for event in events:
                yield _sse_frame(event)
                last_id = event.event_id
                idle_started = time.monotonic()
            if once:
                return
            if await request.is_disconnected():
                _record(
                    action="sse_stream",
                    role="SCHEDULER",
                    success=False,
                    started=stream_started,
                    case_id=snapshot.correlation.case_id,
                    metadata=_runtime_observability_metadata(
                        failure_code="UI_CLIENT_DISCONNECT",
                        normalized_event_type="sse_disconnect",
                        terminal_status="CLIENT_DISCONNECTED",
                        recoverable=True,
                    ),
                    interaction_id=interaction_id,
                    correlation_id=snapshot.correlation.correlation_id,
                    orchestrate_run_id=snapshot.correlation.orchestrate_run_id,
                )
                return
            if (
                time.monotonic() - idle_started
                >= runtime_settings.event_stream_idle_timeout_seconds
            ):
                _record(
                    action="sse_stream",
                    role="SCHEDULER",
                    success=False,
                    started=stream_started,
                    case_id=snapshot.correlation.case_id,
                    metadata=_runtime_observability_metadata(
                        failure_code="SSE_IDLE_TIMEOUT",
                        normalized_event_type="sse_idle_timeout",
                        terminal_status="RECONNECT_REQUIRED",
                        recoverable=True,
                    ),
                    interaction_id=interaction_id,
                    correlation_id=snapshot.correlation.correlation_id,
                    orchestrate_run_id=snapshot.correlation.orchestrate_run_id,
                )
                return
            heartbeat_ticks += 1
            if heartbeat_ticks >= heartbeat_ticks_max:
                yield ": keep-alive\n\n"
                heartbeat_ticks = 0
            await asyncio.sleep(poll_seconds)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def api_scheduler_outcome(request: Request) -> JSONResponse:
    started = time.perf_counter()
    action, case_id, role = "record_outcome", DEMO_CASE_ID, "UNKNOWN"
    try:
        principal = _principal(request)
        role = principal.role.value
        body = await _post_body(request)
        case_id = str(body.get("case_id", DEMO_CASE_ID))
        action = str(body.get("telemetry_action", "record_outcome"))
        authorize(principal, case_id, "record_outcome")
        result = APP.record_outcome(
            case_id=case_id,
            actor_id=principal.actor_id,
            event_type=str(body["event_type"]),
            idempotency_key=str(body["idempotency_key"]),
        )
        _record(
            action=action,
            role=role,
            success=True,
            started=started,
            case_id=case_id,
            metadata={"result": "ok"},
        )
        return _json_resp(HTTPStatus.OK, {"ok": True, "result": result})
    except AuthorizationError as exc:
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "authorization"},
        )
        return _json_resp(HTTPStatus.FORBIDDEN, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        _record(
            action=action,
            role=role,
            success=False,
            started=started,
            case_id=case_id,
            metadata={"failure_code": "workflow"},
        )
        return _json_resp(
            HTTPStatus.BAD_REQUEST,
            {"error": str(exc), "synthetic": True},
        )


def _build_app() -> FastAPI:
    """Build the unified FastAPI app with existing demo routes + MCP endpoint.

    Phase 1 deliberately preserves the existing request handlers and response
    payloads. The MCP sub-application remains mounted only when remote transport
    is configured and its existing security gate passes.
    """
    from veteran_access_bridge.mcp.app import mcp
    from veteran_access_bridge.mcp.config import settings

    mcp_lifespan = None
    transport = settings.vab_mcp_transport
    protected_mcp_app = None
    if transport != "stdio":
        from veteran_access_bridge.mcp.app import validate_transport

        validate_transport(transport, settings.vab_mcp_api_key)
        mcp_sub_app = mcp.http_app(path="/", transport="streamable-http")
        mcp_lifespan = mcp_sub_app.lifespan
        protected_mcp_app = MCPBearerAuthMiddleware(
            mcp_sub_app,
            settings.vab_mcp_api_key,
        )

    api = FastAPI(
        title="Veteran Access Bridge",
        version="0.4.1",
        description=(
            "Synthetic governed scheduling prototype. "
            "Production scheduling writes are disabled."
        ),
        lifespan=mcp_lifespan,
    )

    route_specs = [
        ("/", index, ["GET"]),
        ("/legacy", legacy_index, ["GET"]),
        ("/app.js", app_js, ["GET"]),
        ("/styles.css", styles_css, ["GET"]),
        ("/health", health, ["GET"]),
        ("/readiness", readiness, ["GET"]),
        ("/api/cases/{case_id}", api_case_snapshot, ["GET"]),
        ("/api/metrics", api_metrics, ["GET"]),
        ("/api/observability", api_observability, ["GET"]),
        ("/api/integrations", api_integrations, ["GET"]),
        ("/api/orchestrate/embed-token", api_orchestrate_embed_token, ["GET"]),
        (
            "/api/orchestrate/guest-embed-token",
            api_orchestrate_guest_embed_token,
            ["POST"],
        ),
        ("/api/scheduling-encounters/{case_id}", api_scheduling_encounter, ["GET"]),
        ("/api/voice/status", api_voice_status, ["GET"]),
        (
            "/api/voice-sessions/{voice_session_id}/ibm-phone-context",
            api_ibm_phone_context,
            ["POST"],
        ),
        (
            "/api/integrations/ibm-phone/cdr",
            api_ibm_phone_cdr_webhook,
            ["POST"],
        ),
        ("/api/voice-sessions", api_voice_session_create, ["POST"]),
        (
            "/api/voice-sessions/{voice_session_id}/renew",
            api_voice_session_renew,
            ["POST"],
        ),
        (
            "/api/voice-sessions/{voice_session_id}",
            api_voice_session_get,
            ["GET"],
        ),
        (
            "/api/voice-sessions/{voice_session_id}/events",
            api_voice_session_event,
            ["POST"],
        ),
        (
            "/api/voice-sessions/{voice_session_id}/webrtc-token",
            api_webrtc_token,
            ["POST"],
        ),
        ("/api/voice/synthesize", api_voice_synthesize, ["POST"]),
        ("/api/interactions", api_interactions_create, ["POST"]),
        ("/api/interactions/{interaction_id}", api_interaction_get, ["GET"]),
        (
            "/api/interactions/{interaction_id}/veteran-messages",
            api_veteran_secure_demo_message,
            ["POST"],
        ),
        (
            "/api/interactions/{interaction_id}/messages",
            api_interaction_message,
            ["POST"],
        ),
        (
            "/api/interactions/{interaction_id}/embedded-events",
            api_embedded_interaction_event,
            ["POST"],
        ),
        (
            "/api/interactions/{interaction_id}/actions",
            api_interaction_action,
            ["POST"],
        ),
        (
            "/api/primary-care/{interaction_id}/actions",
            api_primary_care_demo_action,
            ["POST"],
        ),
        (
            "/api/voice-sessions/{voice_session_id}/msa-monitor-token",
            api_msa_monitor_token,
            ["POST"],
        ),
        (
            "/api/interactions/{interaction_id}/msa-monitor-events",
            api_msa_monitor_events,
            ["GET"],
        ),
        (
            "/api/voice-sessions/{voice_session_id}/caller-activity-events",
            api_caller_activity_events,
            ["GET"],
        ),
        ("/api/interactions/{interaction_id}/events", api_interaction_events, ["GET"]),
        ("/api/scheduler/select", api_scheduler_select, ["POST"]),
        ("/api/scheduler/verify", api_scheduler_verify, ["POST"]),
        (
            "/api/scheduler/request-confirmation",
            api_scheduler_request_confirmation,
            ["POST"],
        ),
        ("/api/veteran/respond", api_veteran_respond, ["POST"]),
        ("/api/scheduler/commit", api_scheduler_commit, ["POST"]),
        ("/api/scheduler/outcome", api_scheduler_outcome, ["POST"]),
    ]
    for path, endpoint, methods in route_specs:
        api.add_api_route(
            path,
            endpoint,
            methods=methods,
            response_model=None,
            include_in_schema=(
                path.startswith("/api/") or path in {"/health", "/readiness"}
            ),
        )

    if os.getenv("VAB_ENABLE_TRUSTED_VOICE_BOOKING") == "true":
        from veteran_access_bridge.app.trusted_voice_booking import (
            build_trusted_voice_booking,
            create_trusted_voice_router,
        )

        api.state.trusted_voice_booking = build_trusted_voice_booking(
            conversations=LIVE_INTERACTIONS,
        )
        api.include_router(create_trusted_voice_router(api.state.trusted_voice_booking))
    if os.getenv("VAB_ENABLE_PRIVATE_PC_BOOKING_ENDPOINT") == "true":
        from veteran_access_bridge.app.private_primary_care_booking import (
            build_private_booking_from_environment,
            create_private_booking_router,
        )

        api.include_router(
            create_private_booking_router(build_private_booking_from_environment())
        )

    # The synthetic Veteran browser login and consent API are retired from
    # the autonomous voice-call-center MVP. Keep their implementation modules
    # for historical tests/rollback, but do not publish the routes. The
    # independently authenticated private VA booking endpoint above is
    # unaffected; caller identity and consent must be verified in the
    # trusted voice-host workflow, not by an interactive web login.
    if any(
        os.getenv(flag) == "true"
        for flag in (
            "VAB_ENABLE_SYNTHETIC_VETERAN_SESSIONS",
            "VAB_ENABLE_SYNTHETIC_VETERAN_CONSENT",
            "VAB_ENABLE_SYNTHETIC_SESSION_HOST_ISSUER",
        )
    ):
        import logging

        logging.getLogger(__name__).warning(
            "Deprecated synthetic browser session flags ignored in "
            "voice-call-center MVP"
        )

    if protected_mcp_app is not None:
        api.mount("/mcp", protected_mcp_app)

    return api


app: FastAPI = _build_app()


def main() -> None:
    host = os.getenv("VAB_DEMO_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("VAB_DEMO_PORT", "8080")))
    from veteran_access_bridge.voice.timing import timing_log_config

    APP.ensure_demo_ready()
    transport = os.getenv("VAB_MCP_TRANSPORT", "stdio")
    print(
        f"Veteran Access Bridge: http://{host}:{port} "
        f"(synthetic; production writes disabled; mcp-transport={transport})"
    )
    uvicorn.run(
        "veteran_access_bridge.app.asgi:app",
        host=host,
        port=port,
        log_level="warning",
        log_config=timing_log_config(),
    )


if __name__ == "__main__":
    main()
