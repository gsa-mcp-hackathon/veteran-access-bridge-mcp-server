"""prepare_scheduling_handoff — M2-3 handoff preparation service.

Design
------
A SchedulingHandoff is a review artifact — not a decision. Preparing a handoff
never selects, verifies, authorizes, or books an option. It filters the options
returned by search_availability() to those that are viable for scheduler review
and records that the preparation occurred in the CaseEventStore.

Storage boundary
----------------
Two stores are used for two separate responsibilities:

  CaseEventStore  — records the HANDOFF_PREPARED event (what happened and when).
                    The event payload carries handoff_id. The event log is
                    append-only and must not be used to look up the full handoff.

  HandoffStore    — holds the full SchedulingHandoff document indexed by
                    handoff_id. The MCP tool get_scheduling_handoff reads from
                    this store. It is intentionally separate from the event log.

Viability filter
----------------
An option is viable for handoff iff:
  - readiness not in {STALE, UNAVAILABLE, SOURCE_UNAVAILABLE}
  - readiness is not AVAILABLE_NOT_AUTHORIZED (Community Care slot that has no
    authorization reference — requires scheduler action before handoff)

Community Care options that ARE AUTHORIZED_NOT_VERIFIED are included but
flagged: requires_verification=True is set on the handoff.

All readiness values are preserved exactly as set by the adapter. This function
must not upgrade, downgrade, or re-infer any readiness value.

Idempotency
-----------
handoff_id is a deterministic SHA-256 hash of (case_id, sorted option_ids of
the viable options). Identical viable-option sets always produce the same
handoff_id. A second call with the same effective inputs:
  - finds the idempotency_key already in the CaseEventStore → no second event
  - finds the handoff_id already in the HandoffStore → returns the existing doc

Allowed pre-handoff lifecycle states
-------------------------------------
  READY_FOR_HANDOFF — the canonical state for handoff preparation
  VA_OPTIONS_AVAILABLE, COMMUNITY_OPTIONS_AVAILABLE — also accepted because the
  service layer may not have explicitly advanced the state before preparing the
  handoff artifact.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from veteran_access_bridge.domain.models import (
    AccessOption,
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    OptionReadiness,
    SchedulingHandoff,
    SearchAvailabilityResult,
    SourceSearchStatus,
)
from veteran_access_bridge.services.events import CaseEventStore

# States in which prepare_scheduling_handoff may be called.
_ALLOWED_PRE_HANDOFF_STATES: frozenset[CaseLifecycleState] = frozenset({
    CaseLifecycleState.VA_OPTIONS_AVAILABLE,
    CaseLifecycleState.COMMUNITY_OPTIONS_AVAILABLE,
    CaseLifecycleState.READY_FOR_HANDOFF,
})

# Readiness values that make an option ineligible for the handoff.
_EXCLUDED_READINESS: frozenset[OptionReadiness] = frozenset({
    OptionReadiness.STALE,
    OptionReadiness.UNAVAILABLE,
    OptionReadiness.SOURCE_UNAVAILABLE,
    OptionReadiness.AVAILABLE_NOT_AUTHORIZED,
})

# Community Care readiness values that require verification before booking.
_REQUIRES_VERIFICATION_READINESS: frozenset[OptionReadiness] = frozenset({
    OptionReadiness.AUTHORIZED_NOT_VERIFIED,
})


def _viable_options(options: tuple[AccessOption, ...]) -> tuple[AccessOption, ...]:
    """Return only options that pass the viability filter."""
    return tuple(o for o in options if o.readiness not in _EXCLUDED_READINESS)


def _deterministic_handoff_id(case_id: str, options: tuple[AccessOption, ...]) -> str:
    """Produce a stable, deterministic handoff_id from case and option IDs."""
    sorted_ids = sorted(o.option_id for o in options)
    raw = f"{case_id}:{','.join(sorted_ids)}"
    return "handoff-" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _build_source_summary(
    viable: tuple[AccessOption, ...],
    search_result: SearchAvailabilityResult,
) -> str:
    """Produce a short human-readable source summary for the handoff."""
    source_counts: dict[str, int] = {}
    for opt in viable:
        source_counts[opt.source_system] = source_counts.get(opt.source_system, 0) + 1

    failed_sources = [
        r.source_system
        for r in search_result.source_results
        if r.status not in (SourceSearchStatus.SUCCESS, SourceSearchStatus.PARTIAL,
                            SourceSearchStatus.NO_SLOTS)
    ]

    parts = [f"{src}: {n} option(s)" for src, n in sorted(source_counts.items())]
    if failed_sources:
        parts.append("unavailable: " + ", ".join(sorted(failed_sources)))
    return "; ".join(parts) if parts else "no viable options"


def _idempotency_key_for_handoff(case_id: str, handoff_id: str) -> str:
    return f"{case_id}:HANDOFF_PREPARED:{handoff_id}"


def prepare_scheduling_handoff(
    case_id: str,
    search_result: SearchAvailabilityResult,
    event_store: CaseEventStore,
    handoff_store: "HandoffStore",
    *,
    actor_id: str = "system",
    _as_of: Optional[datetime] = None,
) -> SchedulingHandoff:
    """Prepare a scheduling handoff from a completed availability search.

    The case must have a persisted lifecycle record at an allowed pre-handoff
    state before this function may advance lifecycle state. Missing lifecycle
    history fails closed — this function does not manufacture or backfill
    historical events.

    Parameters
    ----------
    case_id:
        The synthetic scheduling case ID.
    search_result:
        The SearchAvailabilityResult returned by search_availability(). Must
        belong to this case (patient_id and consult_id are not re-checked here;
        the MCP tool wrapper validates the case match).
    event_store:
        The CaseEventStore to record the HANDOFF_PREPARED event. Must already
        contain at least one event for this case in an allowed pre-handoff state.
    handoff_store:
        The HandoffStore to persist and retrieve the SchedulingHandoff document.
    actor_id:
        Opaque identifier for the actor (synthetic/demo only).
    _as_of:
        Explicit timestamp for deterministic testing. Defaults to utcnow().

    Returns
    -------
    SchedulingHandoff
        The prepared (or previously prepared) handoff document.

    Raises
    ------
    ValueError
        If the case has no lifecycle record in the event store (missing lifecycle
        history), or if the current lifecycle state is not in the allowed
        pre-handoff states.
    """
    occurred_at = _as_of if _as_of is not None else datetime.now(timezone.utc)

    # ── 1. Viability filter ───────────────────────────────────────────────
    viable = _viable_options(search_result.options)
    handoff_id = _deterministic_handoff_id(case_id, viable)

    # ── 2. Idempotency: return existing handoff if already prepared ───────
    existing = handoff_store.get(handoff_id)
    if existing is not None:
        return existing

    # ── 3. Validate lifecycle state — fail closed on missing history ───────
    record = event_store.get_lifecycle_record(case_id)
    if record is None:
        raise ValueError(
            f"Case {case_id!r} has no lifecycle history in the event store. "
            "A persisted lifecycle record at an allowed pre-handoff state is "
            "required before a handoff may be prepared. Allowed states: "
            f"{sorted(s.value for s in _ALLOWED_PRE_HANDOFF_STATES)}. "
            "Seed the event store with the appropriate lifecycle events before "
            "calling prepare_scheduling_handoff."
        )
    if record.current_state not in _ALLOWED_PRE_HANDOFF_STATES:
        raise ValueError(
            f"Case {case_id!r} is in lifecycle state "
            f"{record.current_state!r}, which does not permit handoff "
            f"preparation. Allowed states: "
            f"{sorted(s.value for s in _ALLOWED_PRE_HANDOFF_STATES)}."
        )

    # ── 4. Build the handoff document ────────────────────────────────────
    requires_verification = any(
        o.readiness in _REQUIRES_VERIFICATION_READINESS for o in viable
    )
    source_summary = _build_source_summary(viable, search_result)

    handoff = SchedulingHandoff(
        handoff_id=handoff_id,
        patient_id=search_result.patient_id,
        consult_id=search_result.consult_id,
        prepared_at=occurred_at,
        options=viable,
        viable_option_count=len(viable),
        source_summary=source_summary,
        requires_verification=requires_verification,
        synthetic=True,
    )

    # ── 5. Persist the handoff document ───────────────────────────────────
    handoff_store.put(handoff)

    # ── 6. Record the lifecycle event ─────────────────────────────────────
    idem_key = _idempotency_key_for_handoff(case_id, handoff_id)
    evt = CaseEvent(
        event_id=idem_key,  # deterministic event_id = idempotency_key for this event
        case_id=case_id,
        event_type=CaseEventType.HANDOFF_PREPARED,
        from_state=record.current_state,
        to_state=CaseLifecycleState.HUMAN_REVIEW,
        actor_role=ActorRole.SYSTEM,
        actor_id=actor_id,
        occurred_at=occurred_at,
        idempotency_key=idem_key,
        payload={"handoff_id": handoff_id, "viable_option_count": len(viable)},
    )
    # append() is idempotent on the key; a retry returns the existing event.
    event_store.append(evt)

    return handoff


class HandoffStore:
    """In-memory repository for SchedulingHandoff documents.

    Separate from CaseEventStore. The event store records that a handoff was
    prepared; this store holds the full handoff document for retrieval.

    get() is idempotent and read-only.
    put() stores a handoff; a second put with the same handoff_id is silently
    ignored (the first write wins, consistent with idempotent preparation).
    """

    def __init__(self) -> None:
        self._store: dict[str, SchedulingHandoff] = {}

    def put(self, handoff: SchedulingHandoff) -> None:
        """Store a handoff. First write wins; subsequent puts are no-ops."""
        if handoff.handoff_id not in self._store:
            self._store[handoff.handoff_id] = handoff

    def get(self, handoff_id: str) -> Optional[SchedulingHandoff]:
        """Return the handoff document, or None if not found."""
        return self._store.get(handoff_id)

    def __len__(self) -> int:
        return len(self._store)
