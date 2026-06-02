# AI Pharmacy Ecosystem — Learning Notes

> Append-only running log of every concept, analogy, production lesson, beginner mistake, and interview-gold question covered in this project. Read this any time as a revision / interview-prep document.
>
> **Diagrams live in [`diagrams.md`](diagrams.md)** — this file is for the written explanations.

---

## How to use this file
- Each entry: **Concept → Analogy → Production reasoning → 3 beginner mistakes → Interview gold** (where applicable).
- New entries are **appended**, never edited. Older notes stay as-is for revision.
- Glossary at the bottom — new acronyms get a row.

---

## Phase 0 — Foundation

### Why Phase 0 exists at all
**Analogy:** Phase 0 is laying the foundation of a pharmacy building **before** stocking medicines. You don't put medicines on a half-finished floor.

**Production reasoning:** Framework (`CLAUDE.md`, agents, hooks, skills) + Git history + folder layout + `venv` + `.env` pattern — all locked **before** a single line of business code. Skipping this means paying tax later: leaked secrets, broken imports, junk files in Git history.

### Sub-step 0.3 — write `.gitignore` BEFORE the first `git add`
**Why the order matters:** Once `__pycache__/`, `venv/`, or `.env` enters Git history, removing it requires `git filter-repo` + force-push — a destructive operation that breaks every teammate's clone. Write `.gitignore` first, **then** stage anything.

### `.env` vs `.env.example` — the two-file pattern
**Analogy:** `.env` = the **cash safe** (locked, never shared, gitignored). `.env.example` = the **receipt template** (public, shows the *shape* of what's expected, committed).

**Production reasoning:** New teammate clones the repo → `.env.example` tells them what env vars to fill in. The real `.env` (with secrets) never leaves your laptop.

### 3 classic Phase 0 mistakes
1. **`git init` after files already exist** → first commit accidentally includes `.env` with real DB password. Hours to clean up; on a public repo, you must assume the secret is leaked forever and rotate it.
2. **One global Python instead of per-project `venv`** → installing a package upgrades it for *every* project on your laptop. "Works on my machine" hell.
3. **One `.env`, no `.env.example`** → teammate clones, app crashes with `KeyError: 'DATABASE_URL'`, zero documentation of which keys are required.

---

## Phase 1 — FastAPI 3-layer architecture (the heart of the entire backend)

### The 3-layer pattern: router → service → repository
**Analogy:** Pharmacy reception → pharmacist → storeroom clerk. Three different people, three different jobs, deliberately separated.

| Layer | Pharmacy role | Does | Must NOT do |
|-------|---------------|------|-------------|
| **Router** | Reception desk | Accept HTTP, run Pydantic validation, call service, return response | Touch storage, run business rules, format prices |
| **Service** | Pharmacist | Business rules (deduplication, FEFO, price calc), normalize input | Know about SQL, HTTP status codes, or JSON |
| **Repository** | Storeroom clerk | Save/fetch by exact criteria. Today in-memory dict; Phase 2 MySQL | Decide *whether* to save. Reject duplicates. Compute prices. |
| **Pydantic schemas** | Prescription forms | Reject invalid input before it reaches the service | Talk to DB, run business logic |

**The killer test:** *"If I swap MySQL for PostgreSQL in Phase 2, how many files do I edit?"* — Properly 3-layered app: **one** (the repository). Beginner app: **all of them**.

### The "reason to change" principle (Single Responsibility Principle)
A file should change for **one reason only**.
- Repository changes when *storage* changes (in-memory → MySQL → Postgres).
- Service changes when *business rules* change (allow duplicates? new tax rule?).
- Router changes when *HTTP shape* changes (new endpoint, new response code).

Mixing reasons in one file = every change touches multiple files = no fast tests = bugs ship.

### Where the duplicate-detection rule lives: Service, NOT Repository
**Why:** Repository = storeroom clerk (no opinions, just fetches). Service = pharmacist (decides *what counts as the same thing*).

**Analogy — WhatsApp contacts:** You save "Mom". Then "MOM " comes in. The phone's storage chip just stores bytes — no opinion. The **WhatsApp app code** normalized, checked, and warned "duplicate". If storage decided, every app on your phone would have a different definition of "duplicate" → chaos.

**Concrete flow for `"Crocin 500MG "` vs `"Crocin 500mg"`:** *(see diagram: "Duplicate-detection flow" in diagrams.md)*
1. Router gets input → hands to Service
2. Service normalizes name → `"crocin 500mg"`
3. Service asks Repo: `find_by_normalized_name("crocin 500mg")`
4. Repo returns existing record (just fetches, no opinion)
5. Service raises `DuplicateMedicineError`
6. Router catches → returns HTTP **409 Conflict**

### Defense-in-depth note (Phase 2 preview)
The DB's `UNIQUE` constraint is a *safety net*, **not** the primary check. Primary check lives in the service (clean error message, friendly response). DB constraint catches the rare race condition.

### 3 beginner mistakes in 3-layer architecture
1. **SQL inside the router** → untestable without a real DB; bypasses cache when added in Phase 6 → stale data → expired batch sold to customer.
2. **Returning the DB model directly as the API response** → leaks internal fields (`cost_price`, `password_hash`). Famous breach pattern.
3. **Hardcoding the repo in the service constructor** instead of using `Depends()` → can't swap a fake repo for tests; connection leaks in prod → DB runs out of connections at 2 AM.

### Interview gold
**Q:** *"Why do you need uvicorn if you already have FastAPI?"*
**A:** FastAPI is the **framework** — defines *how* to handle requests. Uvicorn is the **server** — actually *receives* them from the OS network stack. FastAPI alone can't open a socket. Same split as Express ↔ Node, Spring ↔ Tomcat.

---

## Step 1.1 — venv + install fastapi / uvicorn / pydantic

### Concept: virtual environment (`venv`)
**Analogy:** A **sealed dispensing tray**. Only this pharmacy's tools/ingredients go inside. The tray next door (other Python projects) is untouched.

**Production reasoning:** Isolation per project. `venv/` itself is recreatable from `requirements.txt` (so `venv/` is gitignored; `requirements.txt` is committed).

### The 3 packages installed in Phase 1
| Package | Analogy | Real job |
|---------|---------|----------|
| `fastapi` | Reception desk **procedure manual** | Defines routes, parses HTTP, generates OpenAPI/Swagger docs, runs Pydantic validation |
| `uvicorn[standard]` | The **doorbell + intercom** | ASGI server listening on port 8000. `[standard]` adds hot-reload + websockets |
| `pydantic` | The **prescription form validator** | Defines valid request/response shapes; rejects bad data *before* it reaches service code |

### `requirements.txt` reproducibility loop
*(see diagram: "Step 1.1 — requirements.txt reproducibility loop" in diagrams.md)*

You `pip install` → `pip freeze > requirements.txt` → commit → teammate clones → `pip install -r requirements.txt` → they have the **exact same packages at exact same versions**. This is why companies don't ship `venv/` (or `node_modules/`).

### PowerShell-specific gotcha
`pip install "uvicorn[standard]"` — **quotes mandatory** in PowerShell because `[` and `]` are special characters (array indexers). Without quotes: cryptic error. Bash and CMD don't need the quotes.

### Python flag gotcha (`-v` vs `-m`)
| Flag | Meaning |
|------|---------|
| `python -m venv venv` ✅ | Run the **m**odule named `venv`, creating a venv folder |
| `python -v venv venv` ❌ | Run Python in **v**erbose mode, then try to execute a file named `venv` |

One letter apart. Completely different behavior. **Always read your flags character by character.**

### How to read scary error dumps
When a command vomits 200 lines of `import 'foo'` and `cleanup[X] removing bar`, **scroll to the bottom**. The real error is at the end. Everything above is noise (often verbose-mode output). The actual error is usually one line.

### 3 beginner mistakes in venv work
1. **Wrong activation script for your shell** (`activate.bat` vs `Activate.ps1` vs `source activate`) → looks activated but isn't → `pip install` quietly pollutes global Python.
2. **Committing the `venv/` folder** → 50MB of OS-specific binaries in Git. Won't work on Mac. Painful to remove later (rewrite history + force push).
3. **Loose version pins** in `requirements.txt` (`fastapi` without `==X.Y.Z`) → install today gets 0.115, install next year gets 0.142 → CI breaks for "no apparent reason" → dependency hell.

### Verification commands to memorize
```powershell
(Get-Command python).Source       # must point inside venv\Scripts\
python --version                  # confirm version
pip freeze                        # see exact installed versions
```

### Interview gold
**Q:** *"Why does your project commit `requirements.txt` but not `venv/`?"*
**A:** `requirements.txt` is a text file declaring *what* should be installed at *what versions*. It's portable across OS, Python versions, and machines. `venv/` is hundreds of MB of OS-specific compiled binaries — useless on a different OS, bloats the repo, slow to clone. The text file is the **source of truth**; the venv is **derived**.

---

## Step 1.2 — backend folder layout (the locked floor plan)

### Concept: layer-first folder structure
**Analogy:** A real pharmacy decides on day 1: reception by the door, dispensing counter at the back, storeroom behind dispensing, billing on the side. Moving the storeroom later = renovation, not edit. Same with code — moving folders later breaks every import in every file.

### The locked layout for `pharmacy-core-backend/`
*(see diagram: "Step 1.2 — backend folder layout" in diagrams.md)*

```
pharmacy-core-backend/
├── venv/                    # gitignored
├── requirements.txt         # committed
├── .env / .env.example      # one gitignored, one committed
└── app/
    ├── main.py              # FastAPI entrypoint
    ├── exceptions.py        # custom errors (PharmacyError + subclasses)
    ├── core/                # config, settings, security helpers
    ├── routers/             # HTTP layer (reception)
    ├── services/            # business logic (pharmacist)
    ├── repositories/        # storage access (storeroom)
    └── schemas/             # Pydantic input/output models
```

**Deliberately NOT created yet:** `models/` (SQLAlchemy ORM — Phase 2), `tests/` (when we have something to test), `utils/` (only when actually needed). **Premature folders age into junk drawers.**

### Convention: `__init__.py` in every package folder
Python won't recognize `app/routers/` as importable without `__init__.py`. Missing = `ModuleNotFoundError`. Even an empty file is fine — it's just a marker that says *"this folder is a Python package."*

### Convention: never raise built-in exceptions from business logic
Every domain error inherits from `PharmacyError`. Routers catch these and translate to specific HTTP status codes (`409` for duplicate, `404` for not found, etc). **Don't raise `ValueError` or `RuntimeError` from services** — they become opaque `500 Internal Server Error` to the client.

### 3 beginner mistakes in folder structure
1. **Flat structure** (everything at root) → works for 50 lines, breaks at 5000. By Phase 5 you'd have a 2000-line `routes.py` nobody can navigate.
2. **Missing `__init__.py`** → `ModuleNotFoundError: No module named 'app.routers'` at 11 PM. 20 minutes lost finding the typo.
3. **`tests/` inside `app/`** → tests ship in your Docker image (Phase 4) → bigger image, slower deploy, leaked test secrets. Tests are *consumers* of the app, not part of it.

### Interview gold
**Q:** *"How do you decide which folder a piece of code belongs in?"*
**A:** Apply the **"reason to change"** test. If this code would change when *storage* changes → repository. When *business rules* change → service. When *HTTP shape* changes → router. When *input validation* changes → schema. If it changes for multiple reasons, it's mixing concerns — split it.

### Worked example — GST price calculation
**Scenario:** A junior PR adds `calculate_gst_inclusive_price(mrp)` to `app/routers/medicines.py`.

**Why reject:**
1. **GST is a business rule, not HTTP plumbing.** It's an *opinion* about the domain ("we charge 12% on top of MRP"). Routers don't hold opinions.
2. **It will get duplicated.** `/medicines`, `/sales`, and `/admin` routers all need GST-inclusive prices. In a router, this becomes 3 copies. In a service, it's 1.

**Where it belongs:** in a service — `pricing_service.gst_inclusive(mrp)`. Every router calls it. When the GST rate changes from 12% to 18%, **one file changes.**

**General rule:** any number-crunching, normalization, or domain decision belongs in a service. Routers stay boring.

---

## Step 1.4 — Pydantic schemas (input/output contract split)

### Concept: two schemas, never one
**Analogy:** Two prescription form pads at the desk:
- **"Request" form (`MedicineCreate`)** — what the customer/pharmacist fills IN. No `id`, no timestamp.
- **"Receipt" form (`MedicineOut`)** — what the pharmacy hands BACK. Includes `id` + `created_at`. Never includes `cost_price` or internal notes.

One pad IN, one pad OUT. Different fields. Different rules. **Same medicine, two views.**

### Why Pydantic exists at all
Declaring a `BaseModel` subclass with typed fields + `Field(...)` constraints gets you, **for free**:
- Automatic JSON parsing
- Automatic field-by-field validation
- Automatic `422 Unprocessable Entity` response on bad input (no `try/except` needed)
- Automatic Swagger docs for both request and response shapes

Zero validation code. The framework handles it **before your function runs**.

### Three concrete reasons NOT to use one shared schema *(worked answer)*

> **Q:** "Why two schemas? Let's just use one `Medicine` class everywhere — DRY principle, right?"

**A — three things that go wrong:**

1. **Security / mass-assignment attack.** Client sends fields they should never control — `id`, `is_admin`, `created_at`. Example: `{"id": 999, "name": "Dolo"}` → client now controls database state.
2. **Internal data leakage.** The same schema exposes private business fields in responses — `cost_price`, `supplier_discount`, `internal_notes`. Customers should never see company secrets.
3. **Input vs output evolve differently.** `POST` may only need `name + mrp`. `GET` later adds `id`, `created_at`, `stock_status`. One shared schema couples them — changing one API breaks every consumer of the other.

**Conclusion:** input contract and output contract are different concepts. Never DRY them together.

### Formal vocabulary to use in interviews
- **Input contract** = the schema clients are *allowed* to send (e.g. `MedicineCreate`)
- **Output contract** = the schema clients *receive* (e.g. `MedicineOut`)
- **Mass assignment** = the vulnerability of letting client-supplied JSON populate ANY model field. Famous Rails (2012) and Django CVEs. Pydantic's two-schema convention prevents it by design.
- **OWASP API Security Top 10 #3 — Excessive Data Exposure** = the formal name for mistake #2 (leaking internal fields). Cite this in interviews.

### The Medicine entity field map
*(see diagram: "Step 1.4 — Pydantic schema split" in diagrams.md)*

| Field | Where it lives |
|-------|----------------|
| `id`, `created_at` | **Only in `MedicineOut`** (server-generated) |
| `name`, `mrp`, `hsn_code`, `manufacturer` | Both `MedicineCreate` and `MedicineOut` |
| `cost_price`, `supplier_notes`, `profit_margin` | **Only in repository layer.** Never in any schema sent to a client. |

### 3 beginner mistakes
1. **One shared schema for input + output** → mass assignment + data leakage (covered above).
2. **No `Field()` constraints** (just `mrp: float`) → `-999.99` makes it into the DB → negative invoices on Friday.
3. **Manually catching `ValidationError` in the router** → breaks FastAPI's automatic `422` + Swagger error docs. **Trust the framework.**

### Interview gold
**Q:** *"Why does production FastAPI code typically have `MedicineCreate`, `MedicineOut`, AND a SQLAlchemy `Medicine` ORM class — three classes for one concept?"*

**A — three contracts, three rates of change:**
- **`MedicineCreate`** = *input contract* — what a client may send
- **`MedicineOut`** = *output contract* — what we promise to return
- **`Medicine`** (ORM, Phase 2) = *storage contract* — the full DB row with internal fields

Each has different validation, audience (client vs server vs DB), and rate of change. Conflating them creates the bugs in beginner mistakes 1–3 above.

---

## Step 1.5 — Repository layer (in-memory, designed to swap)

### Concept: the storeroom clerk's exact job
**Analogy:** The clerk has the only key to the storeroom. They do exactly 4 things:
- Bring item #5 (`get_by_id`)
- Bring everything (`list_all`)
- Check if anything has label X (`find_by_normalized_name`)
- Put new item on a free slot, give it a slot number (`add`)

**They NEVER:** decide if you should add it, compute prices, reject by expiry, check auth. Those are the pharmacist's (service's) or security guard's (middleware's) jobs.

### The 4-method repository contract
| Method | Returns | Job |
|--------|---------|-----|
| `add(name, mrp, hsn_code, manufacturer)` | `MedicineOut` with new `id`+`created_at` | Store, generate id, mirror what a DB auto-increment does |
| `get_by_id(medicine_id)` | `MedicineOut \| None` | Fetch by PK |
| `list_all()` | `list[MedicineOut]` | All records, insertion order |
| `find_by_normalized_name(normalized: str)` | `MedicineOut \| None` | Caller pre-normalizes; repo just compares |

**Why pre-normalized:** the service owns the normalization rule. If "Crocin 500MG " and "crocin 500mg" should match, the service decides that — not the repo. Repo stays storage-rule-free.

### Why the same contract survives Phase 2's MySQL swap
The 4 method names + signatures don't change when storage swaps from dict → MySQL → MySQL+Redis. The service file is untouched across all three. **This is the entire payoff of the repository pattern.**

### 3 beginner mistakes in repository design
1. **Business logic inside repo methods** (duplicate check, FEFO selection, price calc). Rule: repo has zero `if` statements tied to *domain* meaning.
2. **Returning mutable references to internal state** (`return self._store` instead of `list(self._store.values())`). Caller mutates returned object → repo's internal storage mutates → ghost data.
3. **Coupling repo to HTTP schemas** (`def add(self, payload: MedicineCreate)`). Now a CSV bulk-import has to fake a MedicineCreate. Repo should take primitives or domain objects, never HTTP DTOs.

### Worked example — the "atomic check-then-add" temptation

> A teammate proposes a single repo method `add_with_duplicate_check(...)` that scans the store, raises if duplicate, then inserts. "Atomic! Cleaner!"

**Reason 1 — business logic in repo (covered above).**
**Reason 2 — atomicity belongs at the data store, not in Python:**
- In-memory Phase 1: single-process Python + GIL = no race possible for dict ops anyway.
- Phase 2 MySQL: atomicity is enforced by a `UNIQUE` constraint on the `normalized_name` column at the DB engine level. The DB refuses the duplicate insert. Python code wrapping it is redundant.
- Bundling kills flexibility: Phase 8 admin tool might legitimately need to skip the check (force-add). Bulk imports may have their own dedup upstream. Tests of storage alone become impossible.

**Senior framing for interviews:** *"Atomicity belongs at the data store (DB UNIQUE constraint, Redis SETNX). Decisions belong in services. Coupling them violates separation of concerns."*

### Interview gold
**Q:** *"Where does validation live in a layered architecture?"*
**A:** Three layers, three kinds of validation:
- **Schema layer (Pydantic):** *shape* validation — is the JSON well-formed, types correct, lengths sane? Auto-handled by FastAPI → 422 on failure.
- **Service layer:** *business rule* validation — duplicates, FEFO, expiry, stock availability, price math.
- **Storage layer (DB constraints / Redis):** *invariant* validation — UNIQUE, NOT NULL, foreign keys, atomicity guarantees.

Each layer rejects bad data with the right tool. Bundling them creates the classic monolithic-validation mess.

### The full POST /medicines lifecycle (every layer's transformation)
*(see diagram: "POST /medicines — full request lifecycle" in diagrams.md)*

```
Frontend
   │ POST JSON: {"name":"Crocin 500mg","mrp":25.5,"hsn_code":"30049099","manufacturer":"GSK"}
   ▼
Router (FastAPI)
   │ FastAPI auto-parses the JSON body
   ▼
MedicineCreate  ← Pydantic validates SHAPE (types, min_length, gt=0, etc.)
   │ → fails here = automatic HTTP 422, your code never runs
   ▼
Service
   │ - normalize name: "Crocin 500mg" → "crocin 500mg"
   │ - check duplicate (asks repo.find_by_normalized_name)
   │ - calls repo.add(name=..., mrp=..., hsn_code=..., manufacturer=...)
   ▼
Repository
   │ - takes new_id from self._next_id
   │ - stamps created_at = datetime.now()
   │ - builds MedicineOut(id=..., name=..., mrp=..., created_at=...)
   │ - stores it in self._store, increments self._next_id
   ▼
MedicineOut  ← server-generated id and created_at now attached
   │ returned back up: Repo → Service → Router
   ▼
Router
   │ FastAPI serializes MedicineOut to JSON (only the declared output fields)
   ▼
Frontend  ← HTTP 201 + JSON body with id, name, mrp, hsn_code, manufacturer, created_at
```

**What's NEVER in the response (and why):** `cost_price`, `supplier_notes`, `profit_margin` — they live only in the repository's internal state (Phase 2: the DB row). They never appear in `MedicineOut`, so FastAPI **physically cannot** serialize them. That's the input/output contract paying off.

### Pitfalls hit during Step 1.7 — router-loading traps

**Trap A — Decorator arguments evaluate at IMPORT time, not request time.**
Wrote `response_model=MedicinineeOut` (typo for `MedicineOut`). When Python imported the module, the `@router.get(...)` decorator was called immediately, hit the undefined name → `NameError` → **the entire app refused to start**. The bug wasn't lurking for the first GET request — it killed uvicorn boot.
**Senior takeaway:** any typo in a decorator's keyword args, an `app.include_router(...)` call, or a module-level constant blocks app startup. Test that the app boots after every edit, not just that endpoints work.

**Trap B — Compound statements can't share a line with `def`.**
Wrote `def get_medicine(...): result = ... if result is None: raise ...` all on one line. Python rejects this with `SyntaxError`. You CAN write `def f(): return 1` (single simple statement), but you can NEVER write `def f(): if x: y` (compound `if` on header line).
**Rule of thumb:** if the body has a colon (`if:`, `for:`, `with:`, `try:`), it must start on the next indented line.

### Pitfall hit during Step 1.6 — shadowing the `id` builtin

**Bug:** wrote `return self._repo.get_by_id(id)` inside `get_medicine(self, medicine_id: int)`. The parameter was `medicine_id`, but the call used `id`.

**Why it silently fails:** `id` is a **built-in Python function** (returns memory address of an object). Python's name lookup finds the builtin → passes the *function reference* as the argument → `self._store.get(<function id>)` returns `None` → endpoint always 404s. **No error, just always-wrong behavior.**

**Senior lesson — never use these names as variables:** `id`, `list`, `dict`, `str`, `type`, `input`, `next`, `filter`, `min`, `max`, `sum`, `all`, `any`, `bytes`, `set`, `tuple`. They all silently shadow built-ins.

**Detection:** modern linters (`ruff`'s rule `A001` — flake8-builtins) flag this automatically. Wire up `ruff` later in the project; until then, mental checklist before naming any variable.

### Pitfall hit during Step 1.5 — Python indentation defines scope

Three indentation levels matter inside a class:

| Indent | What it means |
|--------|----------------|
| 0 spaces | Module level (top of file) — `class`, top-level `def`, imports |
| 4 spaces | Class body — `def __init__`, `def add`, attribute definitions |
| 8 spaces | Method body — code that runs when the method is called |

**The lesson:** if you accidentally write `def get_by_id(...)` at column 0 instead of column 4, Python doesn't error — it just creates a **top-level function** instead of a method. The class instance won't have that method. The bug surfaces only when you call `repo.get_by_id(...)` and get `AttributeError`. **Always check indentation when adding new methods to an existing class.**

### Where does `self._next_id` come from? (Plain-language)
- `self` is the **specific repo instance's private locker.**
- `__init__` writes `self._next_id = 1` once when the instance is created → "label `_next_id` in the locker, value `1`."
- Every later method that has `self` as its first param can read or write that label.
- The `_` prefix is convention: *"private, don't touch from outside the class."*
- In Phase 2 this whole counter disappears — MySQL's `AUTO_INCREMENT` column hands out the id.

---

## Git / GitHub fundamentals (covered alongside Phase 0)

### Concept: local repo ↔ remote
**Analogy:** `origin` is just a **named pointer** to your GitHub URL. `.gitignore` is the **bouncer** — decides which files are even allowed to be staged. Anything in `.gitignore` is invisible to Git, period.

### First-push workflow
```powershell
git init
git branch -M main
git remote add origin <url>
git add <files>
git commit -m "chore: ..."
git push -u origin main    # -u sets default upstream; only needed on first push
```

The `-u` (short for `--set-upstream`) tells Git: *"from now on, `git push` and `git pull` default to this remote + branch."*

### Authentication: Personal Access Tokens (PAT)
GitHub disabled password auth years ago. When git prompts for password, paste a **PAT** from `github.com/settings/tokens` (classic, scope: `repo`). The PAT is your password.

### Commit message convention
Prefix with the change type:
- `feat: add medicines POST endpoint`
- `fix: handle empty batch in FEFO selector`
- `chore: pin uvicorn version`
- `refactor: extract price calc into pricing service`
- `docs: add /health endpoint example`

In 6 months, `git log --oneline | grep "fix:"` becomes searchable.

---

## Running glossary

| Term | Definition |
|------|------------|
| **ASGI** | Async Server Gateway Interface — the protocol uvicorn speaks to FastAPI |
| **FEFO** | First-Expiry-First-Out — sell the batch expiring soonest |
| **HSN code** | Harmonized System of Nomenclature — Indian GST product classification code |
| **MRP** | Maximum Retail Price — printed on Indian medicine packaging |
| **`Depends()`** | FastAPI's dependency injection mechanism — lets tests swap fakes for real deps |
| **Pydantic schema** | A class defining valid request/response shape; auto-rejects bad data |
| **OpenAPI / Swagger** | Auto-generated interactive API docs at `/docs` (FastAPI ships this free) |
| **PAT** | Personal Access Token — replaces password for git push to GitHub |
| **PSR** | Pages Server Render — Next.js Pages Router server-side rendering (Phase 11) |
| **CRUD** | Create, Read, Update, Delete — the four basic data operations |

---

## Phase 3 — Step 3.1 ✅ DONE — Provider Factory Verified (2026-05-31)

**Milestone:** First real call to a hosted LLM succeeded — NVIDIA AI Endpoints + `mistralai/mistral-nemotron` returned `AIMessage(content='pharmacy-ok')` to a temperature-0 echo prompt.

### What this proves about the wiring

| Layer | Verified |
|---|---|
| `.env` parsing | `_load_dotenv` correctly read `LLM_PROVIDER=nvidia` and the API key |
| Placeholder guard | `_is_placeholder()` rejected `YOUR_NVIDIA_KEY_HERE` earlier; passes real `nvapi-...` |
| Provider dispatch | `get_llm()` branch picked `_build_nvidia_client()` based on env var |
| Lazy import | `langchain_nvidia_ai_endpoints` only imported when actually used (good: OpenAI-only users don't pay the import cost) |
| Network + auth | Real HTTPS call to `integrate.api.nvidia.com/v1/chat/completions` returned 200 |
| Model catalog | `mistralai/mistral-nemotron` is a valid model ID on NVIDIA's endpoint |
| LangChain contract | Return is a proper `AIMessage`, not a tuple/dict — `.content` access works |
| Determinism | `temperature=0.0` made the model echo our string exactly (good for billing — we cannot have creative invoices) |

### 3 production mistakes this smoke test would have caught early

1. **Hardcoding the model name in node code** — if `extract_intent.py` had said `ChatNVIDIA(model="mistral-7b")` directly, swapping models means edits in N files. Going through `MODEL_NAME` from config = one-line swap.
2. **Treating quoted .env values as quoted** — our `.env` had `NVIDIA_API_KEY="nvapi-...."` with literal quotes pasted in. Our minimal loader does NOT strip quotes, so NVIDIA received `"nvapi-..."` (with the `"`) → 401. Standard `python-dotenv` strips quotes silently; ours doesn't. **Lesson:** know exactly what your env-loader does. Fixed by removing quotes from the value.
3. **No "real call" test before writing 5 nodes** — if we'd skipped this and built `extract_intent → resolve_medicine → select_batch → compute_pricing → persist_sale` first, then discovered the key was bad, every node's debugging would point at the wrong layer. **Always smoke-test the dial tone before wiring the phone tree.**

### Mental model: the provider factory pattern

```
node code               app/ai/llm.py            provider packages
─────────               ─────────────            ─────────────────
get_llm()    ───►  LLM_PROVIDER == "nvidia"? ──► ChatNVIDIA
                   LLM_PROVIDER == "openai"? ──► ChatOpenAI
                   anything else?            ──► RuntimeError
```

Every node calls `get_llm()`. NO node knows which provider it's talking to. That's the swap-by-env-var goal.

### Why `@lru_cache(maxsize=1)` on `get_llm()`

Same idea as a database connection pool — building a `ChatNVIDIA(...)` once is cheap, but doing it for every node call wastes time and means cold reloading of API key validation. `lru_cache` makes the second call return the *same* client object instantly. The `1` is the cache size — we only ever want one client per process.

---

## Phase 3 — Step 3.2 (in progress) — File 1: ExtractedIntent schema

### The candy-shop notebook analogy

Mom runs a candy shop and gives you a notebook. Every page has 3 boxes: *What candy? / How many? / Big or small?*. At the top of the stack of pages, two more boxes: *Who is the kid? / Mommy's phone?*. Rules: fill ONE page per candy, no empty boxes, no drawing extra boxes.

| In the candy shop | In our code |
|---|---|
| One page filled in | One `MedicineItem` instance |
| Whole stack + top labels | One `ExtractedIntent` instance |
| You (the kid) filling pages | The LLM producing JSON |
| Mom checking pages | Pydantic validating the JSON |
| Mom rejecting a bad page | `ValidationError` |
| The notebook design itself | The Pydantic BaseModel class definitions |

### Why a schema matters (the *production* reason)

Without a schema, the LLM returns whatever-flavored text it wants. With a schema, we tell the LLM "you MUST return a JSON object that fits this exact shape, and we will reject anything else." This is what `llm.with_structured_output(ExtractedIntent)` does — it constrains the LLM's output and validates it through Pydantic.

For billing this is critical: a fuzzy free-text reply from the LLM cannot be used to debit stock. A validated `ExtractedIntent` with an `int` quantity in 1..1000 can.

### The two-class split (`MedicineItem` and `ExtractedIntent`)

One pharmacist sentence can name MANY medicines. The customer name + phone appear ONCE per sentence, not once per medicine. So:

- `MedicineItem` = the *repeating* part (name, quantity, unit)
- `ExtractedIntent` = the *whole* parsed sentence (list of items + customer info)

This is the same pattern as an HTML form with a repeating table inside — one form metadata block, many table rows.

### Field-by-field rationale

| Field | Type | Constraint | Why |
|---|---|---|---|
| `MedicineItem.name` | `str` | required | The LLM should NEVER skip this — without a name we have no medicine to bill |
| `MedicineItem.quantity` | `int` | `ge=1, le=1000` | Must be a whole number ≥1 (you can't sell -3 strips); capped at 1000 to bound hallucinations |
| `MedicineItem.unit` | `str` | required, free-form for now | Constrained-list later (`Literal["strip","bottle","tablet","ml"]`) when we know the full set |
| `ExtractedIntent.items` | `list[MedicineItem]` | `min_length=1` | Empty list = the sentence was gibberish; better to reject than create a $0 invoice |
| `ExtractedIntent.customer_name` | `Optional[str]` | default `None` | Pharmacist may just say "give me Crocin" without naming the customer |
| `ExtractedIntent.customer_phone` | `Optional[str]` | default `None` | Stored as `str`, NOT `int`, because phones can have leading zeros |

### 3 production mistakes this design prevents

1. **Phone as `int`** — would silently drop leading zeros, breaking customer lookups later.
2. **No `min_length=1` on items** — empty list would slip through validation and produce a zero-line invoice nobody could trace back to a real order.
3. **No `le=1000` on quantity** — a model hallucination like `2 × 10^400` (we literally saw this on Mistral-Nemotron) would attempt to debit absurd stock; the cap rejects the page BEFORE it touches the DB.

### Why `description=...` on every Field

The LLM is given the schema as part of its instructions. The `description` is the LLM's hint about what each box means. An empty description = the LLM guessing from the field name only. A good description is half the prompt. **Treat `description=` as the prompt for that field.**

### `if __name__ == "__main__":` block at the bottom

Lets you run `python -m app.ai.schemas.extracted_intent` directly to sanity-check the schema BUILDS — no LLM call needed, just proves the field rules compile.

---

## Phase 3 — Step 3.2 — File 2: `billing_prompts.py` (the instruction card)

### Continuing the candy-shop analogy

Mom hired Rohit (the LLM). Before he serves any kid, she hands him a small instruction card. The card never changes mid-day. The card has 5 sections:

1. **Role** — who Rohit is (focuses him into a persona)
2. **Task** — what he does
3. **Rules** — guardrails: never invent, lowercase, leave blanks null
4. **Output format** — how his answer must look (JSON only)
5. **Examples** — 1–2 sample "kid said X → Rohit wrote Y" demonstrations

| In the candy shop | In our code |
|---|---|
| The instruction card | A Python `str` constant: `EXTRACT_INTENT_SYSTEM_PROMPT_V1` |
| Rohit reading the card every morning | The LLM consuming the system message at the start of every call |
| Mom rewriting the card next month | Adding `EXTRACT_INTENT_SYSTEM_PROMPT_V2` and switching nodes to use it |

### Why a SEPARATE FILE for prompts (production reason)

Prompts are **products**, not strings.

- They take many tries to tune. Burying one inside a node function makes iteration painful.
- We version them (`_V1`, `_V2`) so we can A/B test and roll back without touching node code.
- Multiple nodes can share a base persona — common Role/Rules block extracted, specialized per node.

In senior-engineer-land this is called **prompt engineering as a first-class artifact**. Same way you wouldn't hardcode an SQL query inside a button click handler — you'd put it in a repository file. Prompts deserve the same respect.

### The 5-section system-prompt structure (industry standard)

| Section | Purpose | Pitfall |
|---|---|---|
| **ROLE** | Set the LLM's persona ("you are a strict pharmacy order-taker") | Vague roles ("assistant") lose focus — be specific |
| **TASK** | Name the action precisely (extract / parse / structure) | Mixed actions in one node = confused output |
| **RULES** | Concrete guardrails, numbered | Vague rules like "be careful" do nothing |
| **OUTPUT FORMAT** | How the answer must look (JSON / table / etc.) | Skipping this lets the LLM add prose around the JSON |
| **EXAMPLES** | 1–3 input-output pairs (few-shot learning) | This is the single highest-leverage section. **2 examples > 10 rules.** |

### Few-shot learning in plain words

"Few-shot" = giving the LLM a tiny handful of examples right inside the prompt. Models learn FAR more from one well-chosen example than from a paragraph of rules. The technical reason: examples are the LLM's strongest "this is the pattern" signal — it will copy what it sees more reliably than what it's told.

### Naming convention: `<USE_CASE>_SYSTEM_PROMPT_V<n>`

- `EXTRACT_INTENT_SYSTEM_PROMPT_V1` (this file)
- Future: `RESOLVE_MEDICINE_SYSTEM_PROMPT_V1`, `COMPUTE_PRICING_SYSTEM_PROMPT_V1`
- After improving: `EXTRACT_INTENT_SYSTEM_PROMPT_V2` — `V1` stays in the file so we can revert.

### 3 production mistakes this design avoids

1. **Hardcoded prompts inside node functions** — un-A/B-testable, un-rollbackable, un-shareable.
2. **No few-shot examples** — outputs drift, especially on cheaper/smaller models like Maverick-17B.
3. **Mixing rules and examples without section labels** — models attend to structure; an unlabeled wall of text confuses them.

### How the prompt actually gets used at runtime

In `app/ai/nodes/extract_intent.py` (File 3, coming next):

```
llm = get_llm()
chain = llm.with_structured_output(ExtractedIntent)
result = chain.invoke([
    SystemMessage(content=EXTRACT_INTENT_SYSTEM_PROMPT_V1),
    HumanMessage(content=pharmacist_sentence),
])
```

The system message is the instruction card. The human message is the kid speaking. The structured-output wrapper is mom checking the filled page.

---

## Phase 3 — Step 3.2 — File 3: `extract_intent.py` (the node where it all connects)

### Continuing the candy-shop analogy

A kid walks in. Rohit's 6-step routine:

1. 👂 **Listen** to what the kid says → `state.get("pharmacist_input", "")`
2. 🛑 **Silent kid?** → return errors, don't bother mom. *Cheap check before expensive LLM call.*
3. 📇 **Pull the instruction card** → `SystemMessage(content=EXTRACT_INTENT_SYSTEM_PROMPT_V1)`
4. 📓 **Open the notebook** (force the LLM into the schema) → `.with_structured_output(ExtractedIntent)`
5. ✍️ **Fill the page** → `.invoke([system, human])` — this is the REAL NVIDIA API call
6. 🧺 **Drop in mom's basket** → `return {"extracted_intent": result.model_dump()}`

### Why LangGraph state is a TypedDict + we return a partial dict

LangGraph's nodes don't return the whole state — they return a **partial update**:

```python
return {"extracted_intent": ...}   # just the key(s) you touched
```

LangGraph **merges** that into the existing state. This is:
- **Safer** — you don't accidentally wipe a field you didn't mean to touch
- **Cleaner** — your node says exactly what it changed
- **Composable** — multiple nodes can return different partial updates; LangGraph stitches them

Think of it like `git diff` instead of overwriting the whole file.

### Why `model_dump()` at the state boundary

LangGraph state often gets serialized (checkpoints, debug logs, time-travel replay). Pydantic objects don't always serialize cleanly. The **rule of thumb**:

> Pydantic objects live INSIDE a function. At the boundary (state, JSON, queue), convert to plain dict via `model_dump()`.

This is the same principle as the FastAPI rule we already follow: SQLAlchemy models live in the repository, Pydantic models live at the API boundary.

### LangChain message types — the convention

- `SystemMessage(content=...)` — instructions, persona, rules. Sent **first**.
- `HumanMessage(content=...)` — actual user input. Sent **after** the system message.
- `AIMessage(content=...)` — the model's response (you usually don't construct these manually).

Models are trained on this exact ordering. **System first, human after.** Reversing the order can silently degrade output — some models will follow the LAST message most strongly.

### Why the empty-input guard saves money + bugs

A real user might press "submit" on an empty form. Calling Maverick with `""` :
- Costs money (yes, free trial credits — but they're finite)
- Returns garbage (or worse, makes something up)
- Slows down the request needlessly

The guard runs in ~1 microsecond and short-circuits the whole thing. Senior engineers always check the cheap conditions first. This is the same instinct as `if not user.is_authenticated: return 401` before touching the DB.

### 3 production mistakes this design avoids

1. **No empty-input guard** — wastes money + lets garbage flow downstream.
2. **Returning the raw Pydantic instance in state** — breaks LangGraph checkpoint serialization.
3. **Hard-coding the prompt string inside the node** — undoes the whole reason we split into 4 files; un-versionable, un-A/B-testable.

### How this node lives in the bigger graph (preview of File 4 and beyond)

```
START
  ↓
[extract_intent]   ← what you're building NOW
  ↓
[resolve_medicine] ← Step 3.4: look up DB by extracted name
  ↓
[select_batch]     ← Step 3.5: FEFO pick from app.repositories
  ↓
[compute_pricing]  ← Step 3.6: server-side price math
  ↓
[persist_sale]     ← Step 3.7: write Sale + SaleItem in one transaction
  ↓
END
```

Each node has the same shape: takes `state`, returns a partial dict. The graph (`StateGraph.compile()`) wires them in order. We'll build that in Step 3.8.

---

## Phase 3 — Step 3.3 — `resolve_medicine` (Priya the inventory clerk)

### Continuing the candy-shop analogy

Rohit (the LLM) filled the notebook pages. He hands the stack to Priya, the inventory clerk. Priya:

1. Picks up a page → reads the candy name
2. Walks to the shelves (the database)
3. Finds the actual jar → reads its SKU number
4. Sticks the SKU on the page
5. Repeats for every page
6. Puts unfound pages on the "can't find" pile and tells mom

| Candy shop | Code |
|---|---|
| Priya | `resolve_medicine` node |
| Shelves | `medicines` table in MySQL |
| Candy name on page | `item["name"]` from `extracted_intent` |
| Walk to shelves | `with SessionLocal() as db:` |
| Find the jar | `repo.find_by_normalized_name(...)` |
| SKU sticker | `medicine.id` (primary key) |
| Stickered page | `{**item, "medicine_id": ...}` in `resolved_items` |
| Can't-find pile | append to `state["errors"]` |

### Why this node exists at all

The LLM gives us a **string** (`"Crocin 500mg"`). Every downstream node — FEFO batch picker, server-side price calculator, invoice writer — needs an **integer primary key**.

- Strings are fragile (casing, whitespace, typos).
- Integer IDs are absolute and indexable.
- This node is the **bridge from messy text to canonical DB references**.

### Why we open a fresh `SessionLocal()` inside the node

FastAPI's `Depends(get_db)` gives endpoints a per-request session. LangGraph nodes don't get that injection — so the node owns its own session lifecycle. The pattern:

```python
with SessionLocal() as db:
    repo = SQLAlchemyMedicineRepository(db)
    # ... use repo here ...
# session auto-closed here, connection returned to pool
```

Same principle as `with open(...)` for files. The session must be cleaned up; the context manager guarantees it even if the loop raises.

### Why we don't `raise` on missing medicine

A real pharmacist might say *"Vitamin Q"* — typo or unstocked item. Aborting the whole order on one missing item is hostile UX. Instead:

- **Found items** → enriched with `medicine_id` and added to `resolved_items`
- **Unfound items** → appended as soft errors to `state["errors"]`
- **The graph itself decides** later (step 3.8) whether to short-circuit or proceed partial

This is called the **collect-then-decide** pattern. Senior-engineer reflex: never let one row of data crash an entire batch.

### State evolution (where this node sits)

```
extract_intent   → state["extracted_intent"]   = {"items": [...], "customer_name": ..., "customer_phone": ...}
resolve_medicine → state["resolved_items"]     = [{...item, "medicine_id": 42}, ...]
                   state["errors"]              = [optional, list of unfound names]
select_batch     → state["priced_items"]        = [{...item, "batch_id": ...,  "unit_price": ...}, ...]
compute_pricing  → state["total_amount"]
persist_sale     → state["sale_id"]
```

Each node enriches state by ADDING new keys. Earlier keys remain readable downstream — useful for audit / debugging.

### Shape of `resolved_items` (the new contract)

```python
[
    {"name": "Crocin 500mg", "quantity": 2, "unit": "strip", "medicine_id": 42},
    {"name": "Benadryl cough syrup", "quantity": 1, "unit": "bottle", "medicine_id": 99},
]
```

We use `{**item, "medicine_id": ...}` to preserve every key the LLM gave us PLUS the new resolved id. That dict-spread idiom is Python's neat way to "copy this dict and add one more key" without losing anything.

### 3 production mistakes this design avoids

1. **Forgetting to normalize before lookup** — the index is on `normalized_name`. Querying with raw text gives false negatives.
2. **Crashing the whole order on one unfound item** — collect-then-decide is the senior pattern.
3. **Holding a DB session for the whole graph** — long-held sessions starve the connection pool. One short session per node is the safe pattern.

### Why update `BillingState` now (`medicine_id` → `resolved_items`)

The Phase 2 state had `medicine_id: int` and `batch_id: int` — singular fields, assuming one medicine per sale. Step 3.2 broke that assumption by allowing many items per sentence. The state had to evolve: `resolved_items: list[dict]` and `priced_items: list[dict]` replace those singular fields cleanly.

This is normal — state schemas evolve as the graph grows. The TypedDict + `total=False` makes this safe (no breaking changes for unused fields).

---

## Phase 3 — Step 3.4 — `select_batch` (Sanjay the storeroom manager)

### Continuing the candy-shop analogy

Priya stickered every page with the SKU. Now Sanjay takes each page:
1. Finds every box of that candy on the shelves
2. Throws out boxes past their expiry date
3. Skips empty boxes
4. From what's left, picks the one that **expires soonest**
5. Checks: enough candy in this box? If not → "out of stock"
6. Writes the batch number + expiry date on the page

Sanjay's rule: *"Always open the older one first. Never let the older box rot while we sell the fresh one."*

### FEFO — what it is, why it matters

**FEFO = First Expiry, First Out.** When you have multiple batches of the same medicine, you ALWAYS sell from the soonest-expiring batch first. Why?

| Reason | Without FEFO |
|---|---|
| Customer safety | Could sell expired medicine — illegal + dangerous |
| Inventory rotation | Older stock rots while fresh sells → financial waste |
| Regulatory compliance | India's Drugs & Cosmetics Act mandates it; audit failures are common |
| Cost control | Each expired strip is a direct write-off |

**FEFO is THE single most important business rule in pharmacy software.** If you take ONE thing from Phase 3 to interviews, take this.

### How FEFO is enforced in the SQL

We already wrote this in Phase 2 — `SQLAlchemyBatchRepository.select_fefo()`:

```sql
SELECT * FROM batches
WHERE medicine_id = :id
  AND quantity > 0                 -- skip empty batches
  AND expiry_date > CURRENT_DATE   -- skip expired batches (MySQL-side date for timezone safety)
ORDER BY expiry_date ASC
LIMIT 1                            -- the soonest-expiring survivor
```

The composite `(medicine_id, expiry_date)` index makes this a **single B-tree seek** — fast even at millions of batch rows. This is why we added that exact index in Phase 2's migration.

### Why this node is "easy mode" compared to extract_intent

- No new LLM call (deterministic SQL)
- No new SQL (Phase 2's `select_fefo` already does the work)
- Same `with SessionLocal()` pattern as `resolve_medicine`
- Same collect-then-decide error pattern

It's almost pure glue code. **Most senior engineering is gluing well-built pieces together — you're learning that pattern.**

### The "FEFO winner has insufficient stock" case

The FEFO query returns the soonest-expiring batch with `quantity > 0`. It does NOT check if that batch has enough for the ORDER. So a batch with 3 strips can be returned for an order of 5.

In this step, that → error. In a future enhancement (step 3.5+), we'll implement **multi-batch split**: take 3 from batch A and 2 from batch B (also in FEFO order). Today we keep it simple.

### Why we `.isoformat()` the expiry_date before putting it in state

`json.dumps()` can't serialize `datetime.date` objects natively. If state["batched_items"] contains a raw `date`, any:
- LangGraph checkpoint (persisted state)
- Debug `print(json.dumps(state))`
- Time-travel replay (LangGraph feature)

...will fail with `TypeError: Object of type date is not JSON serializable`. The pattern:

> **Strings live in state. Date objects live inside functions.** Convert at the boundary.

Same instinct as `result.model_dump()` for Pydantic → dict conversions at the state boundary.

### State evolution after step 3.4

```
extract_intent   → state["extracted_intent"]
resolve_medicine → state["resolved_items"]   (adds medicine_id)
select_batch     → state["batched_items"]    (adds batch_id, batch_number, expiry_date)
compute_pricing  → state["priced_items"]     (adds unit_price, line_total)  [step 3.5]
persist_sale     → state["sale_id"]                                          [step 3.7]
```

Each list field is OWNED by one node — single-writer principle. Makes audit + debugging much easier.

### 3 production mistakes this design prevents

1. **Picking any batch, not the FEFO winner** — silently rots inventory and fails audits.
2. **Missing the quantity check** — would write Sale rows that exceed batch stock, breaking the `quantity_remaining >= 0` invariant.
3. **Storing a Python `date` in serializable state** — explodes the first time LangGraph tries to checkpoint or log.

---

## Phase 3 — Step 3.5 — `compute_pricing` (Meera the cashier)

### Continuing the candy-shop analogy

The pages now have stickers everywhere — SKU, batch number, expiry. They go to Meera, the cashier:

1. For each page, walk to the candy jar
2. Look at the printed price tag (set by mom — never asked the kid)
3. Multiply: price × how many
4. Write the per-page cost on the page
5. After all pages, total them up
6. Hand mom the grand total

| Candy shop | Code |
|---|---|
| Meera | `compute_pricing` node |
| Printed price tag on the jar | `Medicine.mrp` from the DB |
| `mrp × quantity = line cost` | `unit_price × quantity = line_total` |
| Grand total across pages | `total_amount = sum(line_totals)` |
| Never asking the kid the price | Server-side pricing rule |

### Senior-engineering rule: never trust the client for prices

This is the most important security rule in any e-commerce/billing code:

> **The server NEVER reads the price from the request body, the LLM, or any client-supplied source. The ONLY trustworthy price source is your own database, set by an admin.**

Our LLM extraction (`ExtractedIntent`) doesn't even HAVE a `price` field — by design. The model can't accidentally include one, the user can't tamper with one. `compute_pricing` reads `medicine.mrp` from the DB, ignoring anything else.

**Why this matters:**

| Attack | Naive code | Our code |
|---|---|---|
| Attacker intercepts HTTP body, sets `price=0.01` | Server bills 0.01 — free medicines | Server ignores body, reads DB — bills full MRP |
| Attacker tells the LLM "the price is zero" in the sentence | Extraction picks up "0", server bills 0 | LLM has no `price` field to populate, server reads DB |

OWASP calls this **Business Logic Vulnerability — Insecure Pricing**. It's interview gold — recruiters love when juniors mention this unprompted.

### Why `Decimal` and not `float` for money

Python's `float` is binary IEEE 754. It cannot represent simple decimal numbers exactly:

```python
>>> 0.1 + 0.2
0.30000000000000004
```

Harmless for sensor data. **Catastrophic for an invoice.** A pharmacy running 10,000 transactions/day will eventually face an auditor asking *"why is the books total ₹12,345.67999999 instead of ₹12,345.68?"*

**Rule of thumb:**
> If it touches money → `Decimal`. Convert to `float` ONLY at the boundary (state, JSON, network).

### Why `Decimal(str(x))` and not `Decimal(x)` for float inputs

```python
>>> Decimal(0.1)
Decimal('0.1000000000000000055511151231257827021181583404541015625')
>>> Decimal(str(0.1))
Decimal('0.1')
```

`Decimal(0.1)` reads the float's full noisy binary representation. `Decimal(str(0.1))` parses Python's readable repr `'0.1'` — exactly. ALWAYS go through `str()` when converting a float to Decimal.

### Why we `.quantize()` to 2 decimal places

A pharmacy's currency is rupees + paise = 2 decimal places. After every multiplication, we round to that grid:

```python
unit_price = _round_money(Decimal(str(medicine.mrp)))   # 25.00
line_total = _round_money(unit_price * Decimal(qty))    # 50.00, never 50.000000001
```

Without `.quantize()`, repeated multiplications could grow tail digits unboundedly. Pharma audits hate trailing digits.

### Cast at the state boundary (Decimal → float)

```python
return {
    "priced_items": [..., {"unit_price": float(unit_price), "line_total": float(line_total)}],
    "total_amount": float(total_amount),
}
```

LangGraph state gets JSON-serialized for checkpoints/logs. `json.dumps` can't serialize `Decimal`. The cast is unavoidable. Loss of precision at this step is fine — we already rounded to paise; the float representation of e.g. `50.0` is exact.

> **Same pattern as `date.isoformat()` in `select_batch`** — strong type inside the function, JSON-safe type when entering state.

### State shape after this step

```python
state = {
    "pharmacist_input": "...",
    "extracted_intent": {...},
    "resolved_items":   [{name, quantity, unit, medicine_id}, ...],
    "batched_items":    [{...resolved_item, batch_id, batch_number, expiry_date}, ...],
    "priced_items":     [{...batched_item, unit_price, line_total}, ...],   # new
    "total_amount":     50.00,                                              # new
    "errors":           [...],
}
```

This is the state right before `persist_sale` (step 3.7) writes the Sale + SaleItem rows in one transaction.

### 3 production mistakes this design prevents

1. **Reading price from request body** — opens an Insecure-Pricing vulnerability.
2. **Using float for math** — silent rounding errors corrupt invoices.
3. **Passing Decimal into state** — state becomes JSON-unserializable; checkpoints break.

---

## Phase 3 — Step 3.7 — `persist_sale` (Mom writing the bill — atomic)

### Continuing the candy-shop analogy (final scene)

Mom takes the finished notebook pages. She does FOUR things at once — together or not at all:
1. Add the kid to the address book (if new)
2. Open the bill log and write a new bill
3. Copy every notebook page into the bill ledger
4. Walk to the storeroom and subtract sold candy from the boxes

If interrupted halfway → she tears up everything and the shop is unchanged. That's a **transaction**.

| Candy shop | Code |
|---|---|
| Mom doing all 4 atomically | `with db.begin():` |
| Address book | `customers` (find-or-create by phone) |
| New bill | `INSERT sales` |
| Each line on the bill ledger | `INSERT sale_items` |
| Subtract from the box | `UPDATE batches SET quantity = quantity - X` |
| Tearing up on interruption | `db.rollback()` (auto on exception) |
| Signing the bill as final | `db.commit()` (auto on clean exit) |

### Why this node uses ORM models DIRECTLY (not Phase 2 repositories)

The Phase 2 repos commit inside each `.add()` method (cleanly designed for single-table writes). That model fails for multi-table writes because each call commits in isolation:

```
Bad (with auto-commit repos):
  customer_repo.add(...)   ← commits
  sale_repo.add(...)        ← commits
  CRASH HERE
  sale_item_repo.add(...)   ← never runs
  batch_repo.update(...)    ← never runs

Result: customer exists, sale exists, but no lines and no stock decrement.
        Cannot be undone without manual repair scripts.
```

The fix is the **Unit of Work pattern** — the caller (this node) owns the commit boundary. We use ORM models directly inside `with db.begin():`, so only ONE commit (or one rollback) happens for the entire 4-table write.

> **Senior-engineer rule:** Repositories that auto-commit are fine for single-table CRUD. Anything spanning tables needs the caller to own the transaction.

### Find-or-create by phone — the natural-key pattern

```python
customer = db.scalars(
    select(Customer).where(Customer.phone == phone)
).first()
if customer is None:
    customer = Customer(phone=phone, name=name)
    db.add(customer)
    db.flush()  # populate customer.id WITHOUT committing
```

The UNIQUE index on `customers.phone` (added in step 3.6) makes the find side an O(log n) seek and guarantees we never end up with two customer rows for the same number.

`db.flush()` is the key trick: it pushes pending INSERTs to the DB so SQL-generated IDs come back to Python, but DOES NOT commit. The same transaction still wraps everything.

### `db.flush()` vs `db.commit()` — when to use which

| Method | What it does | When to use |
|---|---|---|
| `db.flush()` | Sends pending SQL to the DB so generated columns (auto-increment IDs, server_default timestamps) come back. **Inside the same open transaction.** | When you need the auto-generated ID of a just-inserted row for a foreign key downstream. |
| `db.commit()` | Tells the DB "make all changes since BEGIN permanent" + ends the transaction. | At the END of the unit of work. |
| `db.rollback()` | Discards everything since BEGIN. | On error. (`with db.begin():` does this automatically on exception.) |

In persist_sale we flush after Customer and after Sale (to get their IDs for FKs), then commit ONCE at the end of the `with db.begin():` block (implicit).

### The defensive stock re-check INSIDE the transaction

```python
if batch.quantity < item["quantity"]:
    raise RuntimeError("insufficient stock in batch ...")
```

`select_batch` already verified this earlier in the pipeline. So WHY re-check here? **Concurrency.**

Between `select_batch` and `persist_sale`:
- Another pharmacy terminal could have sold from the same batch
- Stock that was 25 at `select_batch` time could be 10 by the time we get here

The DB row state at THIS moment is what matters. The re-check inside `with db.begin():` is the **race-condition guard**. If it fails, the transaction rolls back cleanly and the user sees a graceful error instead of a corrupted invoice.

This is the **read-modify-write race** — one of the canonical concurrency bugs in any web app. The simplest fix (the one we use) is: check + update inside one transaction. A more advanced fix is row-level locking via `SELECT ... FOR UPDATE`. We're skipping that until / unless we see real contention.

### Atomic-or-nothing — what step 3.7 Test 3 actually proved

We deliberately asked the node to sell 999,999 strips when only 23 exist. The node:
1. Found the customer (existed from Test 1)
2. Inserted a new Sale header row
3. Entered the loop — got to the stock check on the first (and only) item → raised
4. `with db.begin():` caught the exception and rolled back EVERYTHING — the sales INSERT, the not-yet-applied batch UPDATE — all gone

We verified by reading `batch.quantity` after the test: still 23 (same as before Test 3). **If the transaction wasn't truly atomic, the sale row would have remained in the DB and possibly the customer too.** It didn't. The DB is exactly as it was before Test 3 started.

### 3 production mistakes this design avoids

1. **Multi-table writes without a single commit boundary** — partial-write corruption that can't be undone safely.
2. **Trusting an upstream stock check** — concurrency can invalidate it; always re-verify inside the transaction.
3. **`.commit()` per row in the loop** — turns one atomic write into N independent commits; any failure leaves partial state.

### State after this step (= the final state of the billing graph)

```python
state = {
    "pharmacist_input": "...",
    "extracted_intent": {...},
    "resolved_items":   [...],
    "batched_items":    [...],
    "priced_items":     [...],
    "total_amount":     50.00,
    "sale_id":          42,        # ← new (persistent invoice ID)
    "errors":           [],
}
```

`sale_id` is the new invoice ID. The pharmacist UI shows *"Invoice #42 created, total ₹50.00"*.

### Interview talking points unlocked

1. **"How do you guarantee atomicity across 4 tables?"** → `with db.begin():` (Unit of Work) + ORM models directly, not auto-commit repos
2. **"Why re-check stock inside the transaction if select_batch already did?"** → concurrency race protection
3. **"Why is `db.flush()` different from `db.commit()`?"** → flush ships SQL for ID generation; commit ends the transaction
4. **"What happens if your DB connection drops mid-transaction?"** → SQLAlchemy's `pool_pre_ping` + `pool_recycle` catch most stale connections; transaction is automatically rolled back

---

## Phase 3 — Step 3.8 — Compiling the LangGraph (the manager)

### Continuing the candy-shop analogy

The 5 helpers (Rohit, Priya, Sanjay, Meera, Mom) each know their job but not the ORDER. Mom hires a manager with one instruction card: "When a kid walks in: Rohit → Priya → Sanjay → Meera → Mom. Pass the notebook between them." The manager does no actual work — he just calls the right helper in turn and carries the notebook (state).

| Candy shop | Code |
|---|---|
| The manager | `StateGraph(BillingState).compile()` |
| Instruction card | `add_node()` + `add_edge()` calls |
| Notebook passed along | `BillingState` dict |
| "Start"/"End" signs | `START` / `END` sentinels |
| Opening the shop for one customer | `graph.invoke({"pharmacist_input": ...})` |

### How a StateGraph is built

```python
builder = StateGraph(BillingState)        # 1. declare the state shape
builder.add_node("extract_intent", fn)     # 2. register each node by name
builder.add_edge(START, "extract_intent")  # 3. wire the order with edges
...
graph = builder.compile()                  # 4. compile into a runnable
graph.invoke({"pharmacist_input": "..."})  # 5. run the whole pipeline
```

`add_node(name, fn)` — `fn` is any callable taking state, returning a partial-state dict. Our 5 node functions plug in directly.

`add_edge(A, B)` — "after A finishes, run B." A straight chain of edges = a linear pipeline. (LangGraph also supports `add_conditional_edges` for branching — we don't need it yet.)

### The reducer pattern — why `errors` is `Annotated[list[str], operator.add]`

Without a reducer, when a node returns `{"errors": [...]}`, LangGraph OVERWRITES the whole `errors` field. So `resolve_medicine`'s "Crocin not found" would be wiped by a later node returning `{"errors": []}`.

The fix: declare the field as `Annotated[list[str], add]`. Now LangGraph CONCATENATES (because `operator.add` on lists = `+` = concatenation) each returned errors list onto the accumulated one. Errors from every node survive to the end.

This is THE key LangGraph concept: **fields can have reducers that say HOW to merge a node's output into state.** Default = overwrite. `operator.add` = append. You can write custom reducers too.

### Why a linear graph (no conditional short-circuit) is fine here

Every node already guards its own input (`if not X: return {"errors": [...]}`) and no-ops cleanly on bad/missing upstream data. So a failure upstream propagates as soft errors and downstream nodes degrade gracefully. Adding conditional edges to jump straight to END on the first error would be premature optimization — the guards already prevent crashes. We can add routing later if we want to skip wasted node calls.

### Why `@lru_cache` on `get_billing_graph()`

Compiling the graph costs a few ms. Doing it per HTTP request wastes latency. Cache it once per process — same pattern as `get_llm()`.

---

## Phase 3 — Provider switch: NVIDIA → OpenAI (2026-06-02)

### What happened

Per-node tests all passed on NVIDIA + Maverick. But running the FULL compiled graph end-to-end HUNG on NVIDIA (terminal froze, no output). Switched `LLM_PROVIDER=openai` in `.env` — graph ran instantly, wrote `sale_id`, all 5 nodes passed, `errors: []`.

### The lesson — this is WHY we built the factory pattern

The entire reason `app/ai/llm.py` has a `get_llm()` factory dispatching on `LLM_PROVIDER` was so that swapping providers is a ONE-LINE `.env` change with ZERO code edits. When NVIDIA misbehaved, we proved the value: changed `LLM_PROVIDER=nvidia` → `openai`, commented out the NVIDIA `AI_MODEL_NAME` override, done. Not a single node, graph, or schema file touched.

**Interview gold:** "I abstracted the LLM behind a provider factory. When one provider's endpoint stalled on structured output under load, I switched providers in one config line without touching application code." That's exactly the kind of decoupling senior engineers are paid for.

### The two `.env` traps we hit (BOTH providers)

1. **Quoted keys break the minimal loader.** Our `_load_dotenv` does `value.strip()` — strips whitespace, NOT quotes. A key written as `OPENAI_API_KEY="sk-..."` is loaded WITH the literal quotes → 401. Store keys UNQUOTED. (Real `python-dotenv` strips quotes; ours doesn't — know your tools.)
2. **Stale `AI_MODEL_NAME` override.** When switching to OpenAI, the leftover `AI_MODEL_NAME=meta/llama-4-maverick...` would ask OpenAI for a Meta model → 404. Comment it out so the per-provider default (`gpt-4o-mini`) applies.

### gpt-4o-mini vs Maverick for structured output

OpenAI has NATIVE structured output via function-calling — fast, no retry loop, no "model not known to support structured output" warning. NVIDIA's LangChain integration wraps Maverick in a `_FallbackRunnable` that can stall. For a billing pipeline that must be reliable and fast, OpenAI is the safer active choice. NVIDIA stays wired as the alternate.

---

## Phase 3 — Steps 3.9 + 3.10 — HTTP layer + end-to-end test (the waiter)

### The 3-file HTTP layer (same shape as the Medicine domain)

| File | Role | Analogy |
|---|---|---|
| `app/schemas/billing.py` | Input/output contract (`BillingRequest` / `BillingResponse`) | The order slip + the receipt format |
| `app/services/billing_service.py` | Wraps `graph.invoke()`, maps state → response | The kitchen manager |
| `app/routers/billing.py` | `POST /api/v1/billing/sale`, picks status code | The waiter at the counter |

A customer never walks into the kitchen (the graph). They order through the waiter (router), who hands it to the manager (service), who runs the kitchen (graph), and brings back food + bill (response).

### Why the billing router has NO Depends(get_db)

The medicine router injects a request-scoped session via `Depends(get_db)` because its repository needs one per request. The billing graph's nodes EACH open their own `SessionLocal()` internally (persist_sale owns its transaction). So the billing endpoint is session-free at the HTTP layer — the graph is self-contained.

Lesson: session ownership is a per-domain decision. Simple CRUD → request-scoped session injected at the router. Self-contained pipeline → the pipeline owns its sessions. Both are valid; pick by who needs the session boundary.

### Why the service layer exists even though it "just calls the graph"

It looks like a pass-through, but it's the seam where future cross-cutting rules land WITHOUT touching the router or the graph:
- auth / role checks ("is this user allowed to bill?")
- rate limiting / idempotency keys (avoid double-charging on a retried request)
- audit logging
- converting the graph's loose dict-state into a typed, validated `BillingResponse`

Keeping the router dumb (HTTP only) and the graph pure (logic only) means the service is where "policy" lives. Same reason the Medicine domain has a service layer even for pass-through reads.

### HTTP status code design

| Situation | Status | Why |
|---|---|---|
| Sale created (sale_id present) | **201 Created** | A new resource (the invoice) was created |
| Nothing billable (sale_id None) | **422 Unprocessable Entity** | We understood the request but couldn't act — unknown medicine, out of stock |
| Empty / missing / oversized input | **422** (automatic) | Pydantic rejects it BEFORE the graph runs — saves a paid LLM call |

422 (not 400) is the REST-correct choice for "syntactically valid JSON that fails business/validation rules." 400 is for malformed requests; 422 is for well-formed-but-unprocessable.

### What the end-to-end HTTP test proved (FastAPI TestClient)

`TestClient` runs the real app in-process — real router → service → graph → OpenAI → MySQL. No separate uvicorn server (which had been hanging). 4 cases, all green:
1. Valid order → 201 + sale_id 6 + full receipt (the entire project in one HTTP call)
2. Unknown medicine → 422; error list traces the failure cascade through all 5 nodes (graceful degradation, no crash)
3. Empty input → 422 from Pydantic before the graph runs
4. Missing field → 422 "Field required"

### The error-cascade in Test 2 (why we see 4 errors for 1 unknown medicine)

```
"Medicine not found: 'Unicorn Dust 999mg'"          ← resolve_medicine
"select_batch: no resolved_items to pick batches"   ← select_batch guard (nothing resolved)
"compute_pricing: no batched_items to price"        ← compute_pricing guard (nothing batched)
"persist_sale: no priced_items to record"           ← persist_sale guard (nothing priced)
```

This is the **collect-then-decide + error-reducer** patterns working together. Each downstream node's guard fires cleanly (no crash) and appends its own note. The `Annotated[list[str], operator.add]` reducer accumulates all four. The client gets a complete picture of why nothing was billed. In a future step we could add conditional edges to short-circuit after the first failure — but the current design is crash-proof and informative, which matters more right now.

### 3 production lessons from the HTTP layer

1. **Validate at the boundary (Pydantic) to fail cheap** — empty input is rejected before the paid LLM call.
2. **Pick the semantically-correct status code** — 201 for created, 422 for unprocessable; don't lazily return 200 for everything.
3. **Keep a service layer even for thin wrappers** — it's where auth/rate-limit/audit will land without a rewrite.

### Phase 3 COMPLETE — what the system now does

One HTTP POST with a plain-English order →
extract (LLM) → resolve (DB) → FEFO batch → server-side Decimal pricing →
atomic 4-table transaction → invoice in MySQL → typed JSON receipt.

Provider-swappable (OpenAI active, NVIDIA alternate) via one `.env` line.
Every money value exact (Decimal). Stock can't go negative (transactional
re-check). Expired/empty batches never sold (FEFO SQL). Price never trusted
from the client (server-side MRP lookup). Every sale auditable (frozen prices
in sale_items).

---
