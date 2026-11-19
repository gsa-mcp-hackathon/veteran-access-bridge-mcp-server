# DeepEval

DeepEval is a **separate agent-quality check**, not permission to bypass backend validation. Project history records a corrected **0.95** score on a bounded two-task, three-call read evaluation; an earlier 0.0 adapter run had zero evaluable tasks and cannot be interpreted as failure.

```powershell
# In an isolated evaluation environment
python -m pip install deepeval
deepeval --help
deepeval test run --help
# Run ONLY an actual reviewed DeepEval test file from the repository:
deepeval test run PATH_TO_REVIEWED_TEST_FILE.py
```

A runnable test must supply its own `LLMTestCase` (inputs, observed actual output and reference/context), configured metrics and any authorized evaluator-model credentials. This documentation **does not invent a project test-file path** or claim the above CLI has been rerun on the current deployment. See [DeepEval CLI](https://deepeval.com/docs/command-line-interface) and [quickstart](https://deepeval.com/docs/getting-started).

---

**Developer Guide:** [Overview](index.md) · [← IBM watsonx Orchestrate](ibm-orchestrate.md) · [Phoenix tracing →](phoenix.md)
