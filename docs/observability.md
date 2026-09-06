# Observability

> How to follow one request through the whole system: HTTP → service → graph → nodes →
> tools → LLM → response. What each identifier means, what gets logged, how to turn
> LangSmith on, and what must never reach a log.

---

## The three identifiers

Confusing these is the most common mistake in agent systems, so they are kept
deliberately separate.

| Identifier | Answers | Lifetime | Created by |
|---|---|---|---|
| `request_id` | *Which HTTP call was this?* | One inbound request | `RequestContextMiddleware` |
| `thread_id` | *Which conversation was this?* | Many requests, over days | The **client**, sent in the request body |
| `run_id` | *Which graph execution was this?* | One `graph.invoke()` | The service, via `ai_run()` |

The relationships:

```text
thread_id  "conv-8f3a"          one conversation
   ├── request_id  "abf7bf66"   ── run_id "85052671"   turn 1
   ├── request_id  "0f4b4919"   ── run_id "1013c0e4"   turn 2
   └── request_id  "ad152fe4"   ── run_id "3bbee09a"   turn 3
```

- One `thread_id` has **many** `request_id`s — that is what conversation memory means.
- Each AI request has **exactly one** `run_id`.
- A non-AI request (listing medicines) has a `request_id` and **no** `run_id`; it logs
  `run_id=-`.
- `thread_id` is *logged as a field*, never bound to the context — binding it would
  invite exactly the conflation this table exists to prevent.

`request_id` and `run_id` live in `ContextVar`s (`app/core/context.py`), which are
task-local. Two concurrent requests cannot see each other's ids; a module-level global
would have leaked them under load, which is the worst kind of bug to debug.

---

## A real trace

Actual output from `POST /api/v1/business/analyze`:

```text
22:08:24 INFO  app.tracing  tracing_status    [req=-            run=-           ] tracing_enabled=False api_key_present=True
22:08:25 INFO  app.ai       ai_run_started    [req=abf7bf66ee16 run=8505267168d7] agent=business thread_id=conv-demo-1
22:08:25 INFO  app.ai       node_completed    [req=abf7bf66ee16 run=8505267168d7] node=memory_retriever duration_ms=0.0
22:08:25 INFO  app.ai       node_completed    [req=abf7bf66ee16 run=8505267168d7] node=planner   duration_ms=0.1
22:08:25 INFO  app.ai       tool_completed    [req=abf7bf66ee16 run=8505267168d7] tool=margin    duration_ms=41.2 status=success
22:08:25 INFO  app.ai       tool_completed    [req=abf7bf66ee16 run=8505267168d7] tool=sales     duration_ms=49.7 status=success
22:08:25 INFO  app.ai       tool_completed    [req=abf7bf66ee16 run=8505267168d7] tool=expiry    duration_ms=44.3 status=success
22:08:25 INFO  app.ai       node_completed    [req=abf7bf66ee16 run=8505267168d7] node=fetcher   duration_ms=58.3
22:08:25 INFO  app.ai       node_completed    [req=abf7bf66ee16 run=8505267168d7] node=analyzer  duration_ms=0.2
22:08:25 INFO  app.ai       node_completed    [req=abf7bf66ee16 run=8505267168d7] node=reflector duration_ms=0.1
22:08:25 INFO  app.ai       node_completed    [req=abf7bf66ee16 run=8505267168d7] node=finalizer duration_ms=0.1
22:08:25 INFO  app.ai       ai_run_completed  [req=abf7bf66ee16 run=8505267168d7] duration_ms=122.8
22:08:25 INFO  app.http     request_completed [req=abf7bf66ee16 run=-           ] method=POST status_code=200 duration_ms=132.8
```

Read it: three tools took 41 + 50 + 44 ms of work but the fetcher node took 58 ms —
they genuinely ran in parallel. One `grep abf7bf66ee16` returns the whole story.

`request_completed` shows `run_id=-` because the run has already finished and unbound
its id by the time the middleware logs the response. That is correct: the run is over.

---

## Events

Stable `snake_case` names with the variable parts in `extra`. Interpolated prose is
readable once and greppable never.

| Event | Level | Key fields |
|---|---|---|
| `request_completed` | INFO / WARNING (4xx) / ERROR (5xx) | `method` `path` `status_code` `duration_ms` |
| `request_failed` | ERROR + traceback | `method` `path` `error_type` `duration_ms` |
| `ai_run_started` | INFO | `agent` `thread_id` |
| `ai_run_completed` | INFO | `agent` `thread_id` `duration_ms` |
| `ai_run_failed` | ERROR + traceback | `agent` `error_type` `duration_ms` |
| `node_started` | DEBUG | `agent` `node` |
| `node_completed` | INFO | `agent` `node` `duration_ms` |
| `node_failed` | ERROR + traceback | `agent` `node` `error_type` `duration_ms` |
| `tool_started` | DEBUG | `tool` |
| `tool_completed` | INFO | `tool` `duration_ms` `status` |
| `tool_failed` | WARNING | `tool` `error_type` `duration_ms` |
| `llm_completed` | INFO | `model` `duration_ms` `prompt_tokens` `completion_tokens` `total_tokens` |
| `llm_failed` | WARNING | `error_type` `duration_ms` |
| `llm_client_created` | INFO | `provider` `model` |
| `tracing_status` | INFO | `tracing_enabled` `project` `api_key_present` |

`node_started` / `tool_started` are DEBUG so the default INFO stream stays one line per
completed step. Set `LOG_LEVEL=DEBUG` when you need the start of a step that never
finished.

`/health` is not logged — it is polled constantly and would drown everything else.

---

## Where instrumentation lives

```text
app/core/context.py          ContextVars for request_id / run_id, and bind_context()
app/core/logging_config.py   formatters + configure_logging() + record factory
app/core/middleware.py       RequestContextMiddleware — request id, timing, access log
app/core/tracing.py          LangSmith status reporting
app/ai/observability.py      ai_run() · observe_node() · observe_tool() · LLM callback
```

Nodes and tools carry **no** logging code. Node instrumentation is applied where the
graph is assembled (`business_graph.py`), so what is instrumented is readable in one
place and node modules stay about their own logic.

Everything is additive: every wrapper logs and re-raises. No wrapper swallows an
exception or alters a return value, so instrumenting a node cannot change what the
graph does.

### Threads

The BI fetcher runs its tools in a `ThreadPoolExecutor`, and a worker thread starts
with an empty context. Work handed to a thread must be wrapped:

```python
executor.submit(bind_context(execute_tool, task))
```

`bind_context` copies the context **on the calling thread** and returns a zero-argument
callable. That signature is deliberate: it makes it impossible to defer the copy into
the worker by accident, which is a bug that produces `request_id=-` on exactly the
lines you most need correlated. (It was written that way after the first version got
it wrong and a test caught it.)

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` adds `node_started` / `tool_started` |
| `LOG_FORMAT` | `console` | `console` = aligned and readable · `json` = one object per line |

```powershell
$env:LOG_LEVEL="DEBUG"; $env:LOG_FORMAT="json"; uvicorn app.main:app --reload
```

Both formats carry the same fields, so a query written against one still makes sense in
the other. JSON output is validated line-by-line by the test suite.

---

## LangSmith

### The trap

**An API key alone does nothing.** Verified against the installed `langsmith` 0.8.x,
not assumed — `langsmith.utils.tracing_is_enabled()` ends with:

```python
get_env_var("TRACING_V2", default=get_env_var("TRACING", default="")) == "true"
```

and `get_env_var` searches the namespaces `("LANGSMITH", "LANGCHAIN")` in order. So
tracing turns on when **any** of these is exactly the string `"true"`:

```text
LANGSMITH_TRACING_V2 · LANGCHAIN_TRACING_V2 · LANGSMITH_TRACING · LANGCHAIN_TRACING
```

The comparison is exact — no case-folding, no trimming. `"TRUE"`, `"1"` and `"yes"` all
silently leave tracing **off**.

This project had `LANGCHAIN_API_KEY` and `LANGCHAIN_PROJECT` set, no flag, and therefore
produced **zero traces** while `docs/04` recorded tracing as "configured". Hence the
startup report below: the misconfiguration now announces itself on every boot.

### Enabling it

In `pharmacy-core-backend/.env`:

```text
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your key>
LANGSMITH_PROJECT=ai-pharmacy-ecosystem
```

Restart, and check the first two log lines:

```text
INFO  app.tracing  tracing_status  tracing_enabled=True project=ai-pharmacy-ecosystem api_key_present=True
```

If instead you see this, the key is set but nothing is being sent:

```text
INFO     app.tracing  tracing_status                    tracing_enabled=False api_key_present=True
WARNING  app.tracing  tracing_disabled_despite_api_key  hint=set LANGSMITH_TRACING=true in .env
```

`get_env_var` is `lru_cache`d, so the environment must be populated before the first
LangChain call. `app.ai.config` and `app.core.database` both load `.env` at import,
which happens during app import — that ordering is load-bearing, so do not move the
`.env` load later.

### Verification status

| Check | Status |
|---|---|
| Correlation ids present and propagated through nodes, tools and threads | **PASS** — asserted by tests, shown in the smoke run above |
| Node / tool / run timings emitted | **PASS** |
| Tracing flag logic matches the installed library | **PASS** — 17 offline unit tests |
| Startup correctly reports this project's real (disabled) state | **PASS** |
| Traces actually arriving in a LangSmith project | **NOT RUN — requires credentials** |

The last row needs a real API key and a dashboard, so it cannot be verified here. The
app tells you which state it is in; confirming delivery is a manual step once a key is
set.

---

## Security: what must never be logged

Never log, and currently never logged:

- API keys, tokens, passwords, `Authorization` headers
- Full prompts or LLM completions
- User questions (they contain business data — `test_logs_do_not_leak_the_question_or_api_key` asserts this)
- Tool arguments and tool results (a business tool returns real pharmacy figures)
- Whole database rows

Log instead: identifiers, counts, durations, status, error **types**.

Two specific protections:

- **`X-Request-ID` is validated.** An inbound header reaches log sinks, so it is
  untrusted input. Only `[A-Za-z0-9_-]{1,64}` is honoured; anything else — newlines
  that would forge a second log line, terminal escape sequences, unbounded values — is
  replaced with a generated id.
- **The LangSmith key is never returned or logged.** `tracing_status()` reports
  `api_key_present: True/False` and never the value.

Prompts and completions belong in LangSmith, which is access-controlled, not in
application logs.

---

## Token usage and cost

`LLMObservabilityHandler` records `model`, `duration_ms`, and token counts **only when
the provider actually returns them**. There is no estimation and no tokenizer fallback:
an invented number in a cost dashboard is worse than an absent one.

There is deliberately no cost calculation yet — that needs per-model pricing that
changes, and belongs with a real cost milestone.

---

## Testing

38 tests cover this, all offline — none contacts LangSmith:

```powershell
pytest tests/unit/test_observability_context.py   # 14 — ids, isolation, threads, formatters
pytest tests/unit/test_tracing_config.py          # 17 — flag logic, secret redaction
pytest tests/integration/test_observability.py    # 21 — full-chain correlation, failures
```

Assertions target event names and field presence, never exact rendered strings — a
formatter tweak should not fail a behavioural test.

---

## Known limitations

| Gap | Why |
|---|---|
| LangSmith delivery unverified | Needs a real credential and a dashboard |
| No metrics backend | No Prometheus/OTel. Logs first; a metrics story needs a deployment target to ship to |
| No log aggregation | JSON output is ready for a shipper; there is no shipper because there is no deployment yet |
| `request_completed` logs the raw path, not the route template | The matched route is not known at middleware level. High-cardinality paths are a field, not part of the event name, so they do not fragment queries |
| Billing and reorder graph nodes are not individually instrumented | Only their `ai_run` boundary is. The BI agent is the roadmap priority; extend `observe_node` to the others when they are worked on |
| No cost tracking | Deliberate — see above |
| SQL timing is per-tool, not per-query | Verbose SQL logging is off by default; query-level analysis belongs with a performance milestone |
