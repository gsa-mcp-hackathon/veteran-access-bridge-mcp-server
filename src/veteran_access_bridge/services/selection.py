"""Option selection service — M2-4.

validate_option_selection() and record_option_selection() implement the
governed Scheduler option-selection step.

Design rules
------------
1. Selection originates from a valid prepared handoff.
   The option_id must exist in the handoff retrieved from HandoffStore.

2. The case must be in HUMAN_REVIEW (the pre-selection lifecycle state).
   Missing lifecycle history fails closed.

3. Not all handoff options are selectable.
   STALE, UNAVAILABLE, SOURCE_UNAVAILABLE, AVAILABLE_NOT_AUTHORIZED → rejected.
   AVAILABLE, AUTHORIZED_NOT_VERIFIED, VERIFIED_BOOKABLE → selectable.
   AUTHORIZED_NOT_VERIFIED is selectable but sets requires_verification=True.

4. Only ActorRole.SCHEDULER may record a selection.
   VETERAN and SYSTEM are rejected with ValueError.

5. Idempotency key is caller-supplied.
   selection_id is derived deterministically: SHA-256(idempotency_key)[:16].
   Same key + identical material fields → return existing record (no-op).
   Same key + different case/handoff/option/actor → IdempotencyConflictError.
   No event is appended and no selection record is written on a conflict.

6. Exactly one OPTION_SELECTED lifecycle event per selection.
   CaseEventStore deduplicates via idempotency_key; retry returns existing event.

7. Selection does not mean authorization, verification, booking, or confirmation.
   This step only records HUMAN_REVIEW → OPTION_SELECTED.
   Routing to READY_TO_VERIFY vs VERIFIED_BOOKABLE is M2-5 (verification service).
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
    OptionSelectionRecord,
    OptionSelectionValidation,
)
from veteran_access_bridge.services.events import CaseEventStore, IdempotencyConflictError
from veteran_access_bridge.services.handoff import HandoffStore

# Lifecycle state in which selection is permitted.
_REQUIRED_PRE_SELECTION_STATE = CaseLifecycleState.HUMAN_REVIEW

# Readiness values that make an option non-selectable.
_REJECTED_READINESS: frozenset[OptionReadiness] = frozenset({
    OptionReadiness.STALE,
    OptionReadiness.UNAVAILABLE,
    OptionReadiness.SOURCE_UNAVAILABLE,
    OptionReadiness.AVAILABLE_NOT_AUTHORIZED,
})


def _selection_id_from_key(idempotency_key: str) -> str:
    """Derive a deterministic selection_id from the caller-supplied idempotency_key."""
    return "sel-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]


def _material_fields(record: OptionSelectionRecord) -> tuple:
    """Return the fields that constitute 'identical' for idempotency comparison."""
    return (
        record.case_id,
        record.handoff_id,
        record.option_id,
        record.selected_by_role,
        record.selected_by_id,
    )


class SelectionStore:
    """In-memory repository for OptionSelectionRecord documents.

    Parallel to HandoffStore. The CaseEventStore records that a selection
    occurred (audit); SelectionStore holds the full selection document.

    put() is first-write wins per selection_id.
    get_by_key() retrieves by idempotency_key.
    get_for_case() returns the most recent selection for a case, or None.
    """

    def __init__(self) -> None:
        self._by_selection_id: dict[str, OptionSelectionRecord] = {}
        self._by_idempotency_key: dict[str, OptionSelectionRecord] = {}
        # case_id → list of selection_ids in insertion order
        self._case_index: dict[str, list[str]] = {}

    def put(self, record: OptionSelectionRecord) -> None:
        """Store a record. First write wins; subsequent puts with same id are no-ops."""
        if record.selection_id not in self._by_selection_id:
            self._by_selection_id[record.selection_id] = record
            self._by_idempotency_key[record.idempotency_key] = record
            self._case_index.setdefault(record.case_id, []).append(record.selection_id)

    def get(self, selection_id: str) -> Optional[OptionSelectionRecord]:
        return self._by_selection_id.get(selection_id)

    def get_by_key(self, idempotency_key: str) -> Optional[OptionSelectionRecord]:
        return self._by_idempotency_key.get(idempotency_key)

    def get_for_case(self, case_id: str) -> Optional[OptionSelectionRecord]:
        """Return the most recently stored selection for a case, or None."""
        ids = self._case_index.get(case_id, [])
        if not ids:
            return None
        return self._by_selection_id[ids[-1]]

    def __len__(self) -> int:
        return len(self._by_selection_id)


def validate_option_selection(
    case_id: str,
    handoff_id: str,
    option_id: str,
    event_store: CaseEventStore,
    handoff_store: HandoffStore,
) -> OptionSelectionValidation:
    """Validate that an option may be selected from a prepared handoff.

    Read-only: no state is written. Returns an OptionSelectionValidation
    with valid=True and the option if all conditions pass, or valid=False
    with a reason string if any condition fails.

    Validation sequence
    -------------------
    1. Case has lifecycle history (fails closed on missing history).
    2. Case is in HUMAN_REVIEW.
    3. Handoff exists in HandoffStore.
    4. option_id is present in handoff.options.
    5. Option readiness is selectable (not in _REJECTED_READINESS).
    """
    record = event_store.get_lifecycle_record(case_id)
    if record is None:
        return OptionSelectionValidation(
            valid=False,
            reason=(
                f"Case {case_id!r} has no lifecycle history. "
                "A persisted lifecycle record at HUMAN_REVIEW is required."
            ),
        )

    if record.current_state != _REQUIRED_PRE_SELECTION_STATE:
        return OptionSelectionValidation(
            valid=False,
            reason=(
                f"Case {case_id!r} is in lifecycle state "
                f"{record.current_state!r}. "
                f"Selection requires {_REQUIRED_PRE_SELECTION_STATE!r}."
            ),
        )

    handoff = handoff_store.get(handoff_id)
    if handoff is None:
        return OptionSelectionValidation(
            valid=False,
            reason=f"Handoff {handoff_id!r} not found.",
        )

    option: Optional[AccessOption] = next(
        (o for o in handoff.options if o.option_id == option_id), None
    )
    if option is None:
        return OptionSelectionValidation(
            valid=False,
            reason=(
                f"Option {option_id!r} is not present in handoff {handoff_id!r}."
            ),
        )

    if option.readiness in _REJECTED_READINESS:
        return OptionSelectionValidation(
            valid=False,
            reason=(
                f"Option {option_id!r} has readiness {option.readiness!r} "
                "and is not selectable. Options with readiness STALE, UNAVAILABLE, "
                "SOURCE_UNAVAILABLE, or AVAILABLE_NOT_AUTHORIZED cannot be selected."
            ),
        )

    requires_verification = option.readiness == OptionReadiness.AUTHORIZED_NOT_VERIFIED
    return OptionSelectionValidation(
        valid=True,
        option=option,
        requires_verification=requires_verification,
        reason=(
            "Verification required before booking."
            if requires_verification else ""
        ),
    )


def record_option_selection(
    case_id: str,
    handoff_id: str,
    option_id: str,
    actor_role: ActorRole,
    actor_id: str,
    idempotency_key: str,
    event_store: CaseEventStore,
    handoff_store: HandoffStore,
    selection_store: SelectionStore,
    *,
    _as_of: Optional[datetime] = None,
) -> OptionSelectionRecord:
    """Record a Scheduler's option selection and advance lifecycle to OPTION_SELECTED.

    Parameters
    ----------
    case_id:           The synthetic scheduling case ID.
    handoff_id:        The handoff the option is being selected from.
    option_id:         The option_id of the AccessOption being selected.
    actor_role:        Must be ActorRole.SCHEDULER.
    actor_id:          Opaque actor identifier (synthetic/demo only).
    idempotency_key:   Caller-supplied deduplication key.
    event_store:       CaseEventStore — must already contain lifecycle history
                       with current state HUMAN_REVIEW.
    handoff_store:     HandoffStore — must contain the specified handoff.
    selection_store:   SelectionStore — persists the OptionSelectionRecord.
    _as_of:            Explicit timestamp for deterministic testing.

    Returns
    -------
    OptionSelectionRecord
        The stored (or previously stored) selection record.

    Raises
    ------
    ValueError
        If actor_role is not SCHEDULER, if validation fails, or if lifecycle
        history is missing or in the wrong state.
    IdempotencyConflictError
        If idempotency_key is reused with different material selection fields.
    """
    occurred_at = _as_of if _as_of is not None else datetime.now(timezone.utc)

    # ── 1. Role guard ─────────────────────────────────────────────────────
    if actor_role != ActorRole.SCHEDULER:
        raise ValueError(
            f"Only ActorRole.SCHEDULER may record an option selection. "
            f"Got: {actor_role!r}."
        )

    # ── 2. Idempotency: check existing record by key ───────────────────────
    selection_id = _selection_id_from_key(idempotency_key)
    existing = selection_store.get_by_key(idempotency_key)
    if existing is not None:
        # Same key with identical material fields → idempotent return
        if _material_fields(existing) == (case_id, handoff_id, option_id,
                                           actor_role, actor_id):
            return existing
        # Same key with different material fields → fail closed
        raise IdempotencyConflictError(
            f"idempotency_key {idempotency_key!r} already used for a different "
            f"selection. Existing: case={existing.case_id!r} "
            f"option={existing.option_id!r} actor={existing.selected_by_id!r}. "
            f"New: case={case_id!r} option={option_id!r} actor={actor_id!r}. "
            "Generate a new idempotency_key for a different selection."
        )

    # ── 3. Validate ────────────────────────────────────────────────────────
    validation = validate_option_selection(
        case_id, handoff_id, option_id, event_store, handoff_store
    )
    if not validation.valid:
        raise ValueError(
            f"Option selection validation failed: {validation.reason}"
        )

    # validation.option is guaranteed non-None when valid=True
    assert validation.option is not None  # satisfy type checker

    # ── 4. Build the selection record ──────────────────────────────────────
    record = OptionSelectionRecord(
        selection_id=selection_id,
        case_id=case_id,
        handoff_id=handoff_id,
        option_id=option_id,
        readiness_at_selection=validation.option.readiness,
        requires_verification=validation.requires_verification,
        selected_at=occurred_at,
        selected_by_role=actor_role,
        selected_by_id=actor_id,
        idempotency_key=idempotency_key,
        synthetic=True,
    )

    # ── 5. Append the lifecycle event ──────────────────────────────────────
    lc_record = event_store.get_lifecycle_record(case_id)
    assert lc_record is not None  # validated above

    evt = CaseEvent(
        event_id=idempotency_key,      # deterministic: same as idempotency_key
        case_id=case_id,
        event_type=CaseEventType.OPTION_SELECTED,
        from_state=lc_record.current_state,   # HUMAN_REVIEW (validated)
        to_state=CaseLifecycleState.OPTION_SELECTED,
        actor_role=actor_role,
        actor_id=actor_id,
        occurred_at=occurred_at,
        idempotency_key=idempotency_key,
        payload={
            "selection_id": selection_id,
            "option_id": option_id,
            "handoff_id": handoff_id,
            "readiness": validation.option.readiness.value,
            "requires_verification": validation.requires_verification,
        },
    )
    event_store.append(evt)

    # ── 6. Persist the selection record ────────────────────────────────────
    selection_store.put(record)

    return record
