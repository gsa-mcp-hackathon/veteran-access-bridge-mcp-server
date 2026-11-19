# Phoenix tracing

Arize Phoenix can display traces, tool spans, prompts and latency **when an application has OpenTelemetry/OpenInference instrumentation and an export path**. Running Phoenix alone does not capture any agent calls.

```powershell
# Optional: local Phoenix server with Docker
# Review firewall and data-retention settings before exposing ports.
docker run --rm -p 6006:6006 -p 4317:4317 arizephoenix/phoenix:latest
# Open http://localhost:6006 and configure an OpenTelemetry exporter for the app.
```

For Python-based tracing, follow [Phoenix OpenInference setup](https://github.com/Arize-ai/phoenix/blob/main/.agents/skills/phoenix-tracing/references/setup-python.md); choose the instrumentor for the **actual framework** rather than installing an unrelated OpenAI instrumentor. Keep patient IDs, real PHI, secrets and tokens out of trace attributes. A Phoenix screenshot or trace-export artifact **must be collected separately** before claiming evaluated Phoenix results.

---

**Developer Guide:** [Overview](index.md) · [← DeepEval](deepeval.md) · [Release & evidence checklist →](release-checklist.md)
