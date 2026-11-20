"""Lifecycle outcomes service — M2-8.

record_lifecycle_event() drives the six post-booking outcome transitions:

    BOOKED_SIMULATED → APPOINTMENT_COMPLETED → COMPLETED
    BOOKED_SIMULATED → VETERAN_NO_SHOW       → NO_SHOW
    BOOKED_SIMULATED → APPOINTMENT_CANCELLED → CANCELLED
    BOOKED_SIMULATED → RESCHEDULE_REQUESTED  → RESCHEDULED
    NO_SHOW          → FOLLOW_UP_INITIATED   → HUMAN_REVIEW
    RESCHEDULED      → NEW_SEARCH_INITIATED  → READY_TO_SEARCH

Design rules
------------
1. Only the six M2-8 event types above are accepted.
   Any other event_type raises ValueError before touching the event store.

2. from_state is derived from the current lifecycle record.
   The caller does not supply it. Missing history fails closed.

3. The expected from_state is validated against _OUTCOME_TRANSITIONS
   before the event store is called. This is a hard guard, independent
   of the transition table, so the error message names the required state.

4. Role enforcement is in the MCP tool layer, not here.
   This service function does not validate actor_role values; it passes
   them through to CaseEvent and lets the event store type-guard (ActorRole).

5. Idempotency: same idempotency_key → event store returns existing event.
   No duplicate logic here.

6. Terminal-state protection is owned by the event store (TerminalStateError).

Governance boundaries
---------------------
- Never transitions cases outside the six M2-8 outcome pairs.
- Never grants authorization, creates bookings, or modifies earlier lifecycle records.
- Synthetic / local-first — no PHI, no network I/O.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from veteran_access_bridge.domain.models import (
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
)
from veteran_access_bridge.services.events import CaseEventStore

# ── Outcome transition table ────────────────────────────────────────────────
# Maps event_type → (expected_from_state, to_state).
# Only these six pairs are M2-8 responsibilities.

_OUTCOME_TRANSITIONS: dict[
    CaseEventType, tuple[CaseLifecycleState, CaseLifecycleState]
] = {
    CaseEventType.APPOINTMENT_COMPLETED: (
        CaseLifecycleState.BOOKED_SIMULATED,
        CaseLifecycleState.COMPLETED,
    ),
    CaseEventType.VETERAN_NO_SHOW: (
        CaseLifecycleState.BOOKED_SIMULATED,
        CaseLifecycleState.NO_SHOW,
    ),
    CaseEventType.APPOINTMENT_CANCELLED: (
        CaseLifecycleState.BOOKED_SIMULATED,
        CaseLifecycleState.CANCELLED,
    ),
    CaseEventType.RESCHEDULE_REQUESTED: (
        CaseLifecycleState.BOOKED_SIMULATED,
        CaseLifecycleState.RESCHEDULED,
    ),
    CaseEventType.FOLLOW_UP_INITIATED: (
        CaseLifecycleState.NO_SHOW,
        CaseLifecycleState.HUMAN_REVIEW,
    ),
    CaseEventType.NEW_SEARCH_INITIATED: (
        CaseLifecycleState.RESCHEDULED,
        CaseLifecycleState.READY_TO_SEARCH,
    ),
}

_OUTCOME_EVENT_TYPES: frozenset[CaseEventType] = frozenset(_OUTCOME_TRANSITIONS)


def _outcome_event_id(idempotency_key: str) -> str:
    return "oe-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]


def record_lifecycle_event(
    *,
    case_id: str,
    event_type: CaseEventType,
    actor_role: ActorRole,
    actor_id: str,
    idempotency_key: str,
    payload: dict | None = None,
    event_store: CaseEventStore,
) -> CaseEvent:
    """Record a post-booking lifecycle outcome event.

    Parameters
    ----------
    case_id:
        Identifier of the case to advance.
    event_type:
        One of the six M2-8 outcome event types. Any other type raises ValueError.
    actor_role:
        ActorRole of the person performing the action. Enforced by the MCP tool;
        passed through to CaseEvent for audit purposes.
    actor_id:
        Opaque identity string for the actor (synthetic/demo only).
    idempotency_key:
        Caller-supplied deduplication key. Same key → existing event returned.
    payload:
        Optional metadata dict (e.g. cancellation reason). Stored on the event.
    event_store:
        The CaseEventStore to append to.

    Returns
    -------
    CaseEvent
        The stored event (may be a previously stored event on idempotent retry).

    Raises
    ------
    ValueError
        If event_type is not a supported M2-8 outcome type.
        If no lifecycle history exists for the case.
        If the case is not in the expected from_state for this event_type.
    TerminalStateError
        If the case is already in a terminal state (COMPLETED or CANCELLED).
    """
    # ── 1. Validate event_type ──────────────────────────────────────────────
    if event_type not in _OUTCOME_EVENT_TYPES:
        allowed = sorted(t.value for t in _OUTCOME_EVENT_TYPES)
        raise ValueError(
            f"event_type {event_type!r} is not a supported M2-8 outcome type. "
            f"Allowed: {allowed}."
        )

    # ── 2. Idempotency: check before lifecycle guard (M2-8 pattern) ────────
    # If this key was already processed, return the existing event immediately
    # without validating from_state. The state may have advanced after the
    # first successful call, so checking from_state first would break retries.
    existing = event_store.get_by_idempotency_key(idempotency_key)
    if existing is not None:
        return existing

    # ── 3. Derive from_state from current lifecycle record ─────────────────
    record = event_store.get_lifecycle_record(case_id)
    if record is None:
        raise ValueError(
            f"No lifecycle history for case {case_id!r}. "
            "A case must have at least one lifecycle event before outcomes can be recorded."
        )
    from_state = record.current_state

    # ── 4. Validate (from_state, event_type) against outcome table ─────────
    expected_from, to_state = _OUTCOME_TRANSITIONS[event_type]
    if from_state != expected_from:
        raise ValueError(
            f"Cannot record {event_type!r} for case {case_id!r}: "
            f"expected current state {expected_from!r}, "
            f"but case is in {from_state!r}."
        )

    # ── 4. Build and append the event ─────────────────────────────────────
    event = CaseEvent(
        event_id=_outcome_event_id(idempotency_key),
        case_id=case_id,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        actor_role=actor_role,
        actor_id=actor_id,
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=idempotency_key,
        payload=payload or {},
    )
    return event_store.append(event)
