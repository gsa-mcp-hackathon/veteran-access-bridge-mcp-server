"""Integration contracts and readiness report for the M6 demo.

These contracts describe replacement boundaries only. They do not imply access
to production VA interfaces, credentials, OAuth scopes, or booking authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from veteran_access_bridge.domain.models import (
    EPSSlotRecord,
    HSRMAuthorizationRecord,
    SourceSearchResult,
)


@runtime_checkable
class AvailabilityAdapter(Protocol):
    def search(self, patient_id: str, specialty: str, **kwargs) -> SourceSearchResult:
        """Return normalized source availability."""


@runtime_checkable
class CommunityAuthorizationAdapter(Protocol):
    def get_authorization_for_option(
        self, option_id: str, **kwargs
    ) -> HSRMAuthorizationRecord | None:
        """Return explicit referral/authorization evidence for an option."""

    def validate_authorization(
        self,
        record: HSRMAuthorizationRecord,
        intended_service: str,
        provider_id: str | None = None,
        **kwargs,
    ) -> tuple[bool, str]:
        """Validate existing authorization evidence without granting it."""


@runtime_checkable
class CommunitySchedulingAdapter(Protocol):
    def get_slot(self, slot_id: str, **kwargs) -> EPSSlotRecord | None:
        """Return a provider scheduling slot."""

    def recheck_slot(self, slot_id: str, **kwargs) -> bool:
        """Recheck provider slot availability at commit time."""


@dataclass(frozen=True)
class IntegrationCapability:
    system: str
    domain: str
    demo_adapter: str
    production_connection: str
    write_authority: str
    contract_status: str


def integration_readiness_report() -> dict:
    capabilities = (
        IntegrationCapability(
            system="VistA Scheduling",
            domain="VA appointment availability",
            demo_adapter="VistAAdapter",
            production_connection="not configured",
            write_authority="disabled",
            contract_status="normalized availability contract demonstrated",
        ),
        IntegrationCapability(
            system="Federal EHR / FHIR",
            domain="Federal EHR appointment availability",
            demo_adapter="FederalEHRAdapter",
            production_connection="not configured",
            write_authority="disabled",
            contract_status="normalized availability contract demonstrated",
        ),
        IntegrationCapability(
            system="HSRM-style Community Care",
            domain="referral and authorization evidence",
            demo_adapter="SyntheticHSRMAdapter",
            production_connection="not configured",
            write_authority="disabled",
            contract_status="authorization boundary demonstrated",
        ),
        IntegrationCapability(
            system="EPS-style Community Scheduling",
            domain="community provider availability and booking",
            demo_adapter="SyntheticEPSAdapter",
            production_connection="not configured",
            write_authority="simulated only",
            contract_status="availability/recheck/booking boundary demonstrated",
        ),
    )
    return {
        "synthetic": True,
        "production_writes_enabled": False,
        "architecture_statement": (
            "Veteran Access Bridge coordinates governed scheduling workflows; "
            "it does not replace HSRM or EPS and does not independently grant "
            "Community Care authorization."
        ),
        "capabilities": [c.__dict__ for c in capabilities],
        "production_gate": [
            "approved interface and data-use authority",
            "production identity and session enforcement",
            "VA security review and secrets management",
            "auditable least-privilege authorization",
            "transactional persistence and reconciliation",
            "operational monitoring and rollback procedures",
        ],
    }
