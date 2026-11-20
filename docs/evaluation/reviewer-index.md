# Review the Primary Care evidence

Start with one question in the gold matrix. Read across the row from the caller's scheduling question to the fixture, MCP tool, expected fields, observed fields and verdict. For example, the first row expects the encounter tool to identify an established patient. A match shows that the tool returned that field for that fixture. Agent tool selection and live voice quality each require separate evidence.

| Evidence | What you can inspect |
| --- | --- |
| **Recorded · November 19** | [Gold question matrix (CSV)](evidence/primary-care-mcp-gold.csv) · 16 questions with their expected and observed answers. |
| **Recorded · November 19** | [Control results (CSV)](evidence/primary-care-control-suites.csv) · 135 checks across six suites. Each row gives the historical denominator and number passed. |
| **Run locally** | [Start the server and run the tests](../developer-guide/local-mcp-server.md). Five Primary Care scenario tests exercise the fixture. Six additional suites cover consent, booking, scheduling fields and CRM receipts. |
| **Hosted evidence** | [Validation and agent evidence](validation-agent.md) identifies the environment used for each result and the remaining gaps. |
| **Security evidence** | [Security and adversarial evaluation](security-adversarial.md) describes the tested boundaries and outstanding work. |

Record the submission commit with any new run. The gold matrix, automated control checks and live call each answer a different question and retain their own denominator.

### Rerun the 16 gold questions

After [installing the local server](../developer-guide/local-mcp-server.md), run `uv run --no-sync python eval/primary-care/run_gold.py` from the repository root. Each line identifies the question and MCP tool. Compare the final count with the recorded gold matrix above.
