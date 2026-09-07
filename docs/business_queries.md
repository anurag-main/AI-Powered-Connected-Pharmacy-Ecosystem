# Business Queries

> How a plain-English business question becomes SQL, what the LLM is and is not
> allowed to decide, the date semantics, and how memory is scoped.

---

## The pipeline

```text
"What were my top 5 products by sales last month?"
        │
        ▼  LLM — interpretation only
BusinessQuery(metric=sales, dimension=product, period=last_month, sort=desc, limit=5)
        │
        ▼  Pydantic — rejection of anything not representable
validated
        │
        ▼  app/core/time_range.py — deterministic, in code
DateRange(2026-08-01, 2026-08-31)
        │
        ▼  BusinessRepository — WHERE / GROUP BY / ORDER BY / LIMIT
[{label: "Crocin 500", value: 100.00, quantity: 5}, ...]
        │
        ▼  LLM — explanation only
"Crocin 500 led August with ₹100.00 across 5 units…"
```

**The model names the question. The application answers it.** The LLM never computes a
date, never produces a figure, never writes SQL, and never picks a table or column.

---

## What the LLM may say

`app/ai/schemas/business_query.py` is the entire vocabulary.

| Field | Type | Meaning |
|---|---|---|
| `metric` | enum | `sales` · `purchases` · `returns` · `expiry` · `margin` |
| `dimension` | enum \| null | `product` · `manufacturer` · `supplier` · `day` · `month`; null = overall total |
| `period` | enum | `all_time` · `today` · `yesterday` · `this_week` · `last_week` · `this_month` · `last_month` · `this_quarter` · `last_quarter` · `this_year` · `last_year` · `custom` |
| `start_date` / `end_date` | date \| null | **only** with `period=custom` |
| `sort` | enum | `desc` (top/most) · `asc` (lowest/least) |
| `limit` | int | 1–100, default 10 |

Every field is a closed enum or a bounded integer. That is the security model: there is
no blocklist to get past, because `dimension="(SELECT …)"` is not a value the type can
hold. Pydantic rejects it before any application code runs.

### Which breakdowns exist

| Metric | Supported dimensions |
|---|---|
| `sales` | product · manufacturer · day · month |
| `purchases` | supplier · day · month |
| `returns` | product · manufacturer · day · month |
| `margin` | product · manufacturer |
| `expiry` | product · manufacturer |

The gaps are deliberate, not oversights:

- **`sales` has no `supplier`.** A sale points at a batch, and a batch does not record
  which purchase created it. There is no join, so the question is unanswerable.
- **`margin` and `expiry` have no time dimension.** Margin is per sold line; expiry is a
  property of stock on hand. Bucketing either by day answers a question nobody asked.
- **`expiry` accepts no period at all.** It reports stock that has *already* expired — a
  snapshot of now. "Expired stock last month" has no agreed meaning, and inventing one
  would be a silent lie. Batches *approaching* expiry belong to the Expiry-Risk agent.

### There is no `category`

Medicines have `name`, `normalized_name`, `mrp`, `hsn_code` and `manufacturer`. **No
category column exists.** `Dimension` therefore omits it, rather than advertising a
breakdown the repository cannot produce — a planner told it may ask for a category
would promise the user an answer that cannot arrive.

Adding it needs a schema change and a migration, not a repository change. Pinned by
`test_there_is_still_no_category_dimension`.

---

## Date semantics

`app/core/time_range.py`. Read this section before changing anything about periods.

### Timezone

Periods resolve in the pharmacy's local timezone from `APP_TIMEZONE`, defaulting to
**`Asia/Kolkata`**. "Today" means today *there*: a sale rung up at 00:30 IST belongs to
that day's takings, and resolving in UTC would file it under the previous day.

A missing or misspelt zone **raises at startup**. A silent UTC fallback would shift
every boundary by hours and produce confidently wrong "today" figures — worse than
refusing to start. Windows ships no system zone database, so `tzdata` is a pinned
dependency.

> **Assumption to revisit at deployment.** The database stores *naive* timestamps
> written in the server's own local time, so comparisons are naive local datetimes.
> This is correct only while the app server and the database share a timezone — true
> today (one machine), and the thing to check when they are split across hosts.

### Boundaries

A `DateRange` is a pair of **inclusive calendar dates**. `last_month` from any September
day is 1–31 August, both endpoints included.

Turning that into SQL differs by column type, which is why `DateRange` exposes two
helpers instead of letting callers improvise:

| Column | Type | Predicate |
|---|---|---|
| `purchases.purchase_date` | `Date` | `col >= start AND col <= end` |
| `sales.sold_at`, `returns.returned_at` | `DateTime` | `col >= start 00:00 AND col < (end+1day) 00:00` |

**The half-open upper bound on datetimes is the important one.** `col <= end` compares
against `end 00:00:00` and silently drops everything that happened *during* the final
day of the range — the classic off-by-one that quietly under-reports every period.
Pinned by `test_the_last_day_of_a_range_is_included`.

### Edge cases, all tested

| Case | Behaviour |
|---|---|
| Week start | **Monday** (ISO 8601). "This week" on a Sunday is that Monday through Sunday |
| Month lengths | `calendar.monthrange`, so February is 28 or 29 as appropriate |
| Leap years | `last_month` from March 2024 gives 1–29 February |
| Short-month overflow | `last_month` from 31 May gives 1–30 April, not an invalid 31 April |
| Year rollover | `last_month` from January gives December of the previous year; `last_quarter` from Q1 gives Q4 |
| `this_*` periods | Run from the period start to **today**, not to the period end — a month is not over yet |
| Reversed range | `start > end` raises. In SQL it would silently return nothing, and an empty report reads like "no business" rather than "bad query" |
| Dates with a named period | Rejected. Which wins, `last_month` or the dates? Rejecting beats guessing |
| Empty period | Zeros and no rows — a real answer, distinct from a failure |

### Every result says what it measured

Each result carries a `period` label (`"2026-08-01 to 2026-08-31"`, `"all time"`,
`"stock as at today"`), and the analyzer is instructed to state it.

This closes the hole behind the QA pass's worst finding: an all-time total was reported
as "last month's sales", and that mislabelled figure was then written to long-term
memory as durable fact.

---

## Ranking and grouping

All of it happens in SQL — `WHERE`, `GROUP BY`, `ORDER BY`, `LIMIT`. Never "load the
rows and sort in Python": with three months of seed data both look fine, but with three
years of real sales the Python version loads every row into memory to return ten.

**What gets sorted depends on the dimension.** Ranking a product list by value answers
"which sold most". Ranking a *day* list by value would answer "which was my best day"
while destroying the trend the user asked to see — so time buckets (`day`, `month`) sort
chronologically, and `sort` chooses the direction of time instead.

`limit` is capped at 100. Beyond a screenful a breakdown is a data export, which is a
different feature with different performance characteristics.

### Indexes

No new indexes were added. The ones the new queries need already exist:

| Index | Serves |
|---|---|
| `ix_sales_sold_at` | sales and margin date filters |
| `ix_purchases_purchase_date` | purchase date filters |
| `ix_returns_returned_at` | returns date filters |
| `ix_sale_items_medicine_id` | sales/margin grouping join |
| `ix_purchase_items_medicine_id` | purchase grouping join |
| `ix_batches_medicine_expiry` | expiry filter and grouping |

Adding an index "for performance" without a slow query to point at is guesswork, and
every index costs write throughput.

### One dialect-aware spot

`_time_label` uses `strftime` for `day` / `month` bucketing — SQLite's function. MySQL
spells it `date_format`. SQLAlchemy passes either through unchanged, so **this is the
one place in the repository that is dialect-specific**, and the one thing to check when
the MySQL-backed test suite lands. Everything else is portable SQLAlchemy Core.

---

## Memory

### Scope

Every memory is written and read under a `MemoryScope`. Today a scope is **one
conversation**: a fact learned in thread A is invisible from thread B.

The filter is applied on **both write and read**. Filtering only on read would put one
scope's rows physically in another's result set and rely on a query parameter to hide
them; tagging on write means isolation survives a mistake at the read end.

`MemoryScope` is a small object rather than a bare `thread_id` string on purpose. It has
one field now and gains `business_id` when authentication supplies a real identity —
`as_filter()` is then the only place that changes, instead of every call site.

> **A note on the roadmap wording.** The Milestone-1 audit recorded B1 as
> *"cross-conversation memory does not work"*, treating cross-conversation recall as the
> goal. This milestone implements the opposite reading — thread isolation as an explicit,
> tested guarantee. Both cannot be true at once, and the distinction matters: **until
> auth exists there is no identity above the conversation**, so genuine
> cross-conversation recall is not merely unimplemented, it is not expressible. Calling
> the current store "long-term memory" overstates it; it is durable *per-conversation*
> memory. The extension point is ready for when identity arrives.

### The write policy

`app/ai/memory/memory_policy.py`. The extractor **proposes**; the application
**decides**. Previously whatever the model returned was written verbatim and
permanently — the model authorising its own writes.

Three deterministic gates plus a duplicate check:

| Gate | Rule | Why |
|---|---|---|
| Confidence | `>= 0.8` | The QA pass saw an off-topic election remark stored at **0.7** and genuine facts at **0.9**. The threshold sits above the measured false positive and below the measured true positives — taken from behaviour, not picked for looking round |
| Category | one of `business` · `preference` · `goal` · `constraint` | `category` is free text from the model; an allowlist stops a newly invented category silently becoming a new class of stored data |
| Shape | 10–500 characters, non-blank | Junk is junk whatever its confidence |
| Duplicate | normalized exact match within the scope | Restatements across turns would otherwise accumulate |

Normalization lowercases, collapses whitespace and strips trailing punctuation, so
`"I prefer monthly reports."` and `"i prefer  monthly reports"` are one memory.

**Honest limit:** this catches restatements, not paraphrase. *"Monthly reporting is my
preference"* is a different string and will be stored separately. Catching it needs
embedding similarity — recorded as future work rather than pretended, and pinned by
`test_semantic_paraphrase_is_not_caught`.

Rejections are logged with their reason (never the fact text — that is user content), so
*"why doesn't it remember that?"* has an answer in the logs. A gate that drops data
silently is indistinguishable from a broken gate.

The extraction prompt also now forbids storing **any figure from a report**. Business
numbers change with every sale, so a stored figure becomes a confident lie immediately —
and a figure captured from one period can be recalled as describing another, which is
exactly what happened in the QA pass.

---

## Dead state removed

`BusinessState` carried three fields that no node ever wrote. Verified by
repository-wide search before removal, and pinned by `test_the_dead_state_fields_are_gone`.

| Field | Why it was dead | Where it went |
|---|---|---|
| `errors` | Declared `list[str]`, never appended to — and with no reducer it would have overwritten rather than accumulated had two nodes ever tried | Per-query failures already travel inside `business_metrics` as `{"error": …}`, which is where the analyzer looks |
| `execution_time_ms` | No node set it; the service measured the wall clock itself and its "fallback" always shipped | Computed in the service, which is where the information exists |
| `agent_version` | No node set it; it is a property of the deployed graph, not of one run | `AGENT_VERSION` in `app.ai.graphs.business_graph`, now `business-agent-v2` |

The API response still returns `execution_time_ms` and `agent_version` — unchanged
contract, but they are now real values rather than defaults standing in for state
nobody populated.

The bar for state: **every field is written by at least one node and read by at least
one other.** A field nobody writes reads like a promise and silently supplies a default.

---

## Observability

Every query logs its *shape*, never its rows:

```text
tool_completed  [req=abf7bf66ee16 run=8505267168d7] tool=sales_by_product_last_month duration_ms=41.2 status=success
memory_rejected [req=…] reason=confidence_below_threshold category=preference confidence=0.7
memory_persisted[req=…] proposed=2 stored=1 rejected=1
```

The tool name is the query key, so a log line says which metric over which window was
slow or failed. Figures and fact text never reach a log sink — see
`docs/observability.md`.

---

## Known limitations

| Gap | Status |
|---|---|
| No `category` dimension | Needs a schema change and migration |
| Paraphrase deduplication | Deterministic normalization only; needs embedding similarity |
| Cross-conversation memory | Not expressible until auth provides an identity above the conversation |
| Naive timestamps assume app and DB share a timezone | True today; revisit when hosts are split |
| `strftime` is SQLite-specific | The one dialect-aware call; MySQL needs `date_format` |
| No customer-level analysis | `sales.customer_id` exists but is unused by any metric |
| `expiry` has no "expiring soon" window | Deliberately left to the Expiry-Risk agent |
| Golden set grades pipeline, not model routing, in fake mode | `--real` grades routing; see `docs/testing.md` |
