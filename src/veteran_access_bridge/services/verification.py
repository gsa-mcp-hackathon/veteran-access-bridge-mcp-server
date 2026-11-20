"""Verification service — M2-5.

route_from_option_selected() and record_verification_result() implement the
governed verification branch of the scheduling lifecycle.

Design rules
------------
1. Two distinct steps; do not conflate them.

   route_from_option_selected():
       A mechanical SYSTEM action that routes OPTION_SELECTED to either
       VERIFIED_BOOKABLE (VA/Federal EHR) or READY_TO_VERIFY (Community Care).
       The scheduling decision was already captured by record_option_selection();
       no Scheduler action is needed here.
       - VA/Federal AVAILABLE / VERIFIED_BOOKABLE → VERIFIED_BOOKABLE
         Event: VERIFICATION_PASSED. Creates + stores VerificationResult.
       - Community Care AUTHORIZED_NOT_VERIFIED → READY_TO_VERIFY
         Event: VERIFICATION_REQUIRED. Does NOT create a VerificationResult.
         Explicit authorization evidence is required next.

   record_verification_result():
       A Scheduler-gated step that resolves READY_TO_VERIFY based on explicit
       synthetic evidence supplied by the authorized actor.
       - outcome=VERIFIED     → VERIFIED_BOOKABLE (VERIFICATION_PASSED)
       - outcome=AUTH_REQUIRED → AUTH_REQUIRED    (VERIFICATION_FAILED)
       - outcome=INCONCLUSIVE  → HUMAN_REVIEW     (VERIFICATION_INCONCLUSIVE)
       Always creates + stores a VerificationResult.

2. The service never independently determines authorization.
   Outcome is supplied explicitly by the caller. evidence_ref is required for
   Community Care resolution — empty string is rejected.

3. Idempotency matches M2-4 exactly.
   verification_id = "ver-" + SHA-256(idempotency_key)[:16].
   VerificationStore keyed by verification_id and idempotency_key.
   VA/Federal path: same key + same material → return existing VerificationResult.
   CC routing path: CaseEventStore idempotency handles duplicate routing calls;
       route_from_option_selected returns None on idempotent CC retry.
   Same key + different material fields → IdempotencyConflictError.

4. Missing or wrong lifecycle state fails closed.
   No backfill, no fallback, no default state.

5. Exactly one lifecycle event per successful forward transition.
   No event is appended on idempotent retries or failures.

Governance boundaries
---------------------
- Never grants Community Care authorization.
- Never interprets "authorization recorded" as "authorization verified."
- Never infers eligibility, clinical urgency, or clinical appropriateness.
- Does not modify booking behavior, Veteran confirmation, or booking gates.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from veteran_access_bridge.domain.models import (
    ActorRole,
    CaseEvent,
    CaseEventType,
    CaseLifecycleState,
    OptionReadiness,
    VerificationOutcome,
    VerificationResult,
)
from veteran_access_bridge.services.events import CaseEventStore, IdempotencyConflictError
from veteran_access_bridge.services.selection import SelectionStore

# Lifecycle state from which routing originates.
_OPTION_SELECTED = CaseLifecycleState.OPTION_SELECTED

# Lifecycle state in which explicit verification evidence is resolved.
_READY_TO_VERIFY = CaseLifecycleState.READY_TO_VERIFY

# Readiness values that may advance directly to VERIFIED_BOOKABLE.
_DIRECT_BOOKABLE_READINESS: frozenset[OptionReadiness] = frozenset({
    OptionReadiness.AVAILABLE,
    OptionReadiness.VERIFIED_BOOKABLE,
})

# Readiness that requires the Community Care verification stage.
_REQUIRES_VERIFICATION_READINESS: frozenset[OptionReadiness] = frozenset({
    OptionReadiness.AUTHORIZED_NOT_VERIFIED,
})

# Outcome → (lifecycle target, event type)
_OUTCOME_ROUTING: dict[VerificationOutcome, tuple[CaseLifecycleState, CaseEventType]] = {
    VerificationOutcome.VERIFIED: (
        CaseLifecycleState.VERIFIED_BOOKABLE,
        CaseEventType.VERIFICATION_PASSED,
    ),
    VerificationOutcome.AUTH_REQUIRED: (
        CaseLifecycleState.AUTH_REQUIRED,
        CaseEventType.VERIFICATION_FAILED,
    ),
    VerificationOutcome.INCONCLUSIVE: (
        CaseLifecycleState.HUMAN_REVIEW,
        CaseEventType.VERIFICATION_INCONCLUSIVE,
    ),
}


def _verification_id_from_key(idempotency_key: str) -> str:
    """Derive a deterministic verification_id from the idempotency_key."""
    return "ver-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]


def _material_fields_result(result: VerificationResult) -> tuple:
    """Return the fields that constitute 'identical' for idempotency comparison."""
    return (result.case_id, result.option_id, result.outcome)


class VerificationStore:
    """In-memory repository for VerificationResult records.

    Parallel to SelectionStore and HandoffStore. Keyed by verification_id and
    idempotency_key. First-write wins per verification_id.

    get_for_case() returns the most recent VerificationResult for a case, or None.
    """

    def __init__(self) -> None:
        self._by_verification_id: dict[str, VerificationResult] = {}
        self._by_idempotency_key: dict[str, VerificationResult] = {}
        self._case_index: dict[str, list[str]] = {}

    def put(self, result: VerificationResult) -> None:
        """Store a result. First write wins; subsequent puts with same id are no-ops."""
        if result.verification_id not in self._by_verification_id:
            self._by_verification_id[result.verification_id] = result
            self._by_idempotency_key[result.idempotency_key] = result
            self._case_index.setdefault(result.case_id, []).append(result.verification_id)

    def get(self, verification_id: str) -> Optional[VerificationResult]:
        return self._by_verification_id.get(verification_id)

    def get_by_key(self, idempotency_key: str) -> Optional[VerificationResult]:
        return self._by_idempotency_key.get(idempotency_key)

    def get_for_case(self, case_id: str) -> Optional[VerificationResult]:
        """Return the most recently stored VerificationResult for a case, or None."""
        ids = self._case_index.get(case_id, [])
        if not ids:
            return None
        return self._by_verification_id[ids[-1]]

    def __len__(self) -> int:
        return len(self._by_verification_id)


def route_from_option_selected(
    case_id: str,
    selection_id: str,
    idempotency_key: str,
    event_store: CaseEventStore,
    selection_store: SelectionStore,
    verification_store: VerificationStore,
    *,
    _as_of: Optional[datetime] = None,
) -> Optional[VerificationResult]:
    """Route a case from OPTION_SELECTED based on the selected option's readiness.

    This is a mechanical SYSTEM action — no actor role parameter is needed.

    VA/Federal AVAILABLE / VERIFIED_BOOKABLE:
        Appends OPTION_SELECTED → VERIFIED_BOOKABLE (VERIFICATION_PASSED).
        Creates and returns a VerificationResult with outcome=VERIFIED.

    Community Care AUTHORIZED_NOT_VERIFIED:
        Appends OPTION_SELECTED → READY_TO_VERIFY (VERIFICATION_REQUIRED).
        Returns None — no VerificationResult yet; explicit evidence required next.

    Parameters
    ----------
    case_id:            Synthetic scheduling case ID.
    selection_id:       selection_id from the OptionSelectionRecord.
    idempotency_key:    Caller-supplied deduplication key.
    event_store:        Must contain lifecycle history at OPTION_SELECTED.
    selection_store:    Must contain an OptionSelectionRecord for selection_id.
    verification_store: VerificationStore for VA/Federal result persistence.
    _as_of:             Explicit timestamp for deterministic testing.

    Returns
    -------
    VerificationResult
        For VA/Federal direct-booking path (outcome=VERIFIED).
    None
        For Community Care routing path (pending explicit verification).

    Raises
    ------
    ValueError
        If selection_id is unknown, lifecycle state is wrong, or readiness is
        not in the allowed routing set.
    IdempotencyConflictError
        If idempotency_key is reused with different material fields.
    """
    occurred_at = _as_of if _as_of is not None else datetime.now(timezone.utc)

    # ── 1. Idempotency: check VerificationStore for prior VA/Federal result ─
    verification_id = _verification_id_from_key(idempotency_key)
    existing = verification_store.get_by_key(idempotency_key)
    if existing is not None:
        if _material_fields_result(existing) == (case_id, existing.option_id, existing.outcome):
            return existing
        raise IdempotencyConflictError(
            f"idempotency_key {idempotency_key!r} already used for a different "
            f"routing result. Existing: case={existing.case_id!r}. "
            f"New: case={case_id!r}. "
            "Generate a new idempotency_key for a different routing call."
        )

    # ── 2. Fetch selection record ──────────────────────────────────────────
    selection = selection_store.get(selection_id)
    if selection is None:
        raise ValueError(
            f"selection_id {selection_id!r} not found in SelectionStore. "
            "A OptionSelectionRecord must exist before routing."
        )

    # ── 3. Confirm lifecycle state ─────────────────────────────────────────
    lc_record = event_store.get_lifecycle_record(case_id)
    if lc_record is None:
        raise ValueError(
            f"Case {case_id!r} has no lifecycle history. "
            f"Lifecycle must be at {_OPTION_SELECTED!r} for routing."
        )
    if lc_record.current_state != _OPTION_SELECTED:
        raise ValueError(
            f"Case {case_id!r} is in lifecycle state {lc_record.current_state!r}. "
            f"route_from_option_selected requires {_OPTION_SELECTED!r}."
        )

    readiness = selection.readiness_at_selection

    # ── 4a. VA/Federal fast path ───────────────────────────────────────────
    if readiness in _DIRECT_BOOKABLE_READINESS:
        evt = CaseEvent(
            event_id=idempotency_key,
            case_id=case_id,
            event_type=CaseEventType.VERIFICATION_PASSED,
            from_state=CaseLifecycleState.OPTION_SELECTED,
            to_state=CaseLifecycleState.VERIFIED_BOOKABLE,
            actor_role=ActorRole.SYSTEM,
            actor_id="system",
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
            payload={
                "selection_id": selection_id,
                "option_id": selection.option_id,
                "readiness": readiness.value,
                "routing": "direct_bookable",
            },
        )
        event_store.append(evt)

        result = VerificationResult(
            verification_id=verification_id,
            case_id=case_id,
            option_id=selection.option_id,
            source_system=selection.handoff_id,  # best available; full option not in record
            outcome=VerificationOutcome.VERIFIED,
            evidence_ref=None,
            verified_at=occurred_at,
            requires_authorization=False,
            requires_human_review=False,
            idempotency_key=idempotency_key,
        )
        verification_store.put(result)
        return result

    # ── 4b. Community Care routing path ───────────────────────────────────
    if readiness in _REQUIRES_VERIFICATION_READINESS:
        evt = CaseEvent(
            event_id=idempotency_key,
            case_id=case_id,
            event_type=CaseEventType.VERIFICATION_REQUIRED,
            from_state=CaseLifecycleState.OPTION_SELECTED,
            to_state=CaseLifecycleState.READY_TO_VERIFY,
            actor_role=ActorRole.SYSTEM,
            actor_id="system",
            occurred_at=occurred_at,
            idempotency_key=idempotency_key,
            payload={
                "selection_id": selection_id,
                "option_id": selection.option_id,
                "readiness": readiness.value,
                "routing": "verification_required",
            },
        )
        event_store.append(evt)
        # No VerificationResult — pending explicit evidence from Scheduler.
        return None

    # ── 4c. Unsupported readiness ──────────────────────────────────────────
    raise ValueError(
        f"Option readiness {readiness!r} on selection {selection_id!r} cannot be "
        "routed from OPTION_SELECTED. Allowed: "
        f"{sorted(r.value for r in _DIRECT_BOOKABLE_READINESS | _REQUIRES_VERIFICATION_READINESS)}."
    )


def record_verification_result(
    case_id: str,
    option_id: str,
    source_system: str,
    evidence_ref: str,
    outcome: VerificationOutcome,
    actor_role: ActorRole,
    actor_id: str,
    idempotency_key: str,
    event_store: CaseEventStore,
    verification_store: VerificationStore,
    *,
    _as_of: Optional[datetime] = None,
) -> VerificationResult:
    """Record explicit verification evidence and advance READY_TO_VERIFY.

    The caller supplies outcome and evidence_ref. The service applies the
    outcome without independently judging authorization or eligibility.

    Parameters
    ----------
    case_id:            Synthetic scheduling case ID.
    option_id:          The AccessOption being verified.
    source_system:      Source system identifier for the option.
    evidence_ref:       Non-empty reference to authorization evidence checked.
                        Required — empty string is rejected.
    outcome:            VerificationOutcome supplied by the authorized actor.
    actor_role:         Must be ActorRole.SCHEDULER.
    actor_id:           Opaque actor identifier (synthetic/demo only).
    idempotency_key:    Caller-supplied deduplication key.
    event_store:        Must contain lifecycle history at READY_TO_VERIFY.
    verification_store: VerificationStore for result persistence.
    _as_of:             Explicit timestamp for deterministic testing.

    Returns
    -------
    VerificationResult
        The stored (or previously stored) verification result.

    Raises
    ------
    ValueError
        If actor_role is not SCHEDULER, evidence_ref is empty, lifecycle state
        is wrong, or lifecycle history is missing.
    IdempotencyConflictError
        If idempotency_key is reused with different material fields.
    """
    occurred_at = _as_of if _as_of is not None else datetime.now(timezone.utc)

    # ── 1. Role guard ─────────────────────────────────────────────────────
    if actor_role != ActorRole.SCHEDULER:
        raise ValueError(
            f"Only ActorRole.SCHEDULER may record a verification result. "
            f"Got: {actor_role!r}."
        )

    # ── 2. Evidence guard ─────────────────────────────────────────────────
    if not evidence_ref or not evidence_ref.strip():
        raise ValueError(
            "evidence_ref must be a non-empty string. Community Care "
            "verification requires an explicit reference to authorization "
            "evidence checked."
        )

    # ── 3. Idempotency: check VerificationStore ───────────────────────────
    verification_id = _verification_id_from_key(idempotency_key)
    existing = verification_store.get_by_key(idempotency_key)
    if existing is not None:
        if _material_fields_result(existing) == (case_id, option_id, outcome):
            return existing
        raise IdempotencyConflictError(
            f"idempotency_key {idempotency_key!r} already used for a different "
            f"verification. Existing: case={existing.case_id!r} "
            f"outcome={existing.outcome!r}. "
            f"New: case={case_id!r} outcome={outcome!r}. "
            "Generate a new idempotency_key for a different verification."
        )

    # ── 4. Confirm lifecycle state ─────────────────────────────────────────
    lc_record = event_store.get_lifecycle_record(case_id)
    if lc_record is None:
        raise ValueError(
            f"Case {case_id!r} has no lifecycle history. "
            f"Lifecycle must be at {_READY_TO_VERIFY!r} for verification."
        )
    if lc_record.current_state != _READY_TO_VERIFY:
        raise ValueError(
            f"Case {case_id!r} is in lifecycle state {lc_record.current_state!r}. "
            f"record_verification_result requires {_READY_TO_VERIFY!r}."
        )

    # ── 5. Map outcome → lifecycle transition ─────────────────────────────
    to_state, event_type = _OUTCOME_ROUTING[outcome]

    evt = CaseEvent(
        event_id=idempotency_key,
        case_id=case_id,
        event_type=event_type,
        from_state=CaseLifecycleState.READY_TO_VERIFY,
        to_state=to_state,
        actor_role=actor_role,
        actor_id=actor_id,
        occurred_at=occurred_at,
        idempotency_key=idempotency_key,
        payload={
            "option_id": option_id,
            "outcome": outcome.value,
            "evidence_ref": evidence_ref,
            "source_system": source_system,
        },
    )
    event_store.append(evt)

    # ── 6. Build and persist VerificationResult ───────────────────────────
    result = VerificationResult(
        verification_id=verification_id,
        case_id=case_id,
        option_id=option_id,
        source_system=source_system,
        outcome=outcome,
        evidence_ref=evidence_ref,
        verified_at=occurred_at,
        requires_authorization=(outcome == VerificationOutcome.AUTH_REQUIRED),
        requires_human_review=(outcome == VerificationOutcome.INCONCLUSIVE),
        idempotency_key=idempotency_key,
    )
    verification_store.put(result)
    return result
