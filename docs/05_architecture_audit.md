# 05 — Architecture & Repository Audit

> **What this is:** a pre-implementation audit of the whole repository against
> `AI_Pharma_15LPA_Roadmap.md`. It establishes the honest baseline before any new agent is
> built — what actually exists, what is broken, and the order in which to fix it.
>
> **Method:** full inspection of `pharmacy-core-backend/app/**`, `pharmacy-frontend/**`,
> `migrations/`, `scripts/`, `.env`, `requirements.txt`, plus repo-wide searches for tests,
> Docker, CI, auth, Redis, logging and LangSmith configuration. Nothing here is assumed —
> every claim cites a file, a line, or a search that returned zero hits.
>
> **No code was changed in this pass.**
>
> Date: 2026-09-06 · Branch `main` · HEAD `81c88be`

---

## Table of Contents

- [A. Current Architecture](#a-current-architecture)
- [B. Current Agent Inventory](#b-current-agent-inventory)
- [C. Roadmap Gap Analysis](#c-roadmap-gap-analysis)
- [D. Critical Existing Problems](#d-critical-existing-problems-prioritized)
- [E. Current Architecture vs Target Architecture](#e-current-architecture-vs-target-architecture)
- [F. Recommended Execution Plan](#f-recommended-execution-plan--first-8-milestones)
- [G. Open Decisions](#g-open-decisions)

---

## A. Current Architecture

| Component | Status | Evidence |
|---|---|---|
| **Frontend** | Next.js 16 Pages Router, JS only, 4 pages (`index`, `medicines`, `sales`, `reorder`). **No BI/chat UI at all** | [pharmacy-frontend/pages/](../pharmacy-frontend/pages/); grep for `business`/`analyze` in `src/lib/api.js` + all pages → **zero hits** |
| **Backend** | FastAPI, 5 routers, clean Router → Service → Repository layering | [app/main.py:57-64](../pharmacy-core-backend/app/main.py#L57-L64) |
| **Database** | MySQL 8 + SQLAlchemy 2.0, 10 models, 5 Alembic migrations | [app/models/](../pharmacy-core-backend/app/models/), [migrations/versions/](../pharmacy-core-backend/migrations/versions/) |
| **Redis** | ❌ **Does not exist.** Not in `requirements.txt`, not in code | grep `redis` → 1 hit, a comment in [medicine_repository.py:26](../pharmacy-core-backend/app/repositories/medicine_repository.py#L26) |
| **AI Gateway** | ❌ No gateway. Services call graphs directly; no routing, budget, or model-selection layer | [business_service.py:33](../pharmacy-core-backend/app/services/business_service.py#L33) |
| **LLM access** | Single `@lru_cache` client, provider switch via `LLM_PROVIDER`. No fallback, no model routing, no cost/token tracking | [app/ai/llm.py:69-84](../pharmacy-core-backend/app/ai/llm.py#L69-L84) |
| **Agents** | 3 agents, 7 compiled graphs (Billing ×4, Reorder ×1, BI ×1, Tool-calling ×1) | [app/ai/graphs/](../pharmacy-core-backend/app/ai/graphs/) |
| **LangGraph** | Real usage: `StateGraph`, `MessagesState`, conditional edges, `MemorySaver`, `ToolNode`. Solid | [business_graph.py](../pharmacy-core-backend/app/ai/graphs/business_graph.py) |
| **RAG** | ❌ **No knowledge RAG.** ChromaDB exists but serves *only* agent memory. No corpus, chunking, retriever, reranker, or citations | [chroma_store.py:16](../pharmacy-core-backend/app/ai/memory/chroma_store.py#L16) — one collection, `long_term_memory` |
| **Memory** | Short-term: `MemorySaver` (in-process). Long-term: Chroma, **scoped by `thread_id`** | [memory_repository.py:34,56](../pharmacy-core-backend/app/ai/memory/memory_repository.py#L34) |
| **Tools** | 5 `@tool` metric functions, **all zero-argument** | [business_tools.py:38,54,69,84,99](../pharmacy-core-backend/app/ai/tools/business_tools.py#L38) |
| **Authentication** | ❌ **None.** Zero JWT/bcrypt/OAuth references in the entire codebase | grep `jwt\|bcrypt\|oauth\|get_current` → 0 hits |
| **Authorization / RBAC** | ❌ None. No user table, no roles, no permission checks | no `users` model exists |
| **Observability** | ❌ **Effectively off.** `.env` has `LANGCHAIN_API_KEY` + `LANGCHAIN_PROJECT` but **`LANGCHAIN_TRACING_V2` is absent** → LangChain does not trace. No `logging` module anywhere; 10 node files use bare `print()` | grep `LANGSMITH\|LANGCHAIN_TRACING\|import logging\|logger\.` across `app/` → **0 hits** |
| **Deployment** | ❌ None. No Dockerfile, no docker-compose, no `.github/`, no CI config | repo-wide find → 0 hits |
| **Tests** | ❌ **Zero.** No `tests/`, no `test_*.py`, no `conftest.py`, no pytest in `requirements.txt`. Only 2 manual smoke scripts | [scripts/](../pharmacy-core-backend/scripts/) |

> **Correction to `docs/04_bi_agent_qa_report.md`:** it stated "LangSmith environment variables
> present." That is only half true — the *credentials* are present but the *enable* flag
> (`LANGCHAIN_TRACING_V2`) is not, so tracing is almost certainly not running at all.
> Observability is at zero, not at "configured but unverified."

---

## B. Current Agent Inventory

| Agent | Exists? | Location | Purpose | Quality | Problems |
|---|---|---|---|---|---|
| **Billing** | ✅ Yes | `ai/graphs/billing_graph.py`, 5 nodes | Free text → FEFO → priced atomic sale | **Good.** 4 graph variants from 5 nodes; quote/confirm split; server-side pricing; atomic 4-table write | Roadmap says deprioritize. Not an AI-value differentiator. No tests. |
| **Voice matcher** (sub-agent) | ✅ Yes | `ai/matching.py`, `fetch_candidates`, `confidence_reflector` | rapidfuzz shortlist + LLM confirm + confidence gate | **Good pattern** — genuine HITL escalation | Coupled to billing; no eval set for match accuracy |
| **Smart Reorder** | ✅ Yes | `ai/graphs/reorder_graph.py`, 3 nodes | Stock vs velocity → proposals, LLM judges 0-sales items | **Good design.** Pure-math tools, one LLM judgment, idempotent approve, memory of past approvals | Lead time + safety are hardcoded constants ([decide_reorders.py:26-27](../pharmacy-core-backend/app/ai/nodes/decide_reorders.py#L26-L27)); no forecast input; no tests; no eval |
| **Business Intelligence** | ✅ Yes | `ai/graphs/business_graph.py`, 8 nodes | Plan → parallel fetch → analyze → reflect → memory | **Architecturally the best, functionally the weakest.** Real planning, capped reflection, parallel tools, dual memory | Date-blind, aggregate-only, broken cross-session memory, no UI, `errors`/`execution_time_ms`/`agent_version` declared in state but **never written by any node** |
| **Native tool-calling** | ✅ Yes | `ai/graphs/business_tool_graph.py` | Same 5 tools via `ToolNode` + `tools_condition` | Works, useful as a comparison artifact | **Duplicates the whole tool path.** Two registries, two execution paths, no checkpointer, no memory, no tests |
| Expiry Risk | ❌ | — | — | — | Roadmap priority 2 |
| Forecast | ❌ | — | — | — | Roadmap priority 3 |
| Inventory Risk | ❌ | — | — | — | Roadmap priority 4 |
| Supplier Risk | ❌ | — | — | — | Roadmap priority 5 |
| Procurement | ❌ | — | — | — | Roadmap priority 6 |
| Supervisor | ❌ | — | — | — | Roadmap priority 7 |
| Pharma Knowledge RAG | ❌ | — | — | — | Roadmap priority 8 |
| Quality / Deviation | ❌ | — | — | — | Roadmap priority 9 |

---

## C. Roadmap Gap Analysis

| Roadmap Item | Status | Evidence | Gap | Priority |
|---|---|---|---|---|
| **Positioning as Ops Intelligence Platform** | PARTIAL | Billing is the only frontend flow; BI agent has no UI | Product framing contradicted by the actual UI | P1 |
| **Phase 0 — Architecture cleanup** | NOT STARTED | Two parallel tool paths; no agent interface contract; no shared state convention; no tool registry with permissions; no approval model beyond `reorder_requests` | Needs a baseline before agents multiply | **P0** |
| **Phase 1 — Fix BI: user/business identity** | BROKEN | `save_memory`/`search_memories` filter on `thread_id` ([memory_repository.py:34,56](../pharmacy-core-backend/app/ai/memory/memory_repository.py#L34)) | No identity exists independent of conversation | **P0** |
| **Phase 1 — Date filtering** | NOT STARTED | `BusinessRepository` — 5 methods, **zero date parameters**; tools are zero-arg | Every "last month" question silently returns all-time | **P0** |
| **Phase 1 — Grouping / ranking / top-N / comparison / trend** | NOT STARTED | No `GROUP BY`, no `ORDER BY … LIMIT` in `business_repository.py` | "Top sellers", "which supplier", "which grew most" are structurally unanswerable | **P0** |
| **Phase 1 — Memory confidence gate** | NOT STARTED | `memory_persistor` loops and saves unconditionally ([memory_persistor.py:35-40](../pharmacy-core-backend/app/ai/nodes/memory_persistor.py#L35)) | Low-confidence junk persists as truth | P1 |
| **Phase 1 — Memory dedup** | NOT STARTED | `save_memory` always calls `add_documents` | Vector store bloat | P1 |
| **Phase 1 — Refusal behaviour** | PARTIAL | Fixed in `cd04005` + `6a555da`, prompt-level only, **never re-tested** | No regression test proves it holds | P1 |
| **Phase 1 — Evaluation cases** | NOT STARTED | Zero test files repo-wide | The exit condition ("passes the regression suite") is unmeasurable | **P0** |
| **Phase 2 — Expiry Risk Agent** | NOT STARTED | `get_expiry_summary` returns count + total only, no batch list, no value-at-risk ranking | Full agent missing | P2 |
| **Phase 3 — Forecast Agent** | NOT STARTED | No time-series code, no model, no metrics | Full agent missing | P3 |
| **Phase 4–6 — Inventory / Supplier / Procurement** | NOT STARTED | — | Full agents missing | P4 |
| **Phase 7 — Supervisor** | NOT STARTED | No routing node, no `handoff_count` | Blocked on specialists existing | P4 |
| **Phase 8 — Production RAG** | NOT STARTED | Chroma used only for memory; no corpus/chunking/retriever/citations/eval | The single highest-demand skill is absent | P3 |
| **Phase 10 — Security / RBAC** | NOT STARTED | Zero auth code; every endpoint is public | Also blocks real `user_id` for memory | P2 |
| **Phase 11 — Evaluation** | NOT STARTED | No eval harness, no LLM-as-judge, no golden set | — | P1 |
| **Phase 11 — Observability** | BROKEN | Keys in `.env` but no `LANGCHAIN_TRACING_V2`; no logging module; `print()` in 10 files | Believed working, actually off | **P0** |
| **Phase 12 — Docker / CI-CD** | NOT STARTED | No Dockerfile, no compose, no `.github/` | — | P4 |
| **Phase 13 — Cloud deployment** | NOT STARTED | — | — | P5 |
| **Phase 14 — MCP** | NOT STARTED | — | — | P5 |
| **HITL / approval / audit** | PARTIAL | Only `reorder_requests`; no generic approval entity, no audit log | Needed before any agent proposes a PO | P2 |
| **Bounded loops** | DONE | `MAX_REFLECTIONS = 2`, enforced ([business_graph.py:44](../pharmacy-core-backend/app/ai/graphs/business_graph.py#L44)) | Extend to handoffs/tool calls later | ✅ |
| **Structured outputs** | DONE | `with_structured_output` everywhere; Pydantic in `ai/schemas/` | — | ✅ |
| **Deterministic-first** | DONE | `reorder_tools.py` pure fns; `compute_pricing` Decimal maths | Hold this line | ✅ |
| **Repository owns DB access** | DONE | No raw SQL in nodes; sessions opened in nodes/tools, SQL stays in repos | Minor: session lifecycle lives in the tool layer | ✅ |

**Status key:** DONE · PARTIAL · NOT STARTED · BROKEN. Nothing is marked DONE merely because
files exist — DONE means the behaviour was verified in the code path that actually runs.

---

## D. Critical Existing Problems (prioritized)

### 🔴 P0 — Blocks everything downstream

1. **Zero automated tests.** No pytest, no fixtures, no test DB. Roadmap Rule 6 and every phase
   exit condition are unverifiable. Any refactor from here is unsafe.
2. **Observability is off, not "unverified."** Missing `LANGCHAIN_TRACING_V2=true`; no `logging`
   config; `print()` as the logging strategy. The question *"show me a trace"* has no answer today.
3. **BI repository is aggregate-only and date-blind.** 5 fixed methods, no parameters. This is the
   root cause of B2 (hallucinated period fact), B3 and B10 — a prompt fix cannot repair a
   data-layer gap.
4. **Long-term memory is thread-scoped** → cross-session recall is architecturally impossible, not
   buggy. Needs a `user_id`/`business_id`, which in turn wants auth.

### 🟠 P1 — Correctness & credibility

5. **Dead state fields.** `errors`, `execution_time_ms`, `agent_version` are declared in
   `BusinessState` but written by no node; the service silently substitutes defaults. Also
   `errors: list[str]` has **no reducer**, so concurrent writes overwrite rather than append
   (`BillingState` gets this right — the two states are inconsistent).
6. **Duplicated tool paths.** `TOOL_REGISTRY` + `get_business_metrics` (fetcher) *and* `@tool` +
   `ToolNode` (tool-agent graph) over the same 5 functions. Two sources of truth; the code
   comments literally say "Temporary."
7. **No memory write gate or dedup** — a hallucinated fact becomes permanent ground truth.
8. **The flagship agent has no UI.** The BI agent is the project's best work and is unreachable
   from the frontend.
9. **Reorder constants are fake business logic.** `DEFAULT_LEAD_TIME_DAYS = 3`,
   `DEFAULT_SAFETY_DAYS = 2` hardcoded — no per-supplier lead time, no demand variance.

### 🟡 P2 — Production shape

10. **No auth, no RBAC, no rate limiting, no cost controls.** Every endpoint is public; an
    unauthenticated caller can burn OpenAI credit through `/business/analyze`.
11. **Both memory stores are single-process/local-disk** — `MemorySaver` dies on restart, Chroma is
    a local directory.
12. **No generic approval/audit model.** HITL exists only as a bespoke `reorder_requests` table.
13. **No LLM failure handling.** `get_llm()` is `lru_cache`d with no retry, no fallback provider,
    no circuit breaker. If the provider 500s, the agent 500s.
14. **`.env.example` is stale** — documents only `DATABASE_URL`, omits `LLM_PROVIDER`,
    `OPENAI_API_KEY`, `LANGCHAIN_*`. A fresh clone cannot boot the AI layer.
15. **`LLM_PROVIDER` defaults to `"nvidia"`** ([config.py:41](../pharmacy-core-backend/app/ai/config.py#L41))
    while all docs say OpenAI is active — a missing env var silently changes provider.

### 🟢 P3 — Performance / cost

16. **No caching.** Every BI question re-runs 3–5 LLM calls and 5 SQL aggregates, even for an
    identical repeat question.
17. **The three memory nodes run on every turn** — `memory_retriever`, `memory_extractor` and
    `memory_persistor` add 2 extra LLM calls and 2 vector operations per question, unconditionally.

---

## E. Current Architecture vs Target Architecture

```text
CURRENT
├── Next.js (billing-only UI) ──► FastAPI (public, unauthenticated)
│                                     ├── Billing agent (good, deprioritized)
│                                     ├── Reorder agent (good, hardcoded constants)
│                                     └── BI agent (best design, aggregate-only data)
│                                           └── Chroma = memory only (thread-scoped)
└── MySQL. No tests · No traces · No auth · No Redis · No Docker · No CI · No RAG

        ↓ PROBLEMS

  1. Cannot prove anything works        → no tests, no evals
  2. Cannot show how anything works     → tracing flag absent
  3. Data layer can't answer real Qs    → no dates, no grouping, no ranking
  4. Memory can't cross sessions        → no identity independent of thread_id
  5. Product says "Ops Intelligence"    → UI says "billing app"
  6. Two tool registries                → no single source of truth
  7. Anyone can spend the LLM budget    → no auth, no rate limit, no cost cap

        ↓ TARGET

  Next.js (Ops dashboard + AI chat + Approval Center + Trace view)
        │
        ▼
  FastAPI Gateway ── JWT + RBAC + rate limit ── Redis (cache / limits / short-term state)
        │
        ├── Pharma Core APIs (deterministic: billing, catalogue, stock)
        │
        └── AI Gateway (model routing · budget · fallback · trace context)
                  │
                  ▼
            SUPERVISOR (structured routing · MAX_HANDOFFS · tool permissions)
                  │
     ┌────────┬───┴────┬──────────┬──────────┬─────────┐
  Inventory  Forecast  Procure  Supplier   Quality    BI
     └────────┴────────┴──────────┴──────────┴─────────┘
                  │                          │
             RAG Agent (corpus + citations + eval)
                  │
          Human Approval Layer ──► Audit Log
                  │
        LangSmith traces + eval suite + regression gate in CI
```

**Why each change:**

| Change | Why |
|---|---|
| Parameterized repository (dates, grouping, ranking) | Without it, every "period" or "top-N" answer is a fabrication — no prompt fixes that |
| Identity (`user_id`/`business_id`) split from `thread_id` | The one change that makes "long-term memory" true rather than a label |
| Tests + eval harness first | Roadmap Rules 6 and 11; also the only safe way to refactor the tool duplication |
| Turn tracing on properly | Rule 7; and it is the artifact that makes every interview answer demonstrable |
| One tool registry with declared permissions | Prerequisite for the Supervisor — it must be able to deny a tool to an agent |
| Generic approval + audit entities | Prerequisite for the Procurement/Quality agents, which propose real-money actions |
| Auth before Redis/Docker | Supplies the identity that memory needs; also stops open LLM spend |

---

## F. Recommended Execution Plan — first 8 milestones

Sequenced so each milestone unblocks the next.

> **Deliberate deviation from roadmap §38, stated per Rule 16.** §38 places Evaluation at 10 and
> Observability at 11, after six new agents. This plan pulls a *minimal* version of both to the
> front, because §30 Phase 1's own exit condition is *"BI Agent passes the defined regression
> suite"* — a suite that does not exist. Building five more agents on an untested, untraced base
> means five agents that cannot be proven or debugged. The full eval/observability build-out stays
> at positions 10–11; only the harness moves up.

| # | Milestone | Why now | Size |
|---|---|---|---|
| **1** | **Test + eval harness** — pytest, test-DB fixtures, FastAPI `TestClient`, a `fake_llm` fixture, and one golden-question set for the BI agent. No behaviour change. | Nothing below is verifiable without it. Makes every later refactor safe. | S–M |
| **2** | **Turn observability on properly** — `LANGCHAIN_TRACING_V2`, structured `logging` config, request/run id propagated through nodes, replace the 10 `print()` sites, fix `.env.example`. | Cheap, high interview value, and traces are needed to debug milestones 3–5. | S |
| **3** | **Phase 0 cleanup** — collapse the two tool paths into one registry with typed args + declared permissions; add reducers and remove dead fields on `BusinessState`; define the agent interface contract the other agents will implement. | Prevents copying the duplication into six new agents. Prerequisite for the Supervisor. | M |
| **4** | **BI data layer V2** — date-range, grouping, ranking, top-N and period-comparison in `BusinessRepository`; give the 5 tools real typed parameters. | Fixes B2/B3/B10 at the root. Turns the BI agent from demo into genuinely useful. | M–L |
| **5** | **Identity + memory V2** — introduce `user_id`/`business_id`, scope memory to it, add a confidence gate and semantic dedup on write. | Fixes B1/B4/B5. Memory becomes real. | M |
| **6** | **BI regression suite green** — eval cases for milestones 4–5 against the harness from 1, including the refusal/off-topic cases fixed but never re-tested. | This is roadmap **Phase 1's actual exit condition**. Only now is Phase 1 done. | M |
| **7** | **Minimal auth (JWT + bcrypt + 2 roles) + rate limit** — pulled forward from Phase 10. | It *supplies* the `user_id` milestone 5 needs, and stops unauthenticated LLM spend. Doing it later means redoing 5. | M |
| **8** | **Expiry Risk Agent** — roadmap Phase 2, built on the now-parameterized repository, the tool contract from 3, and the approval pattern. | The first agent that gets tests, traces, evals and approval *by default* rather than retrofitted. | M |

Milestones 9+ then follow roadmap §38 unchanged: Forecast → Inventory Risk → Supplier Risk →
Procurement → Supervisor → Production RAG → Quality → full Evaluation → full Observability →
Security hardening → Redis → Docker → CI/CD → Cloud → MCP → Proactive agents.

---

## G. Open Decisions

Two decisions are needed before implementation starts:

1. **Ordering deviation** — approve pulling the eval harness and tracing ahead of new agents, or
   follow §38 literally and start at the BI data-layer fixes.
2. **Auth position** — at #7 (memory identity is built once) or later (milestone 5 uses a
   placeholder `business_id` and gets revisited).

**Recommended first milestone: #1, the test + eval harness** — it changes no behaviour, is fully
reversible, and every subsequent milestone's "done" claim depends on it.
