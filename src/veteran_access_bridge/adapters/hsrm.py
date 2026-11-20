"""Synthetic HSRM authorization adapter — M2-7.

Represents the Community Care authorization/referral domain (HSRM).
Returns deterministic fixture data keyed by authorization_id or option_id.

Governance rules:
- This adapter records existing authorization; it does not grant it.
- It never infers authorization from EPS availability.
- It never infers clinical eligibility or clinical appropriateness.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from veteran_access_bridge.domain.models import (
    HSRMAuthorizationRecord,
    HSRMAuthorizationStatus,
)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hsrm-authorizations.json"


def _load_fixtures() -> dict:
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _record_from_raw(raw: dict, retrieved_at: datetime) -> HSRMAuthorizationRecord:
    return HSRMAuthorizationRecord(
        authorization_id=raw["authorization_id"],
        referral_id=raw["referral_id"],
        case_id=raw["case_id"],
        option_id=raw["option_id"],
        authorized_service=raw["authorized_service"],
        status=HSRMAuthorizationStatus(raw["status"]),
        effective_date=_parse_dt(raw["effective_date"]),
        expiration_date=_parse_dt(raw["expiration_date"]),
        retrieved_at=retrieved_at,
        provenance_ref=raw["provenance_ref"],
        authorized_provider_id=raw.get("authorized_provider_id"),
    )


class SyntheticHSRMAdapter:
    """Synthetic HSRM authorization adapter.

    Returns fixture-backed HSRMAuthorizationRecord objects. Does not make
    network calls. Does not grant authorization.
    """

    def __init__(self) -> None:
        self._fixtures = _load_fixtures()
        # Build secondary index: option_id → first matching authorization_id
        self._by_option: dict[str, str] = {}
        for auth_id, raw in self._fixtures.items():
            opt = raw.get("option_id")
            if opt and opt not in self._by_option:
                self._by_option[opt] = auth_id

    def get_authorization(
        self,
        authorization_id: str,
        *,
        _as_of: Optional[datetime] = None,
    ) -> Optional[HSRMAuthorizationRecord]:
        """Return the authorization record for an authorization_id, or None."""
        raw = self._fixtures.get(authorization_id)
        if raw is None:
            return None
        retrieved_at = _as_of if _as_of is not None else datetime.now(timezone.utc)
        return _record_from_raw(raw, retrieved_at)

    def get_authorization_for_option(
        self,
        option_id: str,
        *,
        _as_of: Optional[datetime] = None,
    ) -> Optional[HSRMAuthorizationRecord]:
        """Return the authorization record for an option_id, or None."""
        auth_id = self._by_option.get(option_id)
        if auth_id is None:
            return None
        return self.get_authorization(auth_id, _as_of=_as_of)

    def validate_authorization(
        self,
        record: HSRMAuthorizationRecord,
        intended_service: str,
        provider_id: Optional[str] = None,
        *,
        _as_of: Optional[datetime] = None,
    ) -> tuple[bool, str]:
        """Validate an authorization record against the intended service.

        Returns (True, "") on success or (False, reason) on failure.
        """
        as_of = _as_of if _as_of is not None else datetime.now(timezone.utc)

        if record.status != HSRMAuthorizationStatus.ACTIVE:
            return False, f"Authorization {record.authorization_id!r} status is {record.status!r}, not ACTIVE."

        if as_of > record.expiration_date:
            return False, (
                f"Authorization {record.authorization_id!r} expired at "
                f"{record.expiration_date.isoformat()}."
            )

        if record.authorized_service.upper() != intended_service.upper():
            return False, (
                f"Authorization {record.authorization_id!r} covers "
                f"{record.authorized_service!r}, not {intended_service!r}."
            )

        if (
            record.authorized_provider_id is not None
            and provider_id is not None
            and record.authorized_provider_id != provider_id
        ):
            return False, (
                f"Authorization {record.authorization_id!r} is for provider "
                f"{record.authorized_provider_id!r}, not {provider_id!r}."
            )

        return True, ""
