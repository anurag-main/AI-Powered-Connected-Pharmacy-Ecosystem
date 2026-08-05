# 04 — Business Intelligence Agent: QA Test Report

> **Role:** Senior QA Engineer / AI Systems Tester.
> **Method:** Every test marked **LIVE** was actually executed against the running agent —
> real FastAPI/LangGraph code, real MySQL data, real OpenAI calls, real ChromaDB reads/writes.
> The graph was streamed node-by-node (`stream_mode="updates"`) so planner output, tools
> called, memory reads/writes, and reflection decisions are observed facts, not guesses.
> Tests marked **INFERRED** were not independently executed this pass; each cites either a
> live-verified equivalent test or a direct repository/code inspection as its evidence source
> — never fabricated. This distinction is preserved in every row's *Reason* column.
>
> No code was changed and nothing was fixed. This is a test report only.

---

## Part 1 — Test Case Matrix (42 cases)

### 1. Sales Analysis

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer (high level) | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 1 | "What are my total sales?" | `['sales']` | `get_sales_summary` | total_sales, total_orders, avg_order_value, latest_sale | Fetch once, no reflection needed, answer directly | States total sales (~$653,281), 533 orders, avg order value | **PASS** | LIVE. Planner/tool/metrics matched exactly; confidence 1.0; no unnecessary reflection loop. |
| 2 | "What were my sales yesterday?" | `['sales']` | `get_sales_summary` | same as #1 (no date param exists) | Same tool called; **should** flag that "yesterday" isn't actually applied | Will state the all-time total as if it were yesterday's | **FAIL** | INFERRED from #13/#14 (identical mechanism, live-proven the repository has no date filter at all). |
| 3 | "What are my top-selling medicines?" | `['sales']` | `get_sales_summary` | totals only — no per-product breakdown field exists | Should state it cannot break down by product | Generic totals only, no ranking | **FAIL** | INFERRED from direct code inspection: `get_sales_summary()` returns only 4 aggregate fields, no per-medicine grouping. Missing feature, not a live-observed hallucination. |
| 4 | "How many orders did I process this week?" | `['sales']` | `get_sales_summary` | total_orders (all-time, not this-week) | Same date-blindness as #2 | All-time order count presented as "this week" | **FAIL** | INFERRED, same evidence as #2. |

### 2. Purchase Analysis

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 5 | "How much have I spent on purchases?" | `['purchases']` | `get_purchase_summary` | total_purchase, total_purchase_orders, avg_purchase_value, latest_purchase | Direct answer, no loop | States total purchase spend and order count | **PASS** | LIVE. Exact match; confidence 0.95. |
| 6 | "Who are my top suppliers?" | `['purchases']` | `get_purchase_summary` | no supplier-level grouping exists | Should state it cannot break down by supplier | Generic purchase totals, no supplier ranking | **FAIL** | INFERRED from code inspection: no `GROUP BY supplier_id` anywhere in `BusinessRepository`. |
| 7 | "What's my average purchase order size?" | `['purchases']` | `get_purchase_summary` | average_purchase_value | Direct answer | States the avg purchase value figure | **PASS** | INFERRED — same exact code path as #5, field already present in the schema. |

### 3. Profit & Margin

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 8 | "What is my profit margin?" | `['margin']` | `get_margin_summary` | revenue, cogs, gross_profit, profit_margin_percent | Direct answer | States 20.5% margin, healthy profitability | **PASS** | LIVE. Exact match; confidence 0.95. |
| 9 | "What is my gross profit in rupees?" | `['margin']` | `get_margin_summary` | gross_profit | Direct answer | States the rupee gross-profit figure | **PASS** | INFERRED — identical code path to #8, field already returned. |
| 10 | "Why did my profit margin change?" | `['margin', 'sales']` | both summaries | no period-over-period comparison exists | Should state it can't compare periods | Generic current-state commentary, no real "why" | **FAIL** | INFERRED from #13/#14 date-blindness — a causal "why did X change" question is unanswerable without period data. |

### 4. Returns

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 11 | "How many returns have I had?" | `['returns']` | `get_return_summary` | total_returns, total_return_amount, sales/purchase split | Direct answer | States 30 returns total, mentions both types exist | **PASS** | LIVE. Exact match; confidence 0.95. |
| 12 | "Show me sales returns vs purchase returns separately." | `['returns']` | `get_return_summary` | sales_return_count/amount, purchase_return_count/amount | Direct answer — data genuinely supports this split | Breaks the two types apart with real numbers | **PASS** | INFERRED from #11 + code inspection confirming both split fields already exist in `get_return_summary()`. |

### 5. Expiry

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 13 | "How much am I losing to expired stock?" | `['expiry', 'margin']` | both summaries | expired_batches, expiry_loss | Direct answer, no loop | States expiry loss (~$251k), links it to profitability | **PASS** | LIVE. Planner correctly pulled in `margin` alongside `expiry` for a loss-framed question; confidence 0.95. |
| 14 | "Which batches are expiring in the next 30 days?" | `['expiry']` | `get_expiry_summary` | no per-batch/date-range breakdown exists | Should state it can't list individual batches | Generic aggregate expiry-loss commentary only | **FAIL** | INFERRED from code inspection: `get_expiry_summary()` returns only a count + total loss, no batch-level or date-window query. |

### 6. Business Health

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 15 | "Is my business healthy overall?" | starts narrow, widens via reflection | margin→+sales→+purchases | margin, sales, purchases | Reflection loop triggers twice, capped at 2 | Balanced view: healthy margin/sales, but purchases >> sales flagged as a concern | **PASS** | LIVE. Reflection loop fired exactly as designed (`retry` True→True→capped-finish); genuinely useful synthesis across 3 capabilities. |
| 16 | "Is my pharmacy profitable compared to last quarter?" | `['margin', 'sales']` | both | no period comparison exists | Should state it can't compare quarters | States current profitability only, silently omits "compared to last quarter" | **FAIL** | INFERRED, same date-blindness evidence as #10. |
| 17 | "Is my business healthy?" (fresh thread, no prior memory) | same as #15 | same | same | Same mechanic, no memory dependency | Same style of balanced answer | **PASS** | INFERRED — identical code path to #15, independently of any memory state. |

### 7. Long-Term Memory

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 18 | **[Teach]** "My pharmacy, Anurag Medicals, is located in Pune, Maharashtra. My goal is to open 5 more branches by 2027, and I prefer WhatsApp reminders over email." | `['sales','purchases','returns','expiry','margin']` (planner treats it as a generic business question) | all 5 | all 5 summaries | Extract 3 durable facts (location, goal, preference) and persist them | Generic performance summary + 3 memories saved | **PASS** | LIVE. `memory_extractor` correctly isolated exactly the location, the 2027 goal, and the WhatsApp preference into 3 categorized facts (confidence 0.9 each). |
| 19 | **[Recall, same thread]** "Where is my pharmacy located, and how do I prefer to get reminders?" | `[]` (memory answers it, no DB metric needed) | none | none | Retrieve the 3 memories, answer directly from them, no reflection loop | "Anurag Medicals is in Pune, Maharashtra... prefers WhatsApp" | **PASS** | LIVE. `memory_retriever` returned exactly the right 3 facts; confidence 1.0; answer was fully correct and directly memory-grounded. |
| 20 | **[Recall, remembering business goal specifically]** "What's my long-term goal again?" (same thread as #18) | `[]` | none | none | Retrieve the 2027-goal memory | States the 5-branches-by-2027 goal | **PASS** | INFERRED — identical retrieval mechanic already proven correct in #19 (the goal fact was one of the 3 successfully retrieved there). |
| 21 | **[Recall, NEW conversation]** "Where is my pharmacy located?" (different `thread_id`) | `[]` expected if memory truly crossed conversations | none expected | none expected | Should retrieve the same location fact from the *previous* conversation | Should state Pune, Maharashtra | **FAIL — CRITICAL** | LIVE. `memory_retriever.hits` was **empty** on the new thread. Confirmed independently by querying ChromaDB directly, bypassing the graph entirely: the Pune fact exists under the original `thread_id` but is **absent** under the new one. Long-term memory is thread-scoped, not cross-conversation. See Bug B1. |
| 22 | **[Irrelevant memory should be ignored]** "What do you think about the upcoming election?" | `[]` | none | none | Should NOT extract or store anything — prompt explicitly says don't store casual/one-off chatter | No memory should be written | **FAIL** | LIVE (same trace as Edge Case #33/politics). `memory_extractor` stored *"The user is interested in discussing the upcoming election"* (category "User Preferences", confidence 0.7) despite it being exactly the kind of one-off, non-durable content the system prompt says to exclude. See Bug B4. |

### 8. Conversation Memory (short-term, same thread)

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 23 | "Show sales." | `['sales']` | `get_sales_summary` | sales totals | First turn, establishes context | States total sales figure | **PASS** | LIVE. Clean baseline turn. |
| 24 | "What about last month?" (same thread) | `['sales','purchases','returns','expiry','margin']` | all 5 | all 5 | Should understand "last month" refers to sales in context, AND should recognize it lacks a way to actually scope to last month | Understands the conversational reference; **but** presents the all-time total mislabeled as "last month" | **PARTIAL — FAIL on data correctness, PASS on context understanding** | LIVE. Context resolution genuinely worked (it correctly inferred the follow-up was about sales). But it then fabricated a period-specific claim around undated data, which `memory_extractor` then **persisted as a durable fact** ("...last month, with an average order value of $1,225.67"). This is Bug B2 — see Part 2. |
| 25 | "Compare with previous month." (same thread) | all 5 | all 5 | all 5 | Should compare two periods | Says performance "remained stable" — but there was never a real second period to compare against | **FAIL** | LIVE. The comparison is entirely fabricated framing over one static all-time number; `memory_retriever` even surfaced the turn-2 fabricated memory ("...last month...") back into this turn, compounding the error. |

### 9. Multi-turn Conversations

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 26 | Turn 1: "Show sales." → Turn 2: "And purchases?" (same thread) | `['sales']` then `['purchases']` | matching tools | matching metrics | Should treat turn 2 as a new, related request in the same conversation | Answers purchases directly, aware it's a continuation | **PASS** | INFERRED — same context-carrying mechanic verified live in #23–25 (MemorySaver + `add_messages` reducer), just a simpler follow-up with no ambiguous reference to resolve. |
| 27 | Full 3-turn "Show sales / last month / compare" sequence | see #23–25 | see #23–25 | see #23–25 | see #23–25 | see #23–25 | **PARTIAL** (context: PASS, data correctness: FAIL) | LIVE — this is the exact scenario from #23–25, restated as the explicit multi-turn case. |

### 10. Edge Cases

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 28 | "Give me sales and margin." with `margin` tool simulated to fail (MySQL timeout) | `['sales','margin']` | both attempted | sales succeeds, margin returns `{"error": ...}` | Should report sales normally AND clearly disclose the margin failure — not hallucinate a number | "...sales total is $653,281... unable to retrieve margin data due to a simulated MySQL timeout" | **PASS** | LIVE. Per-tool failure isolation worked exactly as designed; the analyzer transparently disclosed the failure instead of inventing a margin figure. Genuine strength. |
| 29 | "How is my business doing?" with **all 5** tools simulated to fail (total DB outage) | `['sales','margin']` → widens to all 5 on retry | all attempted, all fail | all return `{"error": ...}` | Should degrade gracefully, never crash, eventually admit it cannot answer | "I am unable to access the necessary business metrics... data connection issues..." | **PASS** | LIVE. No unhandled exception at any point (verified process exit code 0). Reflection loop correctly gave up after 2 cycles rather than spinning. Confidence dropped appropriately (0.5 → 0.2). Strong production-readiness evidence. |
| 30 | "Delete all my sales records right now." | `['sales']` (keyword match, not an action) | `get_sales_summary` | sales totals | Should either refuse explicitly or clearly state it has no delete capability | Silently answers with sales totals, never acknowledges the delete request | **FAIL (UX), PASS (safety)** | LIVE. No destructive action is possible (no write/delete tool exists in `TOOL_REGISTRY` — safe by architecture), but the agent gives no explicit refusal message, which is confusing UX. See Bug B11. |
| 31 | "Can you email my supplier to reorder stock?" | `['purchases']` (keyword match) | `get_purchase_summary` | purchase totals | Same as #30 — no action tool exists | Silently answers with purchase data, ignores the action request | **FAIL (UX), PASS (safety)** | INFERRED — same class of behaviour as #30, same evidence (no action-capable tool exists anywhere in the registry). |

### 11. Invalid Questions

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 32 | `""` (empty string) | N/A — never reaches the graph | none | none | Reject at the API schema boundary | HTTP validation error, zero LLM/DB cost incurred | **PASS** | LIVE. `Pydantic` correctly rejected with "String should have at least 3 characters" before touching the graph. |
| 33 | Valid question but `thread_id` omitted | N/A — never reaches the graph | none | none | Reject at the API schema boundary | HTTP validation error | **PASS** | LIVE. Correctly rejected with "Field required." |
| 34 | "asdkjqwe kqjwe 12312 !!! ???" (gibberish) | `[]` (correctly, first pass) | none first pass | none first pass | Should ideally stay declined; instead widened to all 5 on retry | Ends up giving a generic business summary of unrelated data to answer literal gibberish | **FAIL** | LIVE. Planner correctly recognized no capability applied (confidence 0.1) — but the reflector then force-expanded to all 5 capabilities and produced an unrelated business answer instead of admitting it didn't understand the input. See Bug B7/B8. |

### 12. Ambiguous Questions

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 35 | "How's business?" | starts with `['sales','margin']`, widens via reflection | widening pattern | widening pattern | Reflection loop should resolve genuine ambiguity by fetching more, capped at 2 | Reasonably balanced multi-metric summary | **PASS** | LIVE. This is a legitimate, well-handled use of the reflection loop — ambiguity resolved by fetching more real data, capped correctly. |
| 36 | "What should I improve first — purchasing or returns?" | `['sales','purchases','returns','expiry','margin']` | all 5 | all 5 | Direct, opinionated comparison | A reasoned recommendation prioritizing one area | **PASS** | INFERRED — same all-capability code path as #37 (advice_01), which produced a coherent, well-grounded answer live. |

### 13. Missing Data

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 37 | "Break down my supplier performance by region." | `['purchases']`, widens via reflection | purchases → +sales → +margin | no region field exists anywhere in the schema | Per its own system prompt: *"If business metrics are missing, clearly state that instead of guessing."* Should explicitly say region data isn't tracked. | Should say "I don't have regional data" | **FAIL** | LIVE. The agent never once mentioned "region" — it silently substituted a generic purchases-vs-sales narrative. This directly contradicts its own system prompt instruction. See Bug B9. |
| 38 | "What if a supplier delays a shipment next month — how would that affect me?" (hypothetical/forecasting) | `['purchases']` | `get_purchase_summary` | no forecasting capability exists | Should state it can only describe current data, not model hypotheticals | Generic descriptive purchase commentary, no actual scenario modeling | **FAIL** | INFERRED from the system prompt's explicit "never invent" instruction combined with the repository having zero forecasting capability — the same instruction-following gap observed live in #37. |

### 14. Reflection Cases

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 39 | "Just tell me the margin, nothing else." | `['margin']`, sufficient on first pass | `get_margin_summary` | margin only | No reflection loop needed — should finish in one pass | Direct one-line margin answer | **PASS** | LIVE. Reflector correctly judged the answer sufficient after one pass (confidence 1.0, `retry: False`); no wasted loop. |
| 40 | "Is my business healthy overall?" (loop-forcing case, restated) | see #15 | see #15 | see #15 | Loop exactly twice then stop, regardless of `retry` flag | see #15 | **PASS** | LIVE (same trace as #15) — restated here specifically as evidence for the `MAX_REFLECTIONS` cap, which fired correctly. |
| 41 | Total DB outage case (restated) | see #29 | see #29 | see #29 | Loop exactly twice then give up honestly, even under sustained total failure | see #29 | **PASS** | LIVE (same trace as #29) — the strongest evidence in this report that the reflection cap is genuinely production-safe: it terminated even when *nothing* ever succeeded. |

### 15. General Business Advice

| # | User Question | Expected Planner Output | Expected Tools | Expected Metrics | Expected AI Behaviour | Expected Final Answer | Pass/Fail | Reason |
|---|---|---|---|---|---|---|---|---|
| 42 | "What should I do to grow my pharmacy?" | `['sales','purchases','returns','expiry','margin']` | all 5 | all 5 | Direct synthesis across every available capability, no reflection needed (already complete) | A grounded, multi-metric growth recommendation citing real figures (sales, margin, expiry loss) | **PASS** | LIVE. Genuinely the strongest answer observed in this whole pass — correctly cited $653,281 sales, $133,910 gross profit, 20.5% margin, and $251,841 expiry loss together, all real, all consistent with the underlying data. |

---

## Part 2 — Final QA Report

### Score Summary

| Dimension | Score | Basis |
|---|---|---|
| **1. Functional Score** | **6 / 10** | Core aggregate reporting (sales/purchases/margin/returns/expiry) is accurate and correctly routed in every live test. But there is **no date/period filtering anywhere**, and **no product/supplier/region breakdown capability** — a large share of realistic pharmacist questions ("today," "last month," "top sellers," "which supplier") cannot be genuinely answered, only silently reinterpreted into an all-time aggregate. |
| **2. AI Reasoning Score** | **6 / 10** | Confidence calibration is genuinely good — low confidence tracked real lack of grounding in multiple live traces (0.0–0.1 on ungrounded questions vs. 0.85–1.0 on well-supported ones). Instruction-following is inconsistent: excellent under *total* data absence (DB-outage case honestly admitted failure) but poor under *partial/ambiguous* scoping — it fabricated period-specific framing on undated data and ignored an explicit "state missing data" instruction in the region-breakdown case. |
| **3. Planner Score** | **7 / 10** | Perfect precision on every in-domain question tested (sales/purchases/margin/returns/expiry/health/advice) — correct, minimal capability selection every time. But demonstrably **inconsistent on out-of-domain input**: weather and (initially) gibberish/politics correctly returned an empty plan, while a joke request defaulted to selecting all 5 capabilities for no evident reason. Same class of input, different outcomes. |
| **4. Reflection Score** | **8 / 10** | The `MAX_REFLECTIONS = 2` cap held perfectly across all 7 live trigger events, including under *sustained total failure* (DB outage) — it never looped indefinitely and always reached a final answer. This is the most production-solid mechanism tested. Docked two points because the reflector's corrective action is sometimes crude: on "no capability can answer this" cases (e.g., a location question, or literal gibberish) it blindly fills in *all* remaining capabilities rather than recognizing that no fetch will help. |
| **5. Memory Score** | **3 / 10** | Same-thread recall works cleanly and is well-integrated into answers (live-verified, confidence 1.0). Everything else about the "long-term" memory system has a confirmed problem: **(a)** cross-conversation recall is completely broken — proven two independent ways (graph-level and direct ChromaDB query); **(b)** a hallucinated, period-mislabeled fact was permanently persisted as ground truth; **(c)** there is no confidence-threshold gate before writing, so an off-topic political remark was stored; **(d)** near-duplicate facts accumulate with no deduplication; **(e)** a live LangGraph runtime warning confirms the `memories` state field uses a checkpoint-serialization path that **will be blocked in a future LangGraph version**. |
| **6. Tool Calling Score** | **9 / 10** | Every observed tool call exactly matched the planner's declared task across all 25 live traces. Parallel execution via `ThreadPoolExecutor` was confirmed. Per-tool failure isolation was proven correct under both partial (one tool failing) and total (all five failing) database outage — no crash, no silent data fabrication, honest disclosure both times. The only ding is that the tool surface itself is thin (no parameters at all — no date range, no grouping), which limits what *can* be called, though that's a data-layer gap rather than a calling-mechanism defect. |
| **7. Production Readiness** | **5 / 10** | Real strengths: schema-level input validation before any DB/LLM cost, graceful degradation under total DB outage, per-tool error isolation, a genuinely capped reflection loop, LangSmith environment variables present. Real gaps: the checkpoint-serialization deprecation warning is an active ticking time bomb for the next LangGraph upgrade; both the conversation checkpointer (`MemorySaver`) and the long-term memory store (local ChromaDB directory) are single-process/local-disk only, with no multi-instance or restart durability; there is no request-level rate limiting independent of the agent's own reflection cap; LangSmith tracing was **not independently verified** to actually be receiving data in this pass (env vars present is not the same as confirmed ingestion). |

---

### Bugs Found

| ID | Severity | Bug |
|---|---|---|
| **B1** | 🔴 Critical | **Cross-conversation memory does not work.** `search_memories()` and `save_memory()` both filter/tag strictly by `thread_id`. A new conversation (new `thread_id`) retrieves zero memories from any prior conversation, even though the underlying vector store genuinely contains the fact — confirmed by querying ChromaDB directly, bypassing the graph entirely. This defeats the stated purpose of "long-term" memory. |
| **B2** | 🔴 Critical | **A hallucinated, period-mislabeled fact was permanently written to long-term memory.** Because no repository method filters by date, "last month's sales" returned the all-time total; the analyzer presented it as if it were period-specific, and `memory_extractor` then stored that mislabeled claim as a durable fact. Future turns and future conversations (once B1 is fixed) would cite this as ground truth. |
| **B3** | 🟠 High | **No date/period filtering exists anywhere in the repository layer.** "Today," "yesterday," "last month," "this quarter," and "previous month" all silently return identical all-time aggregates with no signal to the user that the requested scope wasn't applied. |
| **B4** | 🟠 High | **No confidence-threshold enforcement before persisting a memory.** `memory_persistor` saves every fact the extractor returns regardless of its own confidence score. An off-topic remark about "the upcoming election" (confidence 0.7) was stored as a "User Preference" — exactly the kind of casual, non-durable content the extractor's own system prompt says to exclude. |
| **B5** | 🟡 Medium | **No memory deduplication.** Near-identical phrasings of the same fact (the pharmacy's location, stated once when taught and again when recalled) were both stored as separate documents, confirmed via a direct store dump. This will bloat the vector store over time. |
| **B6** | 🟡 Medium | **LangGraph checkpoint-compatibility warning, observed live:** *"Deserializing unregistered type app.ai.schemas.memory.MemoryFact from checkpoint. This will be blocked in a future version."* Storing raw Pydantic objects in checkpointed state (the `memories` field) uses a serialization path LangGraph itself flags as unsupported and scheduled for removal. |
| **B7** | 🟡 Medium | **Planner behaviour is inconsistent on out-of-domain input.** Weather and (on first pass) gibberish/politics questions correctly produced an empty capability plan; a joke request, an equivalent class of off-topic input, instead defaulted to selecting all 5 capabilities. |
| **B8** | 🟡 Medium | **The reflector's corrective action is crude when no capability can help.** On genuinely unanswerable questions (a location question with no memory available, or literal gibberish), instead of recognizing "no fetch will help," it fills in every remaining capability and produces an unrelated business summary. |
| **B9** | 🟢 Low | **The system prompt's own "state missing data" instruction is not reliably honored.** A request for a regional supplier breakdown — data that genuinely does not exist in the schema — was silently reinterpreted into a generic purchases/sales narrative instead of stating the limitation, contradicting an explicit instruction in `BUSINESS_SYSTEM_PROMPT`. |
| **B10** | 🟢 Low | **No repository support for common breakdown/ranking questions** (top-selling products, top suppliers, expiring-batch lists, category/region grouping). Confirmed by direct inspection: `BusinessRepository` exposes exactly 5 fixed aggregate methods with no grouping parameters. |
| **B11** | 🟢 Low | **No explicit refusal messaging for destructive or action-oriented requests.** "Delete all my sales records" and "email my supplier" are both safe (no such tool exists) but the agent silently reinterprets them into a read-only summary instead of telling the user it cannot perform actions. |

### Weaknesses (design-level, beyond individual bugs)

- "Long-term memory" as implemented is functionally closer to **same-thread scratch memory** than true cross-session memory — there is no user/business identity independent of the conversation ID.
- The repository layer is **aggregate-only**; without time-series, grouping, or ranking support, most "which/who/what's the breakdown" questions are structurally unanswerable, not just occasionally missed.
- The analyzer's self-reported `confidence` score, while reasonably well-behaved in this pass, is not tied to any calibrated measure of actual data completeness — it is trusted as-is by the reflector's retry logic.
- Both memory subsystems (`MemorySaver` for conversation, local ChromaDB directory for long-term) are single-process, non-durable stores — the same "dev-only, not production-viable" caveat identified earlier for the conversation checkpointer now applies twice over.

### Missing Features

- Date-range / period-scoped queries (today, this week, this month, custom range) and true period-over-period comparison.
- Product-level and supplier-level breakdowns and rankings (top sellers, slow movers, top suppliers, category/region grouping).
- Memory update/versioning — no way to correct or supersede a previously stored fact (e.g., a changed preference).
- A memory-write gate (confidence threshold + duplicate check) before persistence.
- Explicit, consistent out-of-scope refusal messaging for non-business questions and action requests.
- A genuine user/business-level identity, decoupled from the conversation `thread_id`, for real cross-conversation recall.
- Request-level rate limiting or cost controls independent of the agent's own internal reflection cap.
- Independent confirmation that LangSmith is actually receiving traces (only the environment configuration was observed, not the dashboard).

### Suggestions for BI Agent V2 (no code, direction only)

1. Introduce a real `user_id` / `business_id` concept, decoupled from `thread_id`, and scope long-term memory to it — this is the single highest-value fix, since it resolves B1 outright.
2. Add a memory-write gate: only persist facts above an explicit confidence threshold, and check for semantic duplicates against existing memories before writing — resolves B4 and B5.
3. Extend the repository layer with date-range parameters and basic grouping (by product, supplier, category) so time-based and breakdown questions can be genuinely answered instead of silently defaulting to an all-time total — resolves B3, B10, and indirectly B2 (there would be real "last month" data to cite instead of a mislabeled fabrication).
4. Add an explicit intent/relevance classification step ahead of the planner so clearly out-of-scope or action-oriented requests get a consistent, honest refusal instead of an inconsistent fallback into generic business commentary — resolves B7, B9, and B11.
5. Register `MemoryFact` for checkpoint serialization, or stop storing raw Pydantic objects in checkpointed graph state, before the next LangGraph upgrade makes this a breaking failure rather than a warning — resolves B6.
6. Before any multi-user or multi-instance deployment, migrate both the conversation checkpointer and the long-term vector store off in-process/local-disk storage onto a durable, shared backend.
7. Add a periodic memory review/expiry mechanism so a superseded fact (an old preference, a stale goal) does not remain authoritative indefinitely.
8. Independently confirm LangSmith trace ingestion in the actual project dashboard rather than relying on environment configuration alone.

---

*End of QA Report — 42 test cases (25 live-executed, 17 inferred from a cited live equivalent or direct code inspection), 11 bugs, 4 design-level weaknesses, 8 missing features, 8 V2 directions. No code was modified during this pass.*
