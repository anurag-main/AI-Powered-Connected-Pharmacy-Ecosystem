# Agentic AI Research — Multi-Agent Pharmacy System (for a 15+ LPA job)

> **Purpose:** decide which agents to build next, and which techs to learn while building
> them, so this project becomes a complete portfolio piece that answers any agentic-AI
> interview question from *real* experience.
>
> **Method:** web research (June 2026) on (a) what AI/agent-engineering jobs actually
> demand, (b) production multi-agent architecture patterns, (c) practical pharmacy
> use cases. Sources listed at the bottom.
>
> **TL;DR recommendation:** evolve the single Smart Reorder Agent into a **Supervisor
> multi-agent system** with 4 specialist agents, and layer in the 8 must-know production
> techs as we build. Build order is in §6.

---

## 1. What a 15+ LPA AI / Agent-Engineering job actually demands (2026)

Hard numbers from the LangChain *State of Agent Engineering* survey (1,340 respondents, Nov–Dec 2025) and 2026 hiring guides:

| Signal | Number | What it means for us |
|--------|--------|----------------------|
| Orgs with agents **in production** | 57.3% | Agents are now table-stakes, not a science project |
| Multi-agent usage growth | **+327% in 4 months** | "Multi-agent" is the hot phrase on JDs right now |
| Orgs with **observability** | 89% | You MUST be able to trace/log an agent. Non-negotiable |
| Orgs with **full tracing** | 62% (71.5% of those in prod) | LangSmith / tracing is an expected skill |
| Orgs running **offline evals** | 52.4% | "How do you test an agent?" is a guaranteed interview question |
| Use **LLM-as-judge** for evals | 53.3% | Know this pattern |
| Still rely on **human review** | 59.8% | Human-in-the-loop is core, not optional |
| Use **multiple models** in prod | 75%+ | Provider-agnostic design (we already do this via `get_llm()`) |
| Top production blocker | **Quality 32%**, Latency 20%, Security 25% | These are what senior interviews probe |

**The takeaway:** the job is no longer "call an LLM." It is *"orchestrate multiple agents, give
them memory and tools, make them safe with human approval, and prove they work with traces and
evals."* That is exactly the system we will build.

Salary context (US, for calibration — India 15+ LPA maps to the same skill bar): Agentic AI
Engineer roles quote **$185k–$320k** base. The skill list below is what separates those roles
from a generic "Python + API" role.

---

## 2. The 8 must-know techs (the syllabus hidden in the JDs)

These 8 appear on essentially every 2026 agentic-AI job description. The right side is **where each
one already lives or will live in OUR project** — that's how you turn research into interview stories.

| # | Tech | One-line definition | Where it lives in our pharmacy project |
|---|------|---------------------|----------------------------------------|
| 1 | **Multi-agent orchestration** | A supervisor routes work to specialist agents | NEW: a `supervisor` graph routing to Reorder / Expiry / Interaction / Ask agents |
| 2 | **Tool use / function calling** | LLM calls deterministic functions, never does math itself | Already done: `reorder_tools.py` (pure math), repos (SQL) |
| 3 | **RAG (retrieval-augmented generation)** | Answer from YOUR documents via vector search, not the model's memory | NEW: Drug-Interaction agent over a drug-info corpus in **ChromaDB** (Phase 10) |
| 4 | **Agent memory** | Short-term (this run) + long-term (across runs) | Started: reorder agent now reads `reorder_requests` (its own past actions). Extend with Redis short-term + vector long-term |
| 5 | **MCP (Model Context Protocol)** | Standard way to expose tools so ANY model/agent can discover & call them | NEW: wrap our pharmacy tools (stock lookup, FEFO, reorder) as an MCP server |
| 6 | **Human-in-the-loop (HITL)** | Agent pauses for human approval before acting | Started: pharmacist approves reorders. Formalize with LangGraph `interrupt()` |
| 7 | **Observability / tracing** | See every step, tool call, token, and cost of a run | NEW: **LangSmith** tracing on every node |
| 8 | **Evaluation (evals)** | Prove the agent is correct with test sets + LLM-as-judge | NEW: an eval suite for the reorder/interaction agents |

> If you can speak to all 8 from this one project, you clear the bar for the role. Most candidates
> have 2–3. The whole point of going multi-agent here is to legitimately touch all 8.

---

## 3. The frameworks landscape (so you can answer "why LangGraph?")

| Framework | What it is | Verdict for us |
|-----------|-----------|----------------|
| **LangGraph** | State-machine graph for agents: explicit state, checkpoints, interrupts, human-in-the-loop | **Our choice.** Already in use. Industry default for "more than 2 tool-use turns" |
| CrewAI | Role-based agents ("researcher", "writer") collaborating | Higher-level, less control. Good to *name-drop*, not switch to |
| AutoGen (Microsoft) | Conversational multi-agent | Know it exists |
| Claude Agent SDK | Anthropic's agent harness | Know it exists |
| OpenAI Swarm/Agents SDK | Lightweight handoff agents | Know it exists |

**Interview-ready reason we use LangGraph:** *"I needed explicit, debuggable state and human-approval
gates, not a black box. LangGraph models state as a typed dict with reducers, lets me checkpoint
before expensive LLM calls, and interrupt for human approval — which is exactly what a pharmacy
reorder/interaction system needs because mistakes cost money and safety."*

---

## 4. The two multi-agent architectures (and which we pick)

### Supervisor pattern (we pick this first)
A dedicated **routing node** uses structured output to decide which specialist handles the next
step. Control returns to the supervisor after each specialist. Every decision is visible in traces.

```
              ┌──────────────┐
   user ───▶  │  SUPERVISOR  │ ◀── control returns here after each specialist
              └──────┬───────┘
        ┌────────────┼────────────┬───────────────┐
        ▼            ▼            ▼               ▼
   Reorder      Expiry-Risk   Drug-Interaction  Ask-Your-Pharmacy
   Agent        Agent         Agent (RAG)       Agent (text-to-SQL)
```

- **Pros:** simple to reason about, one routing point, easy to debug, routing visible in traces.
- **Cons:** one extra LLM hop per turn (latency). Fine for early systems.

### Swarm pattern (the "graduate to this later" answer)
No supervisor — agents hand off directly to each other via `Command` objects. Faster (fewer LLM
calls) but harder to debug and prone to **"ping-pong"** (agents bouncing handoffs forever).

**The senior-engineer line:** *"Start with supervisor for clarity, graduate to swarm only when traces
prove latency is the bottleneck and misrouting is rare."*

### Three things the supervisor pattern forces you to implement (all interview gold)
1. **Recursion guard** — track `handoff_count` in state, hard-limit (~3 hops), then escalate to a
   human or a fallback agent. *"A multi-agent system without a recursion guard is a production
   incident waiting to happen."*
2. **Shared state with reducers** — `resolution_notes: Annotated[list, operator.add]` so specialists
   accumulate work instead of overwriting (we already use this exact pattern for `proposals`/`errors`).
3. **Structured routing** — supervisor returns a Pydantic `RoutingDecision{next_agent, reasoning}`,
   never parsed from raw text (same discipline as our `ReorderJudgment`).

---

## 5. Practical pharmacy agents (best, real-world use cases)

Researched against what real pharmacy-AI products actually do. Each maps to a must-know tech, so
every agent teaches you something a JD asks for. Real reported results are cited to keep these honest.

| Agent | What it does | Real-world impact (industry reports) | Tech it teaches |
|-------|-------------|--------------------------------------|-----------------|
| **1. Smart Reorder** ✅ built | Stock vs velocity → propose reorder; LLM judges new-vs-dead 0-sales items | Pharmacies cut excess stock ~30%, stockouts ~40% with AI reorder | Tool use, structured output, HITL, memory |
| **2. Expiry-Risk** ⭐ next | Flags batches expiring soon, ranks by value-at-risk, suggests discount/return | AI expiry tracking cuts medicine waste up to **25%** | A 2nd agent + risk scoring; reuses batch data |
| **3. Drug-Interaction (RAG)** | "Can I sell ibuprofen with this BP med?" → answers from a drug-info corpus | Reduces preventable dispensing errors | **RAG + ChromaDB + embeddings** (the #2 demanded skill) |
| **4. Ask-Your-Pharmacy (text-to-SQL)** | "What were my top 5 sellers in May?" → safe SQL → answer | Staff save ~15 hrs/week vs manual reporting | Text-to-SQL, read-only safety, query guards |
| **5. Demand-Forecast** (stretch) | Seasonal/trend-aware demand per SKU feeding the reorder agent | SKU-level forecast accuracy 80–90% vs manual par-levels | Time-series + agent-feeding-agent |

**Why this set is "best + practical":** all five are things real pharmacy software ships, they reuse
the data we already have (medicines, batches, sales), and together they cover every must-know tech.

---

## 6. Recommended build order (max learning per unit of work)

Each step adds exactly one new big concept — true to the "one concept at a time" rule.

1. **Expiry-Risk Agent** (new specialist #2).
   *New concept:* building a second independent agent + a risk-scoring node. Cheap win, reuses batch
   data, gives the supervisor something to route to. **← do this first.**

2. **Supervisor** over Reorder + Expiry.
   *New concept:* the multi-agent orchestration itself — routing node, recursion guard, shared state.
   This is the moment the project becomes "multi-agent."

3. **LangSmith observability** across all nodes.
   *New concept:* tracing. Wire it once, it covers every agent. 89% of orgs expect this.

4. **Drug-Interaction Agent (RAG)** — the big one.
   *New concept:* RAG end-to-end (chunk → embed → ChromaDB → retrieve → answer). This is Phase 10 and
   the highest-value single skill on the list.

5. **Eval suite** for reorder + interaction (test set + LLM-as-judge).
   *New concept:* proving correctness. The answer to "how do you know it works?"

6. **Ask-Your-Pharmacy (text-to-SQL)** + **MCP server** wrapping the tools.
   *New concepts:* safe text-to-SQL, and exposing tools via MCP so the system is standards-compliant.

7. **Memory upgrade:** Redis short-term + vector long-term (formalize beyond the `reorder_requests` read).

> After step 6 you can legitimately claim all 8 must-know techs on a resume, each with a story.

---

## 7. Memory: the 2026 picture (so we build it right, not trendy)

- LangChain's old `memory` classes are **deprecated**. The supported pattern is LangGraph
  **checkpointer (short-term) + vector store (long-term)**.
- Layered model: **working** (current run) → **episodic/experiential** (vector store) →
  **semantic/relational** (knowledge graph) → **organizational** (governed enterprise context).
- Common 2026 production stack: vector memory for fuzzy recall + an episodic buffer for short-term
  coherence + (optionally) a graph for entity-heavy queries.
- Tools to *name-drop*: **PostgresSaver** (LangGraph checkpointer), **Redis** (short-term, already in
  our stack for Phase 6), **Mem0 / Zep** (specialized long-term memory).

**Our path:** we already gave the reorder agent the simplest real memory (it reads its own past
approvals from `reorder_requests`). Next memory milestone = Redis-backed short-term + a small vector
store for long-term preferences ("this pharmacist always orders Crocin in 100s").

---

## 8. MCP in one paragraph (so the term doesn't scare you in an interview)

**RAG** = give the model better *data*. **Tools** = let the model *act*. **MCP** = a *standard plug
shape* so any model/agent can discover and call your tools the same way (like USB for AI tools). For
us: wrap `get_stock`, `select_fefo`, `suggest_reorder` as an MCP server, and any MCP-aware client
(Claude Desktop, etc.) can use our pharmacy tools without custom glue. It's becoming the default
integration standard in 2026.

---

## 9. How this maps to interview answers (the payoff)

| Likely interview question | Your answer comes from |
|---------------------------|------------------------|
| "How do you orchestrate multiple agents?" | §4 supervisor pattern, recursion guard, shared state |
| "Supervisor vs swarm — when each?" | §4 — start supervisor, graduate to swarm on latency data |
| "How do you stop an agent from looping forever?" | §4 — `handoff_count` recursion guard |
| "How do you give an agent memory?" | §7 — checkpointer + vector, and our `reorder_requests` read |
| "What is RAG and when do you use it?" | §5 #3 + §8 — drug-interaction agent over ChromaDB |
| "How do you keep an agent safe?" | HITL approval + server-side math + structured output + recursion guard |
| "How do you know your agent works?" | §6.5 — eval set + LLM-as-judge + LangSmith traces |
| "Why LangGraph over LangChain/CrewAI?" | §3 — explicit state, checkpoints, interrupts, debuggability |
| "What's MCP?" | §8 — the USB-for-tools standard |

---

## 10. Real pharmacy AI agents shipping in the market (2026)

Researched the actual products people pay for. Grouped by the *capability* (= agent type), with
real companies and reported metrics, plus an honest **"fit for our project?"** column — most of these
assume US insurance / EHR / phone systems we don't have, so I mark what's realistic for a
single-pharmacy India project.

| Agent capability | Real products | Reported results | Fit for OUR project |
|------------------|---------------|------------------|---------------------|
| **Voice refill agent** (patient calls "refill my BP meds") | Brilo AI, Retell AI (G2 4.8, "Best Agentic AI 2026"), Pharmesol, Asepha (86% call containment) | 65% fewer refill calls, 70% faster | ⚠️ Partial — it's the voice problem again (STT ceiling). Skip as primary |
| **Prescription intake / fax / OCR agent** | TJM Labs, Kore.ai (voice+chat+SMS) | Automates intake & reconciliation | ⚠️ Needs prescription images + OCR. Stretch goal |
| **Prior-authorization agent** (insurance approval) | Innovaccer GravityRx, Bookend AI, CVS Claims Assist (−20% processing time) | Faster approvals, fewer denials | ❌ US-insurance specific. Not our market |
| **Medication-adherence / refill-reminder agent** | WestCX (Mosaicx/TeleVox), Pharmie AI | Proactive outreach, fewer missed refills | ✅ **Doable** — we have sales history; "patient hasn't rebought their monthly med" is a real agent we could build |
| **Inventory / reorder agent** | Built into most PMS + Juleb, Kira AI | −30% excess stock, −40% stockouts | ✅ **We already built this** (Smart Reorder) |
| **Expiry / waste agent** | Juleb, IT Medical, Healthray | −25% medicine waste | ✅ **Our planned next agent** |
| **Demand-forecast agent** | WiseCor, ScienceDirect supply-chain models | 80–90% SKU forecast accuracy | ✅ Stretch — feeds the reorder agent |
| **Clinical / drug-interaction "AI pharmacist"** | Sully.ai, Pharmie AI, Asepha.ai | Catches interactions, dosing, allergy conflicts | ✅ **Our planned RAG agent** (ChromaDB) |
| **Ask-the-data / reporting agent** | Various PMS analytics add-ons | Staff save ~15 hrs/week | ✅ **Our planned text-to-SQL agent** |
| **Robotic dispensing** (centralized fill hubs) | CVS (9,000 stores), Walgreens (fills 60% of scripts), Walmart (100k scripts/day) | Massive scale | ❌ Hardware/robotics. Out of scope |

**What this confirms for us:** the agents real products ship that we can *legitimately* build for a
single pharmacy without US-insurance/EHR/robotics are exactly the four already on our roadmap —
**Reorder ✅, Expiry, Drug-Interaction (RAG), Ask-Your-Pharmacy** — plus one worth adding:

> **NEW candidate from the market — Adherence / Re-purchase Agent:** detects customers whose monthly
> medicine is overdue for a refill (from sales history) and flags them for a reminder. Real products
> (WestCX, Pharmie AI) center on this. It's a clean 5th specialist for the supervisor, uses only data
> we already have, and teaches *proactive/scheduled* agent triggers (cron-driven, not request-driven) —
> a pattern interviewers like.

**Interview line this unlocks:** *"I benchmarked my agent set against shipping products like Pharmesol,
Sully.ai and Innovaccer — then deliberately scoped to the capabilities a single independent pharmacy
can run without insurance/EHR integrations: reorder, expiry, drug-interaction RAG, analytics, and
adherence."* That shows product judgment, not just coding.

---

## Sources

- [Agentic AI Engineer: Job Description, Skills & Roadmap (2026) — NovelVista](https://www.novelvista.com/blogs/ai-and-ml/agentic-ai-engineer-career-guide)
- [15 AI Engineer Skills Every Hire Should Have in 2026 — AY Automate](https://www.ayautomate.com/blog/ai-engineer-skills-2026)
- [AI Engineer Roadmap 2026 — Kunal Ganglani](https://www.kunalganglani.com/blog/ai-engineer-roadmap-2026)
- [The Agentic-AI Job Guide (roles & pay) — The AI Career Lab](https://theaicareerlab.com/blog/agentic-ai-jobs-guide-2026)
- [Multi-Agent Orchestration in LangGraph: Supervisor vs Swarm — DEV / Focused](https://dev.to/focused_dot_io/multi-agent-orchestration-in-langgraph-supervisor-vs-swarm-tradeoffs-and-architecture-1b7e)
- [LangGraph Multi-Agent Supervisor — LangChain reference](https://reference.langchain.com/python/langgraph-supervisor)
- [State of Agent Engineering — LangChain](https://www.langchain.com/state-of-agent-engineering)
- [Best AI Observability Tools for Autonomous Agents in 2026 — Arize](https://arize.com/blog/best-ai-observability-tools-for-autonomous-agents-in-2026/)
- [MCP vs RAG vs AI Agents — ByteByteGo](https://blog.bytebytego.com/p/ep202-mcp-vs-rag-vs-ai-agents)
- [Building effective AI agents with MCP — Red Hat Developer](https://developers.redhat.com/articles/2026/01/08/building-effective-ai-agents-mcp)
- [AI Agents for Pharmacy — Agentmelt](https://agentmelt.com/blog/ai-agents-for-pharmacy-automation/)
- [Integrating AI Agents with Pharmacy Inventory — Simbo AI](https://www.simbo.ai/blog/integrating-ai-agents-with-pharmacy-inventory-and-refill-systems-to-optimize-medication-availability-and-automate-real-time-stock-management-in-retail-pharmacies-1140410/)
- [How AI Enhances Pharmacy Systems to Reduce Waste — Juleb](https://juleb.com/blog/How-AI-Enhances-Pharmacy-Systems/en)
- [Agent Memory Architectures: 5 Patterns and Trade-offs — Atlan](https://atlan.com/know/agent-memory-architectures/)
- [State of AI Agent Memory 2026 — Mem0](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- [AI agent memory: types, architecture & implementation — Redis](https://redis.io/blog/ai-agent-memory-stateful-systems/)
- [Top 10 Voice AI Agents for Pharmacy Refill Requests 2026 — Brilo AI](https://www.brilo.ai/resources/top-voice-ai-agents-for-pharmacy-refill-requests)
- [Best Voice AI for Pharmacy 2026 — Pharmesol](https://pharmesol.com/blog/best-voice-ai-for-pharmacy)
- [Top 10 AI Platforms for Specialty Pharmacy 2026 — Innovaccer](https://innovaccer.com/resources/blogs/top-10-ai-platforms-for-specialty-pharmacy-in-2026)
- [Top 3 AI Pharmacists in 2026 — Sully.ai](https://www.sully.ai/blog/top-3-ai-pharmacists-in-2025)
- [WestCX rolls out agentic AI platform for pharmacies — MobiHealthNews](https://www.mobihealthnews.com/news/westcx-rolls-out-agentic-ai-platform-pharmacies)
- [Prescription management use case — Kore.ai](https://www.kore.ai/use-cases/prescription-management)
- [Aetna reduces claims processing time 20%+ with AI — CVS Health](https://www.cvshealth.com/news/innovation/aetna-reduces-claims-processing-time-by-more-than-20-percent-with-ai-to-improve-care-experience.html)
