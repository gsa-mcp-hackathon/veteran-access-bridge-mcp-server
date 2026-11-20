"""Shared MCP process state.

This module holds the module-level singleton stores that are shared across all
MCP tool calls within a single server process. Each store is instantiated once
at import time.

All MCP tool modules must import shared state from here — never from sibling
tool modules. This keeps inter-tool dependencies explicit and avoids circular
cross-imports.

Tests do NOT use these singletons. Every tool exposes a run() function that
accepts optional injected stores; tests pass fresh instances directly.
"""

from __future__ import annotations

from veteran_access_bridge.services.booking import BookingStore, SlotReservationStore
from veteran_access_bridge.services.confirmation import ConfirmationStore
from veteran_access_bridge.services.events import CaseEventStore
from veteran_access_bridge.services.handoff import HandoffStore
from veteran_access_bridge.services.selection import SelectionStore
from veteran_access_bridge.services.verification import VerificationStore

# One CaseEventStore per server process — the authoritative lifecycle audit log.
event_store: CaseEventStore = CaseEventStore()

# One HandoffStore per server process — stores prepared SchedulingHandoff documents.
handoff_store: HandoffStore = HandoffStore()

# One SelectionStore per server process — stores OptionSelectionRecord documents.
selection_store: SelectionStore = SelectionStore()

# One VerificationStore per server process — stores VerificationResult documents.
verification_store: VerificationStore = VerificationStore()

# One ConfirmationStore per server process — stores ConfirmationRequest and
# VeteranConfirmationRecord documents.
confirmation_store: ConfirmationStore = ConfirmationStore()

# One BookingStore per server process — stores BookingRecord documents.
booking_store: BookingStore = BookingStore()

# One SlotReservationStore per server process — double-booking protection.
reservation_store: SlotReservationStore = SlotReservationStore()
