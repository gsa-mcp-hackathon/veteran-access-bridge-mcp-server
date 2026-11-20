"""Zero-dependency local HTTP server for the M3-M6 demo."""

from __future__ import annotations

import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import urlparse

from veteran_access_bridge.app.auth import (
    AuthorizationError,
    DemoRole,
    authorize,
    principal_from_headers,
)
from veteran_access_bridge.app.facade import DEMO_CASE_ID, DemoApplication
from veteran_access_bridge.app.telemetry import TelemetryStore
from veteran_access_bridge.integrations.contracts import integration_readiness_report

APP = DemoApplication()
TELEMETRY = TelemetryStore()


def _static_text(name: str) -> str:
    return (
        files("veteran_access_bridge.app.static")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "VeteranAccessBridgeDemo/0.2"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, name: str, content_type: str) -> None:
        body = _static_text(name).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _principal(self):
        return principal_from_headers(
            self.headers.get("X-Demo-Role"),
            self.headers.get("X-Demo-Actor"),
            self.headers.get("X-Demo-Case"),
        )

    def _json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON request body must be an object.")
        return payload

    def _record(
        self,
        *,
        action: str,
        role: str,
        success: bool,
        started: float,
        case_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        TELEMETRY.record(
            action=action,
            actor_role=role,
            success=success,
            duration_ms=int((time.perf_counter() - started) * 1000),
            case_ref=case_id,
            metadata=metadata,
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._send_static("index.html", "text/html; charset=utf-8")
        if parsed.path == "/app.js":
            return self._send_static("app.js", "text/javascript; charset=utf-8")
        if parsed.path == "/styles.css":
            return self._send_static("styles.css", "text/css; charset=utf-8")
        if parsed.path == "/health":
            return self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "synthetic": True,
                    "production_writes_enabled": False,
                    "milestones": ["M3", "M4", "M5", "M6"],
                },
            )

        started = time.perf_counter()
        try:
            principal = self._principal()
            if parsed.path.startswith("/api/cases/"):
                case_id = parsed.path.rsplit("/", 1)[-1]
                authorize(principal, case_id, "view_case")
                include_audit = principal.role == DemoRole.SCHEDULER
                payload = APP.snapshot(case_id, include_audit=include_audit)
                self._record(
                    action="view_case",
                    role=principal.role.value,
                    success=True,
                    started=started,
                    case_id=case_id,
                    metadata={
                        "lifecycle_state": (payload.get("lifecycle") or {}).get(
                            "current_state"
                        )
                    },
                )
                return self._send_json(HTTPStatus.OK, payload)
            if parsed.path == "/api/metrics":
                authorize(principal, DEMO_CASE_ID, "view_metrics")
                return self._send_json(HTTPStatus.OK, TELEMETRY.summary())
            if parsed.path == "/api/integrations":
                authorize(principal, DEMO_CASE_ID, "view_integrations")
                return self._send_json(HTTPStatus.OK, integration_readiness_report())
            return self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        except AuthorizationError as exc:
            return self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            return self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": str(exc), "synthetic": True},
            )

    def do_POST(self) -> None:  # noqa: N802
        started = time.perf_counter()
        case_id = DEMO_CASE_ID
        action = "unknown"
        role = "UNKNOWN"
        try:
            principal = self._principal()
            role = principal.role.value
            body = self._json_body()
            case_id = str(body.get("case_id", DEMO_CASE_ID))

            if self.path == "/api/scheduler/select":
                action = "select_option"
                authorize(principal, case_id, action)
                result = APP.select_option(
                    case_id=case_id,
                    option_id=str(body["option_id"]),
                    actor_id=principal.actor_id,
                    idempotency_key=str(body["idempotency_key"]),
                )
            elif self.path == "/api/scheduler/verify":
                action = "verify_option"
                authorize(principal, case_id, action)
                result = APP.verify_selected_option(
                    case_id=case_id,
                    actor_id=principal.actor_id,
                    evidence_ref=str(body["evidence_ref"]),
                    outcome=str(body.get("outcome", "VERIFIED")),
                    idempotency_key=str(body["idempotency_key"]),
                )
            elif self.path == "/api/scheduler/request-confirmation":
                action = "request_confirmation"
                authorize(principal, case_id, action)
                result = APP.request_veteran_confirmation(case_id=case_id)
            elif self.path == "/api/veteran/respond":
                action = "respond_confirmation"
                authorize(principal, case_id, action)
                response = str(body["response"])
                result = APP.record_veteran_response(
                    case_id=case_id,
                    actor_id=principal.actor_id,
                    response=response,
                    idempotency_key=str(body["idempotency_key"]),
                )
                if response == "DECLINED":
                    action = "veteran_decline"
                elif response == "REQUESTED_CHANGE":
                    action = "request_change"
            elif self.path == "/api/scheduler/commit":
                action = "commit_booking"
                authorize(principal, case_id, action)
                result = APP.commit_selected_booking(
                    case_id=case_id,
                    actor_id=principal.actor_id,
                    idempotency_key=str(body["idempotency_key"]),
                    appointment_intent=str(
                        body.get("appointment_intent", "INITIAL_CONSULT")
                    ),
                )
            elif self.path == "/api/scheduler/outcome":
                action = str(body.get("telemetry_action", "record_outcome"))
                authorize(principal, case_id, "record_outcome")
                result = APP.record_outcome(
                    case_id=case_id,
                    actor_id=principal.actor_id,
                    event_type=str(body["event_type"]),
                    idempotency_key=str(body["idempotency_key"]),
                )
            else:
                return self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            self._record(
                action=action,
                role=role,
                success=True,
                started=started,
                case_id=case_id,
                metadata={"result": "ok"},
            )
            return self._send_json(HTTPStatus.OK, {"ok": True, "result": result})
        except AuthorizationError as exc:
            self._record(
                action=action,
                role=role,
                success=False,
                started=started,
                case_id=case_id,
                metadata={"failure_code": "authorization"},
            )
            return self._send_json(HTTPStatus.FORBIDDEN, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            failure_code = "workflow"
            if "slot" in message.lower():
                failure_code = "slot_unavailable"
            elif "authorization" in message.lower() or "hsrm" in message.lower():
                failure_code = "authorization"
            self._record(
                action=action,
                role=role,
                success=False,
                started=started,
                case_id=case_id,
                metadata={"failure_code": failure_code},
            )
            return self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": message, "synthetic": True},
            )

    def log_message(self, format: str, *args: object) -> None:
        if os.getenv("VAB_DEMO_ACCESS_LOG", "0") == "1":
            super().log_message(format, *args)


def main() -> None:
    host = os.getenv("VAB_DEMO_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", os.getenv("VAB_DEMO_PORT", "8080")))
    APP.ensure_demo_ready()
    print(
        f"Veteran Access Bridge demo: http://{host}:{port} "
        "(synthetic data; production writes disabled)"
    )
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
