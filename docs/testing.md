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
pytest tests/evaluation         # BI golden set
pytest -m known_gap             # only the tests that pin known defects
pytest -k margin                # by name
```

The human-readable evaluation report:

```powershell
python -m tests.evaluation.runner          # fake LLM — free, offline, deterministic
python -m tests.evaluation.runner --real   # real provider — costs money
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
`FakeMemoryRepository` reproduces the real `thread_id` filter on both read and write — the
filter is the subject of a known-gap test, so the fake must not quietly "fix" it.

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

## The golden set

`tests/evaluation/golden_cases.json` — 15 cases across sales, purchases, returns, expiry,
margin, business health, off-topic, unsupported and action-request.

**What it measures, and what it does not.** In the default fake-LLM mode the planner is
*scripted* from each case's `planned_capabilities`. The harness therefore does not grade
the model's routing — it grades the pipeline around it:

- the plan is honoured by the fetcher (`set(metrics) == set(plan)`)
- no tool silently failed
- an answer exists, with confidence in `[0, 1]`
- the reflection loop stayed inside `MAX_REFLECTIONS`

That is a real regression suite for the graph, and it is honest about not being a model-
quality benchmark. `--real` grades the planner's own routing against
`planned_capabilities`.

Cases marked `requires_real_llm` depend on model judgement — refusing an action, admitting
missing data. They are **skipped** in fake mode and reported as skipped, never counted as
passes.

Every case must be answerable by the capabilities that exist **today**. A case demanding
date filtering or per-product ranking would fail forever and train everyone to ignore a red
suite; `test_no_case_asks_for_a_capability_that_does_not_exist` enforces this.

There is deliberately **no LLM-as-judge yet**. Deterministic checks first; a judge is worth
adding once there is something it can grade that these checks cannot.

### Adding a case

1. Append to the `cases` array in `golden_cases.json`; keep ids sequential, never reuse one.
2. Confirm the current repository can actually serve it.
3. Set `expected_behavior` to `answer_from_business_data` or `no_business_data_needed`; if
   the check is about model judgement, set `requires_real_llm: true`.
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

Currently pinned: **B1** thread-scoped memory · **B3** no date filtering · **B4** no memory
confidence gate · **B10** no grouping/ranking · dead `agent_version` state field.

---

## Layout

```text
tests/
├── _environment.py          env override; imported before any `app` import
├── conftest.py              fixtures: engine, clean_database, db_session, fake_llm, client
├── fakes.py                 FakeLLM, FakeMemoryRepository
├── factories.py             the fixed scenario + EXPECTED figures
├── unit/                    104 tests — repository, tools, nodes, reorder maths,
│                                       correlation context, tracing config
├── integration/             49 tests — full graph, HTTP endpoint, observability chain
└── evaluation/              16 tests — golden set + harness self-checks
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
| Billing and reorder graphs untested | Only `reorder_tools` maths is covered. Both agents work and are lower-priority per the roadmap |
| Native tool-calling graph untested | `FakeLLM.bind_tools` intentionally raises; add binding support when that graph is covered |
| No coverage measurement | `pytest-cov` not added — a number nobody acts on is not worth a dependency yet |
| `StarletteDeprecationWarning` from `TestClient` | Starlette wants `httpx2`; harmless, revisit on the next dependency bump |
