# Avery guidelines and tool reconciliation — November 18, 2026

## Subsequent correction: remove paused workflow

The user confirmed that the agentic workflow was not part of the intended Avery
configuration and authorized detaching it. A fresh pre-change export contained
`Agentic_workflow_1_0468Ym` once in `tools`, with no references to that identifier
in other exported fields. A targeted scan found no references in application
source, active Orchestrate deployment files or evaluation instruction supplements.
This is configuration dependency checking, not proof of historical invocation.

The prepared update removes only that attachment: **21 MCP tools, eight guidelines,
no agentic workflow attachment**. The workflow definition is not deleted.
Model, instructions, context, plugins and all MCP tool bindings are preserved.
Private rollback export: `/tmp/avery-before-workflow-detach-20261118.yaml` in the
existing Codespace. The 22-attachment inventory below describes the earlier state.

## Fresh inventory

Authenticated `tools/list` on the existing canary returned **29 MCP tools**.
CRM and agent scheduling are enabled. A fresh IBM agent export returned **22
attachments: 21 consolidated MCP tools and one `Agentic_workflow_1_0468Ym` workflow**.
An attachment is not evidence the agent invoked it in a call.

The historical 25-tool count comprised the original 21 plus four CRM tools.
The four subsequent voice tools bring the server total to 29:
`search_call_appointments`, `select_call_appointment`, `book_call_appointment`,
and `search_call_knowledge`. All four are attached to Avery, as are
`get_crm_case`, `record_crm_interaction`, `create_crm_follow_up`, and
`update_crm_follow_up`.

Eight server tools are absent from the agent attachments:

- `get_scheduling_handoff`
- `prepare_scheduling_handoff`
- `prepare_veteran_confirmation_request`
- `record_lifecycle_event`
- `record_option_selection`
- `record_veteran_confirmation`
- `validate_booking_preconditions`
- `validate_option_selection`

These belong to the legacy/restricted handoff and scheduling control path.
They should not be attached merely to make counts match. The current voice path
uses guarded selection and booking tools with independently enforced consent and
scope. No tools or workflow attachments were added or removed in this update.
Historical 25-tool evaluation scores remain historical; this inventory is not a
new 29-tool behavioral evaluation.

## Guideline change

The fresh IBM export had zero separate guideline entries. Eight reviewed entries
are defined in `deploy/ibm/orchestrate/avery-guidelines-v1.json`, covering natural
conversation, trusted identity/privacy, relevant MCP tool use, appointment facts,
consent/booking, grounded knowledge, human assistance, and CRM/after-call evidence.

The tool-use rule covers all attached authorized access/read/write capabilities
when relevant, not all tools on every call. It preserves prerequisites and denies
fallback to restricted legacy operations. The voice host owns spoken verification
and automatic after-call processing. No guideline can create identity or consent.

The candidate was constructed from a fresh private agent backup. IBM SDK guideline
schema validation passed; candidate comparison permits only the `guidelines` field
to change. Voice configuration, model, instructions, context variables, plugins,
and tools are preserved. The original private export remains in Codespace at
`/tmp/avery-guidelines-current-20261118.yaml` for rollback.

## Acceptance status

Import completed successfully. Fresh applied-export comparison and publication
status are recorded below after completion. This change does not claim a new
live voice rehearsal, new booking, or full behavioral regression result.

Fresh applied export verified eight exact guideline entries and only the guidelines field changed. All 22 attachments were unchanged. IBM returned: Successfully deployed agent veteran_access_agent_m64. No backend/frontend/voice-worker image was changed; no appointment or CRM record was created by these checks. Configuration validation and publication passed; behavioral voice regression remains unrun for this guideline revision.


Workflow-detach acceptance: fresh applied export exactly matched the prepared candidate, with 21 MCP tools, eight guidelines, and all other fields unchanged. IBM deployment completed successfully (exit 0). No new call, booking, CRM write, backend image or voice change was made. A new live voice regression was not run for this attachment removal.

