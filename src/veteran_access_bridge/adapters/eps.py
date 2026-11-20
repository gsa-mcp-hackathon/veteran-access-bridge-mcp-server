"""Synthetic EPS availability adapter — M2-7.

Represents the Community Care scheduling/availability domain (EPS).
Returns deterministic fixture data keyed by slot_id or option_id.

Governance rules:
- This adapter determines slot availability only.
- It never creates or infers Community Care authorization.
- Authorization is the responsibility of the HSRM domain.
- FOLLOW_UP intents must not proceed via this adapter's initial-consult path.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from veteran_access_bridge.domain.models import EPSSlotRecord

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "eps-slots.json"


def _load_fixtures() -> dict:
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _record_from_raw(raw: dict, retrieved_at: datetime) -> EPSSlotRecord:
    return EPSSlotRecord(
        slot_id=raw["slot_id"],
        option_id=raw["option_id"],
        provider_id=raw["provider_id"],
        provider_name=raw.get("provider_name"),
        appointment_start=_parse_dt(raw["appointment_start"]),
        appointment_end=_parse_dt(raw["appointment_end"]),
        available=raw["available"],
        initial_consult_eligible=raw["initial_consult_eligible"],
        retrieved_at=retrieved_at,
        provenance_ref=raw["provenance_ref"],
    )


class SyntheticEPSAdapter:
    """Synthetic EPS availability adapter.

    Returns fixture-backed EPSSlotRecord objects. Does not make network calls.
    Does not determine authorization.
    """

    def __init__(self) -> None:
        self._fixtures = _load_fixtures()
        # Build secondary index: option_id → list of slot_ids
        self._by_option: dict[str, list[str]] = {}
        for slot_id, raw in self._fixtures.items():
            opt = raw.get("option_id")
            if opt:
                self._by_option.setdefault(opt, []).append(slot_id)

    def get_slot(
        self,
        slot_id: str,
        *,
        _as_of: Optional[datetime] = None,
    ) -> Optional[EPSSlotRecord]:
        """Return the slot record for a slot_id, or None if not found."""
        raw = self._fixtures.get(slot_id)
        if raw is None:
            return None
        retrieved_at = _as_of if _as_of is not None else datetime.now(timezone.utc)
        return _record_from_raw(raw, retrieved_at)

    def recheck_slot(
        self,
        slot_id: str,
        *,
        _as_of: Optional[datetime] = None,
    ) -> bool:
        """Re-verify that a slot is still available at commit time."""
        slot = self.get_slot(slot_id, _as_of=_as_of)
        if slot is None:
            return False
        return slot.available
