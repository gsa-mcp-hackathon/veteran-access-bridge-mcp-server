"""PHI-minimized systems-thinking telemetry for the demo runtime."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any

_ALLOWED_METADATA = frozenset(
    {
        "source_system",
        "lifecycle_state",
        "failure_code",
        "appointment_intent",
        "result",
        "normalized_event_type",
        "tool_outcome",
        "retry_count",
        "terminal_status",
        "runtime_mode",
        "app_env",
        "revision",
        "recoverable",
    }
)


@dataclass(frozen=True)
class TelemetryEvent:
    occurred_at: datetime
    action: str
    actor_role: str
    success: bool
    duration_ms: int
    case_ref: str
    metadata: dict[str, Any]
    interaction_id: str | None = None
    correlation_id: str | None = None
    orchestrate_run_id: str | None = None


class TelemetryStore:
    """In-memory, synthetic-only operational telemetry.

    Raw patient demographics, names, dates of birth, referral text, and other
    PHI-like content are never accepted into metadata. case_ref is the
    synthetic case ID used by the demo.
    """

    def __init__(self) -> None:
        self._events: list[TelemetryEvent] = []
        self._lock = RLock()

    def record(
        self,
        *,
        action: str,
        actor_role: str,
        success: bool,
        duration_ms: int,
        case_ref: str,
        metadata: dict[str, Any] | None = None,
        interaction_id: str | None = None,
        correlation_id: str | None = None,
        orchestrate_run_id: str | None = None,
    ) -> None:
        clean = {
            key: value
            for key, value in (metadata or {}).items()
            if key in _ALLOWED_METADATA
        }
        event = TelemetryEvent(
            occurred_at=datetime.now(timezone.utc),
            action=action,
            actor_role=actor_role,
            success=success,
            duration_ms=max(0, int(duration_ms)),
            case_ref=case_ref,
            metadata=clean,
            interaction_id=interaction_id,
            correlation_id=correlation_id,
            orchestrate_run_id=orchestrate_run_id,
        )
        with self._lock:
            self._events.append(event)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            events = tuple(self._events)
        actions = Counter(e.action for e in events)
        failures = Counter(
            str(e.metadata.get("failure_code", "unspecified"))
            for e in events
            if not e.success
        )
        latencies = [e.duration_ms for e in events]
        return {
            "synthetic": True,
            "event_count": len(events),
            "success_count": sum(1 for e in events if e.success),
            "failure_count": sum(1 for e in events if not e.success),
            "actions": dict(sorted(actions.items())),
            "failure_codes": dict(sorted(failures.items())),
            "average_duration_ms": (
                round(sum(latencies) / len(latencies), 2) if latencies else 0.0
            ),
            "measures": {
                "booking_rework": actions.get("request_change", 0)
                + actions.get("reschedule", 0),
                "stale_or_unavailable_blocks": failures.get("slot_unavailable", 0),
                "authorization_blocks": failures.get("authorization", 0),
                "confirmation_declines": actions.get("veteran_decline", 0),
                "no_show_count": actions.get("no_show", 0),
            },
            "phi_policy": "allowlisted operational metadata only",
        }

    def operational_snapshot(self, *, limit: int = 50) -> dict[str, Any]:
        """Return sanitized recent operational events for scheduler observability."""

        with self._lock:
            events = tuple(self._events[-max(1, limit) :])

        return {
            "synthetic": True,
            "phi_policy": "allowlisted operational metadata only",
            "events": [
                {
                    "occurred_at": event.occurred_at.isoformat(),
                    "action": event.action,
                    "actor_role": event.actor_role,
                    "success": event.success,
                    "duration_ms": event.duration_ms,
                    "case_ref": event.case_ref,
                    "interaction_id": event.interaction_id,
                    "correlation_id": event.correlation_id,
                    "orchestrate_run_id": event.orchestrate_run_id,
                    "metadata": dict(event.metadata),
                }
                for event in events
            ],
        }

    def events(self) -> tuple[TelemetryEvent, ...]:
        with self._lock:
            return tuple(self._events)
