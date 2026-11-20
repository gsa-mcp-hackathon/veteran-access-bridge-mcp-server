"""Server-enforced demo identity, role, and case-scope authorization.

This module is intentionally explicit that the local persona headers are a
synthetic demonstration mechanism, not production authentication.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DemoRole(StrEnum):
    VETERAN = "VETERAN"
    SCHEDULER = "SCHEDULER"


@dataclass(frozen=True)
class DemoPrincipal:
    actor_id: str
    role: DemoRole
    case_ids: frozenset[str]
    synthetic: bool = True


class AuthorizationError(PermissionError):
    """Raised when a demo principal is not allowed to perform an action."""


_ACTION_ROLES: dict[str, frozenset[DemoRole]] = {
    "view_case": frozenset({DemoRole.VETERAN, DemoRole.SCHEDULER}),
    "view_options": frozenset({DemoRole.VETERAN, DemoRole.SCHEDULER}),
    "view_audit": frozenset({DemoRole.SCHEDULER}),
    "view_metrics": frozenset({DemoRole.SCHEDULER}),
    "view_integrations": frozenset({DemoRole.SCHEDULER}),
    "select_option": frozenset({DemoRole.SCHEDULER}),
    "verify_option": frozenset({DemoRole.SCHEDULER}),
    "request_confirmation": frozenset({DemoRole.SCHEDULER}),
    "respond_confirmation": frozenset({DemoRole.VETERAN}),
    "send_secure_demo_message": frozenset({DemoRole.VETERAN}),
    "commit_booking": frozenset({DemoRole.SCHEDULER}),
    "record_outcome": frozenset({DemoRole.SCHEDULER}),
}


def authorize(principal: DemoPrincipal, case_id: str, action: str) -> None:
    """Enforce role and case scope for one application action."""
    allowed = _ACTION_ROLES.get(action)
    if allowed is None:
        raise AuthorizationError(f"Unknown protected action {action!r}.")
    if principal.role not in allowed:
        raise AuthorizationError(
            f"Role {principal.role.value} is not allowed to perform {action!r}."
        )
    if case_id not in principal.case_ids:
        raise AuthorizationError(
            f"Actor {principal.actor_id!r} is not scoped to case {case_id!r}."
        )


def principal_from_headers(
    role_header: str | None,
    actor_header: str | None,
    case_header: str | None,
) -> DemoPrincipal:
    """Build a synthetic principal from local-demo HTTP headers.

    Required headers:
      X-Demo-Role: VETERAN or SCHEDULER
      X-Demo-Actor: opaque synthetic actor ID
      X-Demo-Case: comma-separated synthetic case IDs

    The server validates all three values. The browser cannot choose actions
    outside the resulting role/case scope.
    """
    if not role_header or not actor_header or not case_header:
        raise AuthorizationError(
            "Missing demo identity headers. X-Demo-Role, X-Demo-Actor, "
            "and X-Demo-Case are required."
        )
    try:
        role = DemoRole(role_header.strip().upper())
    except ValueError as exc:
        raise AuthorizationError(
            f"Invalid X-Demo-Role {role_header!r}. "
            f"Allowed: {[r.value for r in DemoRole]}."
        ) from exc
    case_ids = frozenset(
        item.strip() for item in case_header.split(",") if item.strip()
    )
    if not case_ids:
        raise AuthorizationError("X-Demo-Case must contain at least one case ID.")
    return DemoPrincipal(
        actor_id=actor_header.strip(),
        role=role,
        case_ids=case_ids,
    )
