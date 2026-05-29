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
