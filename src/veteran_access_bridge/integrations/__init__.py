"""Production-shaped integration contracts for the M6 demo."""

from .contracts import (
    AvailabilityAdapter,
    CommunityAuthorizationAdapter,
    CommunitySchedulingAdapter,
    integration_readiness_report,
)

__all__ = [
    "AvailabilityAdapter",
    "CommunityAuthorizationAdapter",
    "CommunitySchedulingAdapter",
    "integration_readiness_report",
]
