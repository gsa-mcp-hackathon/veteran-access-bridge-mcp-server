# MCP Server Validation

**Checkpoint:** November 15–16, 2026 · **Goal:** validate tool contracts, scoped inputs, explicit denials and backend reliability.

<div class="ev-meta"><span>Runner: local Python tests and in-process MCP probes</span><span>Model: none — deterministic assertions</span><span>Transport: local fixture mode</span><span>Result: bounded checks passed</span></div>

## Contract → execution → result

<div class="eval-three"><div><b>01 · Design</b><p>21/25/29 tool configurations, schemas, valid and invalid inputs</p></div><div><b>02 · Execute</b><p>Python unit/integration tests, MCP contract probes and negative arguments</p></div><div><b>03 · Analyze</b><p>Scope denial, schema assertions, and identified platform limitations</p></div></div>

## Dated evidence

| Run | Result | Boundary |
|---|---:|---|
| November 15 backend regression | 1,337 passed; 19 skipped | Earlier release |
| November 16 Linux regression | 1,380 passed; 19 skipped | Separate Linux run |
| November 16 contract probes | 108/108 | Recorded 25-tool configuration |
| November 16 hostile-argument probes | 76/76 | Input/argument checks, not a prompt-injection certification |
| November 16 scope/schema | 261/261 | Overlapping assertions; do not sum with probes |
| November 18 local Windows review | 1,624 passed; 19 skipped; **one failed** | Linux-only `os.O_NOFOLLOW` unsupported on Windows |

## Sample check

```json
{"name":"get_scheduling_encounter","arguments":{"case_id":"DEMO-PC-5000999-001"}}
```

The fixture is read-only. An unknown case returns a denial/error rather than invented scheduling facts. A passing schema probe does not confirm a live booking.

**Evidence:** [November 16 tool-wide report](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/server-wide-evaluation-20261116.md) · [Per-tool coverage](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/docs/evaluation/server-wide-tool-coverage-20261116.md) · [MCP contract probe source](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/eval/probe_mcp_contracts.py) · [Argument probe source](https://github.com/wbgreen0405/veteran-access-bridge/blob/5b6cd072f23b4d4edce2e19c4f75faa774c87988/eval/probe_mcp_adversarial.py)

**Next:** [Phoenix & Gold Questions](gold-phoenix.md)
