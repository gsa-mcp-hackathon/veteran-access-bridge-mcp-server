"""Local-only signed scheduler assertion verification for synthetic EPS booking.

This verifies an assertion issued by a separately trusted authority. It does
not issue credentials or turn demo persona headers into real authentication.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt

from veteran_access_bridge.services.pg_governed_eps_commit import (
    VerifiedSchedulerContext,
)

ISSUER = "vab-local-scheduler-authority"
AUDIENCE = "vab-synthetic-eps-booking"


@dataclass(frozen=True)
class SchedulerAssertionClaims:
    actor_id: str
    case_id: str


def verify_scheduler_assertion(
    token: str, *, signing_secret: str, required_case_id: str
) -> VerifiedSchedulerContext:
    """Verify signature, expiration, issuer, audience, role and exact case scope.

    The secret must be injected via an independent trusted server configuration,
    never accepted from MCP arguments or persona headers. There is no token
    issuance path here; accepting an untrusted issuer invalidates this boundary.
    """
    if not isinstance(signing_secret, str) or len(signing_secret.encode()) < 32:
        raise PermissionError("Strong scheduler assertion verifier secret required")
    if not token or not required_case_id:
        raise PermissionError("Signed scheduler assertion and case required")
    try:
        claims = jwt.decode(
            token,
            signing_secret,
            algorithms=["HS256"],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "role", "case_id"]},
            leeway=0,
        )
    except jwt.PyJWTError as exc:
        raise PermissionError("Invalid or expired scheduler assertion") from exc

    actor = claims.get("sub")
    case_id = claims.get("case_id")
    if (
        claims.get("role") != "SCHEDULER"
        or not isinstance(actor, str)
        or not actor.strip()
        or not isinstance(case_id, str)
        or case_id != required_case_id
        or claims.get("synthetic") is not True
    ):
        raise PermissionError("Scheduler assertion role/case/provenance mismatch")
    return VerifiedSchedulerContext(
        actor_id=actor,
        case_id=case_id,
        authenticated=True,
        authorized_scheduler=True,
    )
