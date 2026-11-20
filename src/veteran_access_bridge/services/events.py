"""CaseEventStore — append-only lifecycle event store for M2.

Design principles
-----------------
1. Type-boundary enforcement
   append() accepts only CaseLifecycleState for from_state/to_state.
   WorkflowState is rejected at runtime even when its string value matches a
   CaseLifecycleState value. This is enforced with an explicit isinstance guard
   and raises TypeError so the caller gets a clear, unambiguous error rather
   than a silent misclassification.

2. Transition validation
   Every append is checked against ALLOWED_LIFECYCLE_TRANSITIONS before the
   event is stored. An invalid transition raises ValueError with the offending
   (from_state → to_state) pair.

3. Idempotency
   Two deduplication indexes are maintained:
   - idempotency_key: a caller-supplied string for request-level deduplication.
     A second append with the same key returns the *existing* event unchanged.
   - event_id: a unique event identifier. A second append carrying the same
     event_id raises ValueError (conflicting reuse) because different
     from/to/payload data under the same ID is ambiguous and must fail closed.

   The contract is:
   - same idempotency_key, same logical request → return existing event (no-op)
   - same event_id, different data → fail closed (ValueError)
   - same event_id, same data → treat as idempotent retry (return existing)

4. Immutable append-only history
   Events are stored in a tuple per case. History is never modified. Callers
   receive copies of the stored tuples, not the internal lists.

5. Lifecycle state reconstruction
   get_lifecycle_record() walks the event list for a case and returns a
   CaseLifecycleRecord whose current_state is the to_state of the last event.
   This is deterministic and repeatable.

6. Terminal-state protection
   Appending to a case whose current_state has no allowed outbound transitions
   (COMPLETED, CANCELLED) raises ValueError. The transition check naturally
   enforces this because the terminal state maps to frozenset() in
   ALLOWED_LIFECYCLE_TRANSITIONS, so any target raises "not allowed".

7. Synthetic / local-first
   No persistence, no network I/O, no PHI. All data is in-process memory.
   This is intentional for the M2 synthetic demo. File-backed persistence
   is deferred to M3.
"""

from __future__ import annotations

from typing import Optional

from veteran_access_bridge.domain.models import (
    ALLOWED_LIFECYCLE_TRANSITIONS,
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleRecord,
    CaseLifecycleState,
    WorkflowState,
)

# Sentinel used internally to detect that WorkflowState was passed instead of
# CaseLifecycleState. Raising TypeError with a clear message is preferable to
# allowing the StrEnum string equality to mask the mistake.
_WORKFLOW_STATE_TYPE_ERROR = (
    "CaseEventStore requires CaseLifecycleState for {param!r}, "
    "not WorkflowState. Both enums share string values but are distinct types. "
    "Got: {value!r} (type={type_name})"
)


def _assert_lifecycle_state(value: object, param: str) -> CaseLifecycleState:
    """Raise TypeError if value is not a CaseLifecycleState.

    Explicitly rejects WorkflowState even though its string value may match a
    CaseLifecycleState value. This is the primary cross-type bug guard.
    """
    if isinstance(value, WorkflowState):
        raise TypeError(
            _WORKFLOW_STATE_TYPE_ERROR.format(
                param=param,
                value=value,
                type_name=type(value).__name__,
            )
        )
    if not isinstance(value, CaseLifecycleState):
        raise TypeError(
            f"CaseEventStore requires CaseLifecycleState for {param!r}, "
            f"got {type(value).__name__!r}: {value!r}"
        )
    return value  # type: ignore[return-value]


def _assert_actor_role(value: object) -> ActorRole:
    """Raise TypeError if value is not an ActorRole."""
    if not isinstance(value, ActorRole):
        raise TypeError(
            f"CaseEventStore requires ActorRole for actor_role, "
            f"got {type(value).__name__!r}: {value!r}"
        )
    return value  # type: ignore[return-value]


class IdempotencyConflictError(ValueError):
    """Raised when an event_id is reused with different data.

    This is a fail-closed error. The caller must not retry with the same
    event_id if the payload differs; generate a new event_id instead.
    """


class InvalidTransitionError(ValueError):
    """Raised when a state transition is not in ALLOWED_LIFECYCLE_TRANSITIONS."""


class TerminalStateError(ValueError):
    """Raised when an append is attempted on a case in a terminal state."""


class CaseEventStore:
    """Append-only in-memory lifecycle event store.

    Thread safety: not thread-safe. This is intentional for the single-process
    synthetic M2 demo. Thread safety and persistence are deferred to M3.

    Usage:
        store = CaseEventStore()
        event = CaseEvent(...)
        stored = store.append(event)          # returns stored event (may be existing)
        record = store.get_lifecycle_record("DEMO-CARD-001")
        history = store.get_events("DEMO-CARD-001")
    """

    def __init__(self) -> None:
        # case_id → ordered list of CaseEvent (append-only)
        self._history: dict[str, list[CaseEvent]] = {}
        # idempotency_key → CaseEvent (first-write wins)
        self._idempotency_index: dict[str, CaseEvent] = {}
        # event_id → CaseEvent (for conflicting-reuse detection)
        self._event_id_index: dict[str, CaseEvent] = {}

    # ------------------------------------------------------------------
    # Core append operation
    # ------------------------------------------------------------------

    def append(self, event: CaseEvent) -> CaseEvent:
        """Append a lifecycle event and return the stored event.

        Returns the *existing* event if the idempotency_key was already seen
        (idempotent retry). Raises on invalid transitions, terminal state
        violations, and conflicting event_id reuse.

        Parameters
        ----------
        event:
            A fully constructed CaseEvent. from_state and to_state must be
            CaseLifecycleState instances, not WorkflowState.

        Returns
        -------
        CaseEvent
            The stored event (may be a previously stored event if idempotent).

        Raises
        ------
        TypeError
            If from_state or to_state is WorkflowState or any other non-
            CaseLifecycleState type, or if actor_role is not ActorRole.
        InvalidTransitionError
            If the (from_state → to_state) pair is not in the transition table.
        TerminalStateError
            If the case is already in a terminal state (COMPLETED or CANCELLED)
            and the transition is not permitted.
        IdempotencyConflictError
            If event_id is reused with different (from_state, to_state, payload).
        """
        # ── 1. Type-boundary guards ────────────────────────────────────────
        from_state = _assert_lifecycle_state(event.from_state, "from_state")
        to_state = _assert_lifecycle_state(event.to_state, "to_state")
        _assert_actor_role(event.actor_role)

        # ── 2. Idempotency: check idempotency_key first ────────────────────
        if event.idempotency_key in self._idempotency_index:
            return self._idempotency_index[event.idempotency_key]

        # ── 3. Idempotency: check event_id for conflicting reuse ──────────
        if event.event_id in self._event_id_index:
            existing = self._event_id_index[event.event_id]
            # Same event_id, same data → treat as idempotent (different key path)
            if (
                existing.from_state == from_state
                and existing.to_state == to_state
                and existing.payload == event.payload
            ):
                return existing
            # Same event_id, different data → fail closed
            raise IdempotencyConflictError(
                f"event_id {event.event_id!r} already exists with different "
                f"(from_state, to_state, payload). "
                f"Existing: {existing.from_state!r} → {existing.to_state!r}. "
                f"New: {from_state!r} → {to_state!r}."
            )

        # ── 4. Transition validation ───────────────────────────────────────
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(from_state, frozenset())

        # Terminal-state check produces a more specific error
        if not allowed and from_state in (
            CaseLifecycleState.COMPLETED,
            CaseLifecycleState.CANCELLED,
        ):
            raise TerminalStateError(
                f"Case {event.case_id!r} is in terminal state {from_state!r}. "
                "No further lifecycle transitions are permitted."
            )

        if to_state not in allowed:
            raise InvalidTransitionError(
                f"Transition {from_state!r} → {to_state!r} is not allowed. "
                f"Permitted targets from {from_state!r}: "
                f"{sorted(s.value for s in allowed) or '(none — terminal state)'}."
            )

        # ── 5. Current-state consistency check ────────────────────────────
        # If events already exist for this case, the from_state of the new
        # event must match the current persisted state.
        existing_events = self._history.get(event.case_id, [])
        if existing_events:
            current = existing_events[-1].to_state
            if from_state != current:
                raise InvalidTransitionError(
                    f"Case {event.case_id!r} current state is {current!r} "
                    f"but event declares from_state={from_state!r}. "
                    "Events must be appended in order."
                )

        # ── 6. Store ───────────────────────────────────────────────────────
        if event.case_id not in self._history:
            self._history[event.case_id] = []
        self._history[event.case_id].append(event)
        self._idempotency_index[event.idempotency_key] = event
        self._event_id_index[event.event_id] = event

        return event

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_events(self, case_id: str) -> tuple[CaseEvent, ...]:
        """Return an immutable copy of the event history for a case.

        Returns an empty tuple if the case has no events.
        """
        return tuple(self._history.get(case_id, []))

    def get_lifecycle_record(self, case_id: str) -> Optional[CaseLifecycleRecord]:
        """Return the current lifecycle record for a case, or None if unknown.

        The current_state is reconstructed deterministically from event history
        by reading the to_state of the last appended event.
        """
        events = self._history.get(case_id)
        if not events:
            return None
        last = events[-1]
        return CaseLifecycleRecord(
            case_id=case_id,
            current_state=last.to_state,
            last_event_type=last.event_type,
            last_event_at=last.occurred_at,
            event_count=len(events),
        )

    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[CaseEvent]:
        """Return the stored event for this idempotency key, or None.

        Used by service callers to check whether a request was already
        processed before performing pre-append validation (idempotency-before-
        lifecycle-guard pattern, same as M2-6/M2-8).
        """
        return self._idempotency_index.get(idempotency_key)

    def case_ids(self) -> frozenset[str]:
        """Return the set of all case IDs with at least one event."""
        return frozenset(self._history.keys())
