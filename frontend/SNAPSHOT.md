# Companion browser frontend (snapshot)

This folder is a copy of the companion browser call center (`veteran-appointment-bridge`) at its release commit `166dd1a`, the revision used in the demonstration. It was copied on November 23, 2026 so the submission does not depend on a private repository.

**Changes from the original:** the IBM watsonx Orchestrate account and instance identifiers in `src/components/msa/avery-embedded-chat.tsx` are replaced with `<YOUR_ORCHESTRATE_ACCOUNT_ID>` and `<YOUR_ORCHESTRATE_INSTANCE_ID>` placeholders, and links to the private repositories were repointed to public copies or shown as plain text. No secrets were present; `.env.example` contains names only.

The frontend is optional for evaluating the MCP server. Its build and setup instructions are in [README.md](README.md); the Developer Guide's [browser call page](../docs/developer-guide/browser-call.md) explains how it connects to the backend.
