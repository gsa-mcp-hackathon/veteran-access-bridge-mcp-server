# Evaluation & Results

The results below come from **different checkpoints**. They must not be combined into a single pass rate.

| Date / checkpoint | Recorded outcome | Scope |
|---|---|---|
| November 15, 2026 | **1,337 passed, 19 skipped** | Backend regression at that release |
| November 16, 2026 | **1,380 passed, 19 skipped** | Linux regression |
| November 16, 2026 | **108/108** | MCP contract probes in 25-tool configuration |
| November 16, 2026 | **76/76** | Hostile-argument probes |
| November 16, 2026 | **261/261** | Scope and schema assertions; overlapping with other checks |
| November 16, 2026 | **PASS: one synthetic booking** | One appointment and one host CRM note independently persisted |
| November 18, 2026 | **1,624 passed, 19 skipped, 1 failed** | Windows documentation-review regression; Linux-only `os.O_NOFOLLOW` failure retained |

### Voice responsiveness

The successful November 16 controlled call recorded **4.879 seconds median first-audio latency**, maximum **13.720 seconds** across nine samples. This is one call—not a population-wide responsiveness benchmark.

### What these evaluations demonstrate

The test suite and probes support confidence in the implemented contracts, local fixtures, scope denial and specific synthetic transaction. They do not establish universal attack resistance, full production VA integration, production load performance or completed coverage of the broader 48-scenario test design.

### What remains open

Hosted DB concurrency, uncertain-write recovery, broader injection/poisoning/SSRF tests, dependency findings and final browser presentation checks need their own evidence. Earlier model-evaluator scoring is **not** a substitute for deterministic authorization checks.

**Next:** [Demo & quick start](demonstration.md) · [Security](security-governance.md)
