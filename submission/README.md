# For Judges — Veteran Access Bridge

**Start here.** Curated GSA MCP & SI Agent Hackathon materials. The **Python FastMCP server** is the primary deliverable; Avery is the synthetic voice demonstration client.

| Section | Judge's question |
|---|---|
| [01 · Problem and solution](01-problem-and-solution/README.md) | What challenge does the server address? |
| [02 · Architecture](02-architecture/README.md) | How does MCP connect tools and trusted services? |
| [03 · Demonstration](03-demonstration/README.md) | What functionality was actually demonstrated? |
| [04 · Evaluation](04-evaluation/README.md) | What passed, failed, or remains unverified? |
| [05 · Security](05-security/README.md) | How are permissions enforced and what are the limitations? |
| [06 · Reproduce](06-reproducibility/README.md) | How can I run safe synthetic tests? |

## Judge's quick route

1. **Watch:** [Recorded Avery demonstration](../docs/assets/avery-demo.mp4) and [walkthrough](../docs/demonstration.md).
2. **Inspect:** [Current MCP catalog](../docs/mcp-implementation.md) and [architecture](../docs/solution-architecture.md).
3. **Evaluate:** [Evaluation Command Center](../docs/evaluation/index.md), [29-tool scorecard](../docs/evaluation/per-tool.md) and [security findings](../docs/evaluation/security-adversarial.md).
4. **Reproduce:** [Local MCP server guide](../docs/developer-guide/local-mcp-server.md).

The [evidence manifest](evidence-manifest.json) identifies the source, date and limits of each reported result.

## Submission artifact status

| Artifact | Where judges can inspect it | Status |
|---|---|---|
| Source code and local tests | Repository `src/`, `eval/` and `tests/` | Included |
| MkDocs documentation | `docs/` and published GitHub Pages after merge | Review in PR #30 |
| Recorded demo | [Public video file](../docs/assets/avery-demo.mp4) | Included |
| Tool-level matrix | [29-tool index](04-evaluation/evidence/m64-per-tool-evidence.json) and [25-tool historical CSV](04-evaluation/evidence/historical-25-tool-coverage-20261116.csv) | Included with limitations |
| Security closeout | [Sanitized summary](05-security/evidence/m64-security-closeout-summary.md) | Included; 4 deployed PARTIAL |
| Final presentation (PowerPoint) | Separately maintained presentation | **Not yet copied into this repo** |
| Final evaluation document (DOCX/PDF) | Separately maintained report | **Not yet copied into this repo** |

The last two artifacts need version reconciliation, privacy review and deliberate inclusion. Their absence must not be presented as a finished judge package.

**Current reviewed configuration:** 29 registered tools, 21 attached to Avery, 8 excluded from the agent. The November 16 tool contract matrix covered an earlier 25-tool inventory. Local catalog-integrity remediation passed **48/48 focused checks**, not 48 deployed adversarial scenarios. S03/A21, S13/A23, S14 and S15 remain **PARTIAL** for deployed security acceptance.

**Publication boundary:** This public package includes sanitized summaries and local test matrices; no unredacted private IBM traces, patient details, passwords, tokens or identity factors. Historical and current evidence must not be pooled into one success rate.
