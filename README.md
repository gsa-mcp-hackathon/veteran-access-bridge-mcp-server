# Veteran Access Bridge MCP Server

**Project author:** William Green

Veteran Access Bridge is a **Model Context Protocol (MCP) server for Veteran appointment scheduling**. It gives super intelligence (SI) applications tools to retrieve information from the VA Patient Health sandbox, look up VA facilities, search for eligible appointments, and request a simulated booking. The backend restricts patient-specific operations to the verified caller’s case and requires confirmation before saving an appointment.

The Primary Care demonstration shows the server in use. A Veteran calls through a browser and speaks with Avery, an IBM watsonx Orchestrate voice agent. A reviewer can follow the conversation alongside the MCP tool calls, see the chosen appointment, and inspect the confirmation that the booking was saved.

[Explore the architecture](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/solution-architecture/) · [Follow the demonstration](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/demonstration/) · [Explore evaluation results](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/evaluation/) · [Reproduce the local server](#reproduce-the-local-server)

**For judges** · [Submission package](for-judges/README.md) · [29-tool evaluation](docs/evaluation/per-tool.md) · [Evidence manifest](for-judges/evidence-manifest.json)

**For reviewers** · [Backend release contents](release/README.md) · [Run the local server](docs/developer-guide/local-mcp-server.md) · [Find a test](tests/README.md) · [Read the recorded results](docs/evaluation/reviewer-index.md)

## Why we built it

We chose routine Primary Care scheduling to explore how a Veteran could make a request in their own words and how a reviewer could verify what happened afterward. When someone says, “Monday works for me,” the system still has to establish which Monday, at which facility, whether the visit fits the slot, and whether the caller has authorized the booking.

The MCP server turns those decisions into tools an SI application can use. The scheduling service applies eligibility rules, the call session carries the verified identity, and a saved receipt gives the reviewer evidence beyond a spoken confirmation.

## GSA challenge alignment

**Primary category — Service “Read” Integration.** Avery can select an MCP tool to retrieve a patient-health summary from a VA government service in its sandbox environment. The server also exposes facility search and lookup tools.

The write path has a distinct destination. After the caller confirms, the project’s trusted booking service records a simulated appointment in Supabase and reads it back. After hang-up, the backend saves a CRM summary and generates a confirmation letter. Test records and appointment inventory stay within the demonstration environment. [GSA hackathon challenge and judging criteria](https://www.gsa.gov/super-intelligence/si-community-of-practice/events-and-training/mcp-server-and-si-agent-government-hackathon)

## What the MCP server does

| Scheduling task | Tool or operation | What the result establishes |
|---|---|---|
| Verify the caller | `verify_synthetic_identity` | The verification outcome belongs to the current call and case. |
| Retrieve patient context | `get_va_patient_health_sandbox_summary` | The agent receives a permitted summary for the verified test case. |
| Find a facility | `search_va_sandbox_health_facilities` | An application can query supported facility information. |
| Find eligible appointments | `search_call_appointments` | The caller can hear eligible options from the test inventory in local time. |
| Select an appointment | `select_call_appointment` and spoken readback | The caller’s choice is tied to a specific slot and can be corrected before booking. |
| Book after confirmation | Policy-checked write and independent readback | A receipt confirms the saved appointment. |

Tool counts depend on what is enabled. The default local release advertised **21 tools**. A separate evaluation enabled CRM and exercised **25 tools**. Each result below identifies the configuration or run it describes. [MCP implementation](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/mcp-implementation/)

## Architecture and data flow

| Component | Responsibility |
|---|---|
| Avery on IBM watsonx Orchestrate | Interprets the request and selects permitted MCP tools. |
| LiveKit voice worker | Connects speech from the browser call to its backend session. |
| Veteran Access Bridge MCP server | Validates inputs, enforces case scope, and returns structured results. |
| VA sandbox services | Supply supported government-service reads, including the patient-health summary. |
| Trusted booking service and Supabase | Check the selected slot and consent, save the simulated appointment, and verify it through readback. |

**Hang-up triggers after-call work.** For the verified booking shown in the demo, the host saved a CRM summary and generated a letter. The interface reports its delivery status as “Generated · Not sent.” This attribution matters when reading traces: an IBM-selected tool and a host-triggered record are different events. [Architecture walkthrough](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/solution-architecture/)

## Follow the recorded call

The **3-minute, 39-second** recording (the same call shown on presentation slides 10–11) follows one Primary Care request through after-call work.

| Time | What to look for |
|---|---|
| **2:00 — Patient-health read** | The activity panel names the patient-health MCP tool and attributes its selection to the IBM agent. |
| **3:12 — Verified booking** | The confirmed appointment card shows the selected Topeka visit in Central time. The scheduling panel reports a successful independent readback. |
| **3:36 — After-call work** | Wrap Up turns green. The reviewer can see the saved CRM note and generated confirmation letter. |

[Demonstration walkthrough](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/demonstration/)

## Evaluation methods and results

We asked three questions: **Did the server return the right information? Did the agent use the right tool? What did the backend actually save?**

| Question | Observed result | Method and scope |
|---|---|---|
| Can a client discover the server? | **21 tools advertised** | A fresh checkout started the installed server and listed its tools over standard input/output with default settings. |
| Does the scheduling logic handle unsuitable slots? | **5 of 5 checks passed** | Local Primary Care tests covered new and established patients, a slot that was too short, and unknown classification. |
| Do MCP answers match the expected results? | **16 of 16 gold answers matched** | Phoenix helped organize a local fixture evaluation of four tools using one known and one unknown case. Several questions checked different fields of the same response. |
| Did Avery use MCP appropriately in a recorded conversation? | **DeepEval score of 0.95** | The corrected run covered one conversation, two tasks, and three tool calls. It measures behavior on that trace. |
| Can an IBM-selected verification be traced to the backend? | **One linked verification receipt** | A separate hosted voice test distinguished the first host-invoked encounter lookup from IBM’s selection of the identity tool. |
| Did booking and wrap-up persist? | **One verified test appointment, a saved CRM note, and a generated letter** | A dated hosted acceptance run checked the resulting records. The final demo shows its own confirmation and wrap-up. |

[Gold questions and scored answers](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/for-judges/engineering-records/docs/evaluation/judge-review) · [DeepEval method and scoring notes](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/eval/deepeval) · [Verification trace](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/docs/evaluation/browser-identity-mcp-20261118.json) · [Booking and wrap-up evidence](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/docs/operations/voice-call-polish-booking-20261117.json)

## Security and adversarial evaluation

| What we tested | Observed result | Evidence boundary |
|---|---|---|
| **Unsafe inputs sent directly to MCP tools** | **76 of 76 argument checks passed** across 25 tools in the November 16 CRM-enabled configuration. The tested requests were rejected or produced safe negative results. Local fixture stores remained unchanged. | This was a local server test. It exercised neither a hosted database nor an agent responding to malicious instructions. [Server evaluation](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/docs/evaluation/server-wide-evaluation-20261116.md) |
| **Unauthorized caller requests** | Across **five restricted requests in three voice sessions**, the traces showed **zero MCP attempts during those requests**. All three sessions subsequently completed a permitted follow-up. | The traces establish what Avery invoked. The retained database audit covered different sessions, so database effects for these five requests remain unverified. [Voice evidence and reconciliation](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/for-judges/engineering-records/docs/evaluation/judge-review) |
| **Indirect prompt injection through tool results** | **Six cases prepared; execution pending.** | These cases cover untrusted instructions embedded in returned content. A result requires actual tool outputs and agent traces. No pass rate is reported. [Prepared cases](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/eval/deepeval/server_wide_injection_cases.json) |

[Security and governance walkthrough](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/security-governance/)

## Reproduce the local server

The commands below use the pinned backend release verified from a fresh clone. You need Git, Python 3.12, and uv. The default checks run without IBM, VA, LiveKit, Deepgram, or Supabase credentials.

**1. Install the verified release.**

```bash
git clone https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server.git
cd veteran-access-bridge-mcp-server
git rev-parse HEAD
uv sync --locked --group dev
```

**2. Discover the tools.** This command starts the server, connects an MCP client over standard input/output, lists the available tools, and exits. Expect **21 tools** in the default configuration.

```bash
uv run --no-sync python scripts/list_local_mcp_tools.py
```

**3. Run the Primary Care scheduling checks.** Expect **5 passed**.

```bash
uv run --no-sync pytest -q tests/test_m6_2_primary_care_scenarios.py
```

**4. Run the complete backend test directory.** The test index highlights the seven Primary Care suites. Hosted and optional-dependency checks may skip in a local run.

```bash
uv run --no-sync pytest -q tests
```

[Developer guide](https://gsa-mcp-hackathon.github.io/veteran-access-bridge-mcp-server/developer-guide/) · [Pinned release quickstart](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/blob/main/for-judges/engineering-records/QUICKSTART.md)

## Release references

| Reference | Version | What it identifies |
|---|---|---|
| Reproducible backend | [`ea0880f`](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server) | Server source, corrected dependency lockfile, discovery script, and evaluation instructions. |
| Deployed IBM backend | `293fc8c`, revision `00062` | IBM reported this revision serving 100% of backend traffic on November 19, 2026. Its application code matches the reproducible release. |
| Companion browser frontend | [`166dd1a`](https://github.com/gsa-mcp-hackathon/veteran-access-bridge-mcp-server/tree/main/frontend) | Source and build instructions for the browser call center. |

Veteran Access Bridge is an independent hackathon prototype. It uses test patient records, demonstration appointment inventory, and a project-managed test database.
