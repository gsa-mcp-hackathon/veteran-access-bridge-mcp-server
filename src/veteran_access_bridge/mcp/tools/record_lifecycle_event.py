"""MCP tool: record_lifecycle_event.

Approval-gated — records a post-booking lifecycle outcome for a synthetic
scheduling case. Drives the following transitions:

    BOOKED_SIMULATED → APPOINTMENT_COMPLETED → COMPLETED
    BOOKED_SIMULATED → VETERAN_NO_SHOW       → NO_SHOW
    BOOKED_SIMULATED → APPOINTMENT_CANCELLED → CANCELLED   (SCHEDULER/VETERAN/SYSTEM)
    BOOKED_SIMULATED → RESCHEDULE_REQUESTED  → RESCHEDULED (SCHEDULER/VETERAN)
    NO_SHOW          → FOLLOW_UP_INITIATED   → HUMAN_REVIEW (SCHEDULER only)
    RESCHEDULED      → NEW_SEARCH_INITIATED  → READY_TO_SEARCH (SCHEDULER only)

Role enforcement per event type:
    APPOINTMENT_COMPLETED  — SCHEDULER or SYSTEM
    VETERAN_NO_SHOW        — SCHEDULER or SYSTEM
    APPOINTMENT_CANCELLED  — SCHEDULER, VETERAN, or SYSTEM
    RESCHEDULE_REQUESTED   — SCHEDULER or VETERAN
    FOLLOW_UP_INITIATED    — SCHEDULER only
    NEW_SEARCH_INITIATED   — SCHEDULER only

Idempotent: same idempotency_key + identical actor/event returns existing event.
Conflicting reuse of idempotency_key fails closed.

Shared process state imported from mcp/state.py.
Tests inject fresh instances via run() parameter interface.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastmcp import FastMCP

from veteran_access_bridge.domain.models import ActorRole, CaseEventType
from veteran_access_bridge.mcp.durable_runtime import require_private_durable_writer
from veteran_access_bridge.mcp.serialization import to_jsonable
from veteran_access_bridge.mcp.state import event_store as _event_store
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.outcomes import record_lifecycle_event

# ── Role rules per event type ───────────────────────────────────────────────

_ALLOWED_ROLES: dict[CaseEventType, frozenset[ActorRole]] = {
    CaseEventType.APPOINTMENT_COMPLETED: frozenset(
        {
            ActorRole.SCHEDULER,
            ActorRole.SYSTEM,
        }
    ),
    CaseEventType.VETERAN_NO_SHOW: frozenset(
        {
            ActorRole.SCHEDULER,
            ActorRole.SYSTEM,
        }
    ),
    CaseEventType.APPOINTMENT_CANCELLED: frozenset(
        {
            ActorRole.SCHEDULER,
            ActorRole.VETERAN,
            ActorRole.SYSTEM,
        }
    ),
    CaseEventType.RESCHEDULE_REQUESTED: frozenset(
        {
            ActorRole.SCHEDULER,
            ActorRole.VETERAN,
        }
    ),
    CaseEventType.FOLLOW_UP_INITIATED: frozenset(
        {
            ActorRole.SCHEDULER,
        }
    ),
    CaseEventType.NEW_SEARCH_INITIATED: frozenset(
        {
            ActorRole.SCHEDULER,
        }
    ),
}


def run(
    case_id: str,
    event_type: str,
    actor_role: str,
    actor_id: str,
    idempotency_key: str,
    payload: dict | None = None,
    *,
    event_store: CaseEventStore | None = None,
) -> dict[str, Any]:
    """Testable inner function; MCP tool wrapper calls this."""
    require_private_durable_writer()
    es = event_store if event_store is not None else _event_store

    # ── Coerce event_type ───────────────────────────────────────────────────
    try:
        et = CaseEventType(event_type)
    except ValueError:
        allowed = sorted(t.value for t in _ALLOWED_ROLES)
        raise ValueError(
            f"Invalid event_type {event_type!r}. "
            f"Allowed outcome event types: {allowed}."
        )

    # ── Validate event_type is a supported outcome type ────────────────────
    if et not in _ALLOWED_ROLES:
        allowed = sorted(t.value for t in _ALLOWED_ROLES)
        raise ValueError(
            f"event_type {event_type!r} is not a supported outcome event type. "
            f"Allowed: {allowed}."
        )

    # ── Coerce actor_role ───────────────────────────────────────────────────
    try:
        role = ActorRole(actor_role)
    except ValueError:
        allowed_roles = [r.value for r in ActorRole]
        raise ValueError(
            f"Invalid actor_role {actor_role!r}. Allowed values: {allowed_roles}."
        )

    # ── Role guard ──────────────────────────────────────────────────────────
    allowed_for_type = _ALLOWED_ROLES[et]
    if role not in allowed_for_type:
        raise ValueError(
            f"actor_role {role!r} is not permitted for event_type {et!r}. "
            f"Allowed roles: {sorted(r.value for r in allowed_for_type)}."
        )

    # ── Delegate to service layer ───────────────────────────────────────────
    event = record_lifecycle_event(
        case_id=case_id,
        event_type=et,
        actor_role=role,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        payload=payload,
        event_store=es,
    )

    result = to_jsonable(event)
    result["synthetic"] = True
    return result


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        name="record_lifecycle_event",
        annotations={
            "title": "Record Lifecycle Event",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    async def record_lifecycle_event_tool(
        case_id: Annotated[str, "Synthetic scheduling case ID."],
        event_type: Annotated[
            Literal[
                "APPOINTMENT_COMPLETED",
                "VETERAN_NO_SHOW",
                "APPOINTMENT_CANCELLED",
                "RESCHEDULE_REQUESTED",
                "FOLLOW_UP_INITIATED",
                "NEW_SEARCH_INITIATED",
            ],
            "Post-booking lifecycle outcome event type.",
        ],
        actor_role: Annotated[
            Literal["SCHEDULER", "VETERAN", "SYSTEM"],
            "Role of the actor recording this outcome. "
            "Not all roles are permitted for all event types.",
        ],
        actor_id: Annotated[str, "Opaque actor identifier (synthetic/demo only)."],
        idempotency_key: Annotated[
            str,
            "Caller-supplied deduplication key. Same key + same event = no-op. "
            "Same key + different event = error.",
        ],
        payload: Annotated[
            dict | None,
            "Optional metadata (e.g. cancellation_reason, reschedule_notes). "
            "Stored on the audit event.",
        ] = None,
    ) -> dict[str, Any]:
        """Record a post-booking lifecycle outcome for a synthetic scheduling case.

        Drives state transitions after a booking has been simulated:
        - APPOINTMENT_COMPLETED → marks appointment as completed (terminal)
        - VETERAN_NO_SHOW       → records no-show; staff follow-up available
        - APPOINTMENT_CANCELLED → cancels post-booking (terminal)
        - RESCHEDULE_REQUESTED  → marks for rescheduling
        - FOLLOW_UP_INITIATED   → moves no-show case to human review
        - NEW_SEARCH_INITIATED  → restarts search after rescheduling

        Not all actor roles are permitted for all event types.
        Idempotent: same idempotency_key with identical parameters returns
        the existing event without writing new state.
        Does not create, modify, or cancel real appointments.
        """
        return run(case_id, event_type, actor_role, actor_id, idempotency_key, payload)
