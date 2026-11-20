"""Repeatable synthetic deployed-runtime smoke test for Issue #83."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

CASE_ID = "DEMO-PC-5000999-001"
ENCOUNTER_ID = "SE-DEMO-PC-5000999-001-REQ-PC-5000999-001"


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any): ...
    def post(self, url: str, **kwargs: Any): ...


@dataclass
class SmokeReport:
    passed: bool = True
    checks: list[dict[str, Any]] = field(default_factory=list)
    interaction_id: str | None = None
    correlation_id: str | None = None
    orchestrate_run_id: str | None = None
    runtime_mode: str | None = None

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": bool(condition), "detail": detail})
        if not condition:
            self.passed = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "synthetic": True,
            "production_write_attempted": False,
            "interaction_id": self.interaction_id,
            "correlation_id": self.correlation_id,
            "orchestrate_run_id": self.orchestrate_run_id,
            "runtime_mode": self.runtime_mode,
            "checks": list(self.checks),
        }


def _headers() -> dict[str, str]:
    return {
        "X-Demo-Role": "SCHEDULER",
        "X-Demo-Actor": "ibm-runtime-smoke",
        "X-Demo-Case": CASE_ID,
    }


def _contains_forbidden_credential_material(value: Any) -> bool:
    forbidden_keys = {
        "orchestrate_bearer_token",
        "vab_mcp_api_key",
        "authorization",
        "api_key",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in forbidden_keys:
                return True
            if _contains_forbidden_credential_material(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_credential_material(item) for item in value)

    text = str(value).lower()
    forbidden_text = (
        "authorization: bearer",
        '"orchestrate_bearer_token":',
        '"vab_mcp_api_key":',
    )
    return any(item in text for item in forbidden_text)


def run_runtime_smoke(
    client: HttpClient,
    *,
    require_remote: bool = True,
) -> SmokeReport:
    """Exercise the deployed synthetic IBM path without booking anything."""

    report = SmokeReport()

    readiness = client.get("/readiness")
    report.check(
        "readiness_http",
        readiness.status_code == 200,
        f"HTTP {readiness.status_code}",
    )
    if readiness.status_code != 200:
        return report

    ready_payload = readiness.json()
    report.runtime_mode = ready_payload.get("orchestrate_runtime_mode")
    report.check("readiness_ready", ready_payload.get("ready") is True)
    if require_remote:
        report.check(
            "remote_runtime_enabled",
            report.runtime_mode == "remote",
            f"mode={report.runtime_mode}",
        )
        report.check(
            "orchestrate_base_configured",
            ready_payload.get("orchestrate_base_url_configured") is True,
        )
        auth_configured = (
            ready_payload.get("orchestrate_api_key_configured") is True
            or ready_payload.get("orchestrate_bearer_token_configured") is True
        )
        report.check(
            "orchestrate_auth_configured",
            auth_configured,
            f"mode={ready_payload.get('orchestrate_auth_mode')}",
        )
    report.check(
        "readiness_contains_no_credentials",
        not _contains_forbidden_credential_material(ready_payload),
    )

    created = client.post(
        "/api/interactions",
        headers=_headers(),
        json={
            "case_id": CASE_ID,
            "scheduling_encounter_id": ENCOUNTER_ID,
            "channel": "PHONE",
            "initial_message": "I need a primary care appointment",
        },
    )
    report.check(
        "interaction_create_http",
        created.status_code == 201,
        f"HTTP {created.status_code}",
    )
    if created.status_code != 201:
        try:
            failure = created.json()
            report.check(
                "interaction_failure_is_explicit",
                bool(failure.get("runtime_failure_code"))
                and failure.get("recoverable") is True,
                str(failure.get("runtime_failure_code")),
            )
        except Exception:
            report.check("interaction_failure_is_explicit", False)
        return report

    created_payload = created.json()
    report.interaction_id = created_payload.get("interaction_id")
    report.correlation_id = created_payload.get("correlation_id")
    report.orchestrate_run_id = created_payload.get("orchestrate_run_id")
    report.check("interaction_id_present", bool(report.interaction_id))
    report.check("correlation_id_present", bool(report.correlation_id))

    expected_agent_id = ready_payload.get("orchestrate_agent_id")
    actual_agent_id = created_payload.get("agent_id")
    report.check(
        "agent_response_started",
        bool(expected_agent_id) and actual_agent_id == expected_agent_id,
        f"expected={expected_agent_id}, actual={actual_agent_id}",
    )

    if require_remote:
        report.check("orchestrate_run_id_present", bool(report.orchestrate_run_id))
    report.check(
        "interaction_response_contains_no_credentials",
        not _contains_forbidden_credential_material(created_payload),
    )

    message = client.post(
        f"/api/interactions/{report.interaction_id}/messages",
        headers=_headers(),
        json={"message": "Mornings are best"},
    )
    report.check(
        "preference_message_http",
        message.status_code == 200,
        f"HTTP {message.status_code}",
    )
    if message.status_code != 200:
        failure = message.json()
        report.check(
            "message_failure_is_explicit",
            bool(failure.get("payload", {}).get("failure_code"))
            and failure.get("recoverable") is True,
            str(failure.get("payload", {}).get("failure_code")),
        )
        return report

    message_payload = message.json()
    report.check(
        "agent_message_event",
        message_payload.get("event_type") == "agent_answered",
        str(message_payload.get("event_type")),
    )
    report.check(
        "message_response_contains_no_credentials",
        not _contains_forbidden_credential_material(message_payload),
    )

    encounter = client.get(
        f"/api/scheduling-encounters/{CASE_ID}",
        headers=_headers(),
    )
    report.check(
        "governed_encounter_http",
        encounter.status_code == 200,
        f"HTTP {encounter.status_code}",
    )
    if encounter.status_code == 200:
        encounter_payload = encounter.json()
        governed = encounter_payload.get("encounter", {})
        report.check(
            "classification_is_governed",
            governed.get("patient_classification") == "ESTABLISHED",
            str(governed.get("patient_classification")),
        )
        report.check(
            "primary_care_context",
            governed.get("request", {}).get("care_category") == "PRIMARY_CARE",
        )
        report.check(
            "deterministic_calendar_present",
            len(encounter_payload.get("calendar", [])) == 3,
            f"slots={len(encounter_payload.get('calendar', []))}",
        )

    events = client.get(
        f"/api/interactions/{report.interaction_id}/events?once=1",
        headers=_headers(),
    )
    report.check(
        "sse_replay_http",
        events.status_code == 200,
        f"HTTP {events.status_code}",
    )
    stream_text = events.text if events.status_code == 200 else ""
    report.check(
        "sse_interaction_received",
        "event: interaction_received" in stream_text,
    )
    report.check(
        "sse_intent_captured",
        "event: intent_captured" in stream_text,
    )
    report.check(
        "sse_preference_captured",
        "event: preference_captured" in stream_text,
    )
    report.check(
        "sse_agent_answered",
        "event: agent_answered" in stream_text,
    )
    report.check(
        "sse_correlation_preserved",
        bool(report.correlation_id) and report.correlation_id in stream_text,
    )
    report.check(
        "sse_contains_no_credentials",
        not _contains_forbidden_credential_material(stream_text),
    )

    return report
