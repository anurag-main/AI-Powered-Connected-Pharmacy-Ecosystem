# Documentation Index

Every agent and every major feature leaves behind a document explaining **how the code
actually works** — from `main.py` through the database and back to the response.

```text
docs/
├── README.md                     this index
├── architecture.md               the current implemented system
│
├── agents/
│   └── expiry_risk_agent.md      Expiry Risk Agent
│
├── features/                     (empty — see "Not yet written" below)
│
├── business_queries.md           BI agent structured queries, date semantics, memory
├── observability.md              request_id / run_id / thread_id, events, LangSmith
├── testing.md                    test foundation, fixtures, golden sets
│
├── 00_project_architecture.md    early architecture notes (superseded by architecture.md)
├── 01_middleware_working.md      middleware walkthrough
├── 02_billing_agent.md           Billing agent
├── 03_reorder_agent.md           Reorder agent
├── 04_bi_agent_qa_report.md      BI agent QA findings
└── 05_architecture_audit.md      full repository audit, sections A-G
```

---

## Start here

| I want to… | Read |
|---|---|
| Understand the whole system as it stands | [`architecture.md`](architecture.md) |
| Understand one agent end to end | the file in [`agents/`](agents/) |
| Know what is broken or missing | [`05_architecture_audit.md`](05_architecture_audit.md) |
| Run or extend the tests | [`testing.md`](testing.md) |
| Debug a request | [`observability.md`](observability.md), then the agent's §25 |

---

## Agents

| Agent | Status | Document |
|---|---|---|
| Expiry Risk | Documented to the standard, backend **and** frontend | [`agents/expiry_risk_agent.md`](agents/expiry_risk_agent.md) |
| Business Intelligence | Partial — [`business_queries.md`](business_queries.md), [`04_bi_agent_qa_report.md`](04_bi_agent_qa_report.md) | not yet at the standard |
| Reorder | Partial — [`03_reorder_agent.md`](03_reorder_agent.md) | not yet at the standard |
| Billing | Partial — [`02_billing_agent.md`](02_billing_agent.md) | frozen; not being extended |
| Tool Agent (experimental) | **Undocumented and untested** | — |

## Features

| Feature | Status | Document |
|---|---|---|
| Observability | Documented | [`observability.md`](observability.md) |
| Testing + evaluation | Documented | [`testing.md`](testing.md) |
| Memory (ChromaDB) | Partial, inside [`business_queries.md`](business_queries.md) | `features/memory.md` not yet written |

### Not yet written

`features/memory.md` · `features/authentication.md` · `features/rbac.md` ·
`features/rag.md` — the last three because the code does not exist yet. A document is
written **with** the feature, not reconstructed afterwards.

---

## The standard

Every new agent or major feature gets its own document, at code level, matching the
actual implementation — actual file names, actual class and function names, actual
routes. It must let someone who has never seen the project trace:

```text
main.py -> API -> service -> agent -> LangGraph -> node -> tool -> repository -> database
        -> repository -> service -> agent -> LLM -> API -> frontend
```

Required sections: overview · business use case · high-level architecture ·
round-trip data flow · file-by-file flow · **frontend architecture · frontend
file-by-file flow · complete user-to-database round trip** · entry point · request
schema · LangGraph flow · agent state · tool flow · database flow · SQL vs Python vs
LLM · LLM flow · what the LLM does and does not do · observability · error flow ·
test flow · evaluation · security · performance · example request · how to debug ·
common failure modes · future extensions · interview explanation.

Three diagrams minimum: system architecture, agent/graph flow, complete round trip.
Mermaid, so they stay editable.

**A feature is not done until:**

```text
BACKEND   [ ] Logic  [ ] Agent  [ ] Tool  [ ] Repository  [ ] API  [ ] Tests  [ ] Evaluation
FRONTEND  [ ] Page   [ ] Components  [ ] API client  [ ] Loading  [ ] Error  [ ] Empty
          [ ] Real API integration
SYSTEM    [ ] End-to-end verified  [ ] Observability  [ ] Document
          [ ] architecture.md updated  [ ] This index updated
```

Every milestone runs two tracks — backend and frontend — and finishes with a working
product feature, not backend code waiting for a UI.

Two rules that matter more than the rest:

1. **Document what the code does, not what it was supposed to do.** Inspect the files
   before writing. Use the real names.
2. **Never claim something that is not there.** If auth is missing, say it is missing.
   If a benchmark was not run, say "not yet measured."
