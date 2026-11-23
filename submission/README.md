# For Judges — Veteran Access Bridge

**Start here.** Curated materials for the GSA MCP Server and SI Agent Government Hackathon. The **Python FastMCP server** is the primary deliverable; Avery is the synthetic voice demonstration client.

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
3. **Evaluate:** [Evaluation Command Center](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/evaluation/), [inline Per-Tool scorecard](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/evaluation/#panel-tools) and [security findings](../docs/evaluation/security-adversarial.md).
4. **Reproduce:** [Local MCP server guide](../docs/developer-guide/local-mcp-server.md).

The [evidence manifest](evidence-manifest.json) identifies the source, date and limits of each reported result.

## Submission artifact status

| Artifact | Where judges can inspect it | Status |
|---|---|---|
| Source code and local tests | Repository `src/`, `eval/` and `tests/` | Included |
| MkDocs documentation | `docs/` and published [GitHub Pages](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/) | Published documentation |
| Recorded demo (MP4, 3:39) | [Public video file](../docs/assets/avery-demo.mp4); same call as presentation slides 10–11 | Included |
| Tool-level matrix | [29-tool index](04-evaluation/evidence/m64-per-tool-evidence.json) and [25-tool historical CSV](04-evaluation/evidence/historical-25-tool-coverage-20261116.csv) | Included with limitations |
| Security closeout | [Sanitized summary](05-security/evidence/m64-security-closeout-summary.md) | Included; 4 deployed PARTIAL |
| Final presentation (PowerPoint, 20 slides) | [deliverables/Veteran-Access-Bridge-Presentation.pptx](deliverables/Veteran-Access-Bridge-Presentation.pptx) | Included |
| Final evaluation report (Word) | [deliverables/Veteran-Access-Bridge-Evaluation-Report.docx](deliverables/Veteran-Access-Bridge-Evaluation-Report.docx) | Included |
| Submission links sheet (PDF) | [deliverables/Veteran-Access-Bridge-Submission-Links.pdf](deliverables/Veteran-Access-Bridge-Submission-Links.pdf) | Included |

**Current reviewed configuration:** 29 registered tools, 21 attached to Avery, 8 excluded from the agent. The November 16 tool contract matrix covered an earlier 25-tool inventory; on November 21 the contract probes (**126/126**) and hostile-argument probes (**86/86**) covered all 29 tools. Local catalog-integrity remediation passed **48/48 focused checks** (November 22), not 48 deployed adversarial scenarios. S03/A21, S13/A23, S14 and S15 remain **PARTIAL** for deployed security acceptance.

**Publication boundary:** This public package includes sanitized summaries and local test matrices; no unredacted private IBM traces, patient details, passwords, tokens or identity factors. Historical and current evidence must not be pooled into one success rate.

## What this package includes

- Six numbered judge sections, one index and a traceable results manifest
- A public recording of the final demonstration call and reproducible local MCP instructions
- Historical 25-tool contract and hostile-argument evidence, copied with provenance
- An inline 29-tool inventory and test scorecard, with historical and current results labeled separately
- November 21–22 evaluation and remediation findings, including four PARTIAL deployed security outcomes
- The final presentation and evaluation report (`deliverables/`)
- Public copies of the engineering records the documentation cites ([engineering records](engineering-records/README.md), [frontend snapshot](../frontend/SNAPSHOT.md))

## Known limitations (not claimed)

- A full deployed M6.4 per-tool IBM evaluation has not been run, so this package reports no per-tool IBM pass rate, latency p95 or repeatability (Pass³) score.
- Four deployed security items (S03/A21, S13/A23, S14, S15) remain PARTIAL, and no production security signoff is claimed.
- All data is synthetic; no production VA system or booking was used.

The published site is the easy-to-read front door; the versioned files here are the evidence record.
