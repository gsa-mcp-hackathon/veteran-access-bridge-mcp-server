# Security

Veteran Access Bridge is a hackathon prototype with strict synthetic-only boundaries.

## Boundaries

- Synthetic data only; do not use PHI or production patient data.
- Do not commit VA production credentials, API keys, private keys, tokens, or secrets.
- No real appointment booking or production scheduling transactions.
- The LLM must not diagnose, invent consults/referrals/authorizations, or independently determine Community Care eligibility.
- Human scheduler review remains authoritative for consequential scheduling actions.
- Browser clients must never receive privileged MCP or source-system credentials.
- Source provenance, freshness, stale-state handling, and partial source failures must remain explicit.

## Reporting

Do not place secrets, credentials, PHI, or sensitive patient information in GitHub issues. Report security concerns privately to the repository owner.
