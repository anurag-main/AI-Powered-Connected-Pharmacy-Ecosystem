# Testing & Evaluation

> How the suite is built, how to run it, and how to extend it.
> Everything lives under `pharmacy-core-backend/tests/`.

---

## Running

All commands from `pharmacy-core-backend/`, PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

pytest                          # everything
pytest tests/unit               # fast, no I/O beyond SQLite
pytest tests/integration        # graph + HTTP boundaries
pytest tests/evaluation         # BI + expiry golden sets
pytest -m known_gap             # only the tests that pin known defects
pytest -k margin                # by name
```

The human-readable evaluation report:

```powershell
python -m tests.evaluation.runner                 # BI set, fake LLM, offline
python -m tests.evaluation.runner --real          # BI set against a real provider
python -m tests.evaluation.expiry_runner          # expiry set, fake LLM, offline
python -m tests.evaluation.expiry_runner --real   # expiry set against a real provider
```

No test makes a network call. `pytest` needs no API key and no MySQL.

---

## Test database

A temporary **file-based SQLite** database in the OS temp directory, created once per
session and deleted at the end.

`tests/_environment.py` rewrites `DATABASE_URL` **before anything under `app` is
imported**, so `app.core.database` builds its one process-wide engine against that temp
file. There is no code path back to the developer's MySQL, and
`assert_not_production_database()` aborts the run if the URL is ever not SQLite. The real
`.env` is never modified.

**Why a file and not `sqlite://`** — an in-memory SQLite database belongs to a single
connection. The app engine and the test engine would each get their own empty copy, and
the BI fetcher runs its tools in a `ThreadPoolExecutor`, i.e. on other connections again.
A file is shared by every connection and thread with no pool trickery.

**Why `drop_all` / `create_all` per test** — the usual trick of wrapping each test in a
rolled-back transaction only isolates a *single* session, and the graph opens its own on
worker threads, which would not see uncommitted rows. Rebuilding ten SQLite tables costs
single-digit milliseconds.

**Schema comes from `Base.metadata`, not Alembic.** The suite tests application
behaviour, not the migration chain — see *Known debt* below.

---

## Fake LLM

Every BI node calls `get_llm().with_structured_output(Schema).invoke(messages)`. Left
alone, the suite would make real OpenAI calls: slow, costly, and non-deterministic, so no
assertion about the graph could ever be stable.

`tests/fakes.py::FakeLLM` implements only the slice of `BaseChatModel` the nodes touch and
answers **by schema class**, because that is how a node identifies what it wants — the
planner asks for a `PlannerOutput`, the analyzer for a `BusinessAnalysis`:

```python
def test_something(fake_llm):
    fake_llm.responses[PlannerOutput] = PlannerOutput(tasks=["sales", "margin"])
    ...
    assert fake_llm.call_count(PlannerOutput) == 1
```

A response may be an object, or a callable receiving the messages — the callable form lets
one test vary the answer per turn (reflector unsatisfied first pass, satisfied next).
Asking for an unscripted schema raises a named `AssertionError` rather than returning
`None`, so a node reaching for something the test did not anticipate fails loudly.

Setting `fake_llm.error` makes every call raise — that is how the provider-outage tests
work.

> **Patching note.** Each node did `from app.ai.llm import get_llm`, which binds the
> function *by value* into that module's namespace. Patching `app.ai.llm.get_llm` alone
> would not reach them, so the `fake_llm` fixture patches each node module individually.
> The list is `_LLM_NODE_MODULES` in `conftest.py` — **add to it when a new node calls an
> LLM**, or that node will hit the real provider.

`fake_llm` is deliberately **not** autouse: a test needing an LLM should say so.

## Fake memory store

`fake_memory` **is** autouse. The cost of forgetting it is that a test writes junk into the
developer's real ChromaDB store at `memory_db/` and bills real embedding calls to do it.
`FakeMemoryRepository` enforces `MemoryScope` filtering on both read **and** write, exactly
as the real store does — scope isolation is the property under test, so a fake that quietly
returned everything would make those tests meaningless.

---

## Test data

`tests/factories.py` holds **one fixed scenario**: 2 medicines, 3 batches (one expired),
2 sales, 2 purchases, 3 returns. Small enough that every expected metric is worked out by
hand and written into the test as a literal — a test that computes its own expectation
cannot catch a bug in the code that computes it.

The derived figures live in `EXPECTED`, so tests and the harness share one source of
truth. Every money value is binary-exact as a float, so SQLite's lack of native `DECIMAL`
cannot introduce rounding noise.

Fixtures: `db_session` (raw session) · `seeded_db` (scenario loaded) · `seeded_app_db`
(same data, for code that opens its own session — the BI tools do).

---

## The golden sets

Two, with different powers.

**BI** (`golden_cases.json`, 33 cases) grades the *pipeline*, because the BI agent's
answers depend on what the model decides to fetch.

**Expiry** (`expiry_risk_cases.json`, 16 cases) grades *actual computed values* — excess
counts, rupees at risk, which batch ranks first. That is only possible because the expiry
calculation is deterministic: given the same stock and sales, the report is byte-identical
however the model phrases it. It is a correctness suite, not just a plumbing check.

### The BI set

`tests/evaluation/golden_cases.json` — 33 cases across sales, purchases, returns, expiry,
margin, business health, date filtering, ranking, grouping, combined queries, off-topic,
unsupported and action-request.

**What it measures, and what it does not.** In the default fake-LLM mode the planner is
*scripted* from each case's `planned_queries`. The harness therefore does not grade the
model's routing — it grades the pipeline around it:

- the plan is honoured by the fetcher, key for key
- no query silently failed
- **every result carries the period it covers** — the hole that let an all-time total be
  reported as "last month"
- an answer exists, with confidence in `[0, 1]`
- the reflection loop stayed inside `MAX_REFLECTIONS`

Period cases are graded on whether the period was applied and reported, **not** on which
rows came back: the seeded scenario sits at fixed dates, so asserting row contents would
tie the suite to the calendar. Date-boundary values are asserted against explicit ranges in
`tests/unit/test_business_repository.py` instead.

That is a real regression suite for the graph, and it is honest about not being a model-
quality benchmark. `--real` grades the planner's own routing against
`planned_queries`.

Cases marked `requires_real_llm` depend on model judgement — refusing an action, admitting
missing data. They are **skipped** in fake mode and reported as skipped, never counted as
passes.

Every case must be answerable by the capabilities that exist **today**. A case demanding a
category breakdown would fail forever and train everyone to ignore a red suite;
`test_every_planned_query_is_valid` enforces this by constructing each case's queries
through the same `BusinessQuery` validation the planner faces.

There is deliberately **no LLM-as-judge yet**. Deterministic checks first; a judge is worth
adding once there is something it can grade that these checks cannot.

### Adding a case

1. Append to the `cases` array in `golden_cases.json`; keep ids sequential, never reuse one.
2. Confirm the current repository can actually serve it.
3. Set `expected_behavior` to `answer_from_business_data` or `no_business_data_needed`; if
   the check is about model judgement (refusal wording, admitting missing data), set
   `requires_real_llm: true`.
4. Run `pytest tests/evaluation`.

A new `expected_behavior` value needs a matching branch in `runner.check_state`.

---

## Marking known defects

Tests marked `@pytest.mark.known_gap` pin **current** behaviour that a later milestone will
change. They assert what the system does today and carry a message telling the future
reader what to do when it changes:

```python
assert result["retrieved_memories"] == [], (
    "Cross-conversation recall now works — B1 is fixed. Replace this gap test "
    "with an assertion that the fact IS recalled."
)
```

This keeps the suite green while making the defect impossible to forget: fixing B1 turns
that test red, and the failure message says exactly what to do. Run `pytest -m known_gap`
to list them.

Milestone 3 cleared most of these. **B3** (date filtering), **B4** (confidence gate),
**B5** (deduplication), **B10** (grouping/ranking) and the dead `agent_version` field are
fixed, and each gap test was replaced by a test of the new behaviour rather than deleted.
**B1** was reinterpreted as a guarantee — thread isolation is now asserted, not pinned as a
defect; see `docs/business_queries.md`.

Currently pinned: no `category` dimension (needs a schema change) · semantic paraphrase is
not deduplicated (needs embeddings).

---

## Layout

```text
tests/
├── _environment.py          env override; imported before any `app` import
├── conftest.py              fixtures: engine, clean_database, db_session, fake_llm, client
├── fakes.py                 FakeLLM, FakeMemoryRepository
├── factories.py             the fixed scenario + EXPECTED figures
├── unit/                    431 tests — BI repository + query validation + period
│                                       resolution, expiry risk service + repository +
│                                       query, tools, nodes, memory policy, reorder
│                                       maths, correlation context, tracing config
├── integration/             72 tests — BI graph, expiry graph, HTTP endpoints,
│                                       observability chain
└── evaluation/              57 tests — BI + expiry golden sets, harness self-checks
    ├── golden_cases.json
    ├── runner.py            also runnable as `python -m tests.evaluation.runner`
    └── test_bi_golden_cases.py
```

Most tests are unit tests. Integration tests cover boundaries that unit tests cannot: the
compiled graph, the checkpointer, the thread pool, and HTTP validation.

---

## Observability tests

`configure_logging(level="DEBUG")` runs once at conftest import, before any test. It
replaces the root handlers, so letting it run lazily on the first `app.main` import
would rip out pytest's `caplog` handler mid-test.

The record factory it installs is what puts `request_id` / `run_id` onto `caplog`'s
records — a handler *filter* would only stamp records reaching our own handler, and
`caplog` uses its own. Details in `docs/observability.md`.

Observability assertions target event names and field presence, never exact rendered
strings, so a formatter tweak does not fail a behavioural test.


## Known debt

| Gap | Why it is not done yet |
|---|---|
| Migrations are untested | Schema is built from `Base.metadata`. Testing the Alembic chain properly needs a MySQL container — belongs with the Docker milestone |
| SQLite is not MySQL | No coverage of MySQL-specific behaviour (`CHECK` enforcement, collation, `(CURRENT_DATE)` defaults). A small MySQL-backed suite belongs with Docker |
| Billing / reorder graphs and the billing + sales UI untested | Only `reorder_tools` maths is covered on the backend; on the frontend only the expiry page has tests. Both are lower-priority per the roadmap |
| `strftime` in time breakdowns is SQLite-specific | Passes on SQLite; MySQL needs `date_format`. The one dialect-aware call, and the first thing to check when a MySQL-backed suite lands |
| Native tool-calling graph untested | `FakeLLM.bind_tools` intentionally raises; add binding support when that graph is covered |
| No coverage measurement | `pytest-cov` not added — a number nobody acts on is not worth a dependency yet |
| `StarletteDeprecationWarning` from `TestClient` | Starlette wants `httpx2`; harmless, revisit on the next dependency bump |


## Frontend tests

The backend suite above is `pharmacy-core-backend`. The frontend has its own, smaller
suite in `pharmacy-frontend`.

```powershell
cd pharmacy-frontend
npm test            # vitest run
npm run test:watch  # vitest
```

```text
tests/
├── setup.js                 jest-dom matchers; stubs global fetch to THROW by default
├── helpers.js               response fixtures + the fetch mock
└── expiry-page.test.jsx     22 tests over pages/expiry.jsx
```

**Stack:** Vitest 5 + React Testing Library 16 + jsdom. `vitest.config.mjs` sets the
jsdom environment and mirrors the `@` alias from `jsconfig.json`, so imports resolve
the same way `next build` resolves them.

**Next.js is not involved.** Pages are imported and rendered as plain React
components, which works because every page here keeps its shell in a `getLayout`
static instead of wrapping itself. No router, no font loader, no `_app`.

**The mock boundary is `fetch`, deliberately.** Mocking our own `getExpiryReport`
would skip `lib/api/expiry.js` (`toQuery`) and `lib/api/client.js` (status-to-message
mapping, `X-Request-ID`) — the two places a frontend bug actually hides. Mocking
`fetch` keeps both under test and lets the parameter tests assert the real URL,
method and body.

`setup.js` installs a `fetch` stub that throws. A test that forgets to script a
response fails loudly rather than reaching FastAPI, MySQL or OpenAI.

### What is covered

Only the expiry page today: loading, success, empty, error, request parameters, and
that backend values are displayed unchanged. The billing and sales pages have no
tests yet.

These assert **display**, never business logic. Whether excess or value at risk is
*correct* belongs to the backend's 196 expiry tests; the frontend tests prove the UI
asks the right question and prints the answer it was given.

### Known debt

| Gap | Why |
|---|---|
| Billing and sales pages untested | Expiry was the milestone; these follow with their own feature work |
| No component-level tests | Components are exercised through the page, which is where the behaviour is visible. Isolated tests would add count, not confidence |
| No coverage measurement | Same reasoning as the backend — a number nobody acts on is not worth a dependency |
