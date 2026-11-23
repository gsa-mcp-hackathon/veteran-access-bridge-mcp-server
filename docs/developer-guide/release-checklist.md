!!! info "Fresh-install evidence is distinct from historical release evidence"
    Use the [clean-room reproduction protocol](clean-room-reproducibility.md) before calling the full Avery cloud experience reproducible. The restricted-environment audit could not perform the cloud acceptance gates.

# Release & evidence checklist

- [ ] Record source SHA, Python version, environment and installed package versions.
- [ ] Confirm **read-only** Cardiology, Primary Care and unknown-case denial in local fixture mode.
- [ ] Run tests/probes in **new output directories**; retain failures and skip counts.
- [ ] Document *which* IBM toolkit, agent version and authorized sandbox were evaluated.
- [ ] Inspect PostgreSQL schema, RLS, migration version and provenance before describing RAG as deployed.
- [ ] Keep sandbox and Supabase credentials in approved secret storage—never in GitHub Pages or Markdown.
- [ ] Do not reuse consumed historical booking cases, claim production VA writes, or treat a generated sentence as a booking receipt.

[Reproducibility source guide](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/developer-guide/clean-room-reproducibility/) · [IBM CLI runbook](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/developer-guide/ibm-orchestrate/) · [Evaluation Results](../evaluation/index.md)

---

**Developer Guide:** [Overview](index.md) · [← Phoenix tracing](phoenix.md)
