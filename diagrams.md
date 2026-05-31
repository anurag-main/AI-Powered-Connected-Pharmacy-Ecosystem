# AI Pharmacy Ecosystem — Diagrams

> Single source of truth for every architecture / flow diagram in this project.
> New diagrams are **appended** under a phase heading. Older ones are never deleted.
> Open this file in any Markdown viewer (VS Code preview, GitHub, Obsidian) to see all diagrams rendered.

---

## Phase 0 — Foundation roadmap

The order of steps to lay the project foundation before any application code is written.

```mermaid
graph TD
    A[0.1 Framework loaded] --> B[0.2 git init]
    B --> C[0.3 Write .gitignore first]
    C --> D[0.4 Lock folder layout]
    D --> E[0.5 Python venv]
    E --> F[0.6 .env + .env.example]
    F --> G[0.7 README skeleton]
    G --> H[0.8 First commit]
    H --> I[Phase 1: FastAPI]

    classDef done fill:#a3e4a3,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef todo fill:#fff,stroke:#1565c0,stroke-width:2px,color:#000
    classDef next fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000

    class A done
    class B,C,D,E,F,G,H todo
    class I next
```

---

## Phase 1 — FastAPI 3-layer architecture

### Phase 1 step roadmap

```mermaid
graph TD
    A[1.1 venv + install deps] --> B[1.2 Folder layout]
    B --> C[1.3 GET /health endpoint]
    C --> D[1.4 Pydantic schemas]
    D --> E[1.5 Repository layer]
    E --> F[1.6 Service layer]
    F --> G[1.7 Router + Depends]
    G --> H[1.8 uvicorn + Swagger]
    H --> I[1.9 First commit]
    I --> J[Phase 2: MySQL]

    classDef start fill:#a3e4a3,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef todo fill:#fff,stroke:#1565c0,stroke-width:2px,color:#000
    classDef next fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000

    class A start
    class B,C,D,E,F,G,H,I todo
    class J next
```

### 3-layer request flow (the heart of Phase 1)

Solid arrows = request going IN. Dotted arrows = response coming BACK.

```mermaid
graph LR
    Client[Client / Browser] -->|POST /medicines| Router
    Router[Router — Reception] -->|MedicineCreate| Service
    Service[Service — Pharmacist] -->|domain object| Repo
    Repo[Repository — Storeroom] -->|insert / fetch| Storage[(Storage)]

    Storage -.->|raw record| Repo
    Repo -.->|Medicine| Service
    Service -.->|MedicineOut| Router
    Router -.->|HTTP 201 JSON| Client

    classDef client fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000
    classDef router fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef service fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef repo fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef storage fill:#e0e0e0,stroke:#424242,stroke-width:2px,color:#000

    class Client client
    class Router router
    class Service service
    class Repo repo
    class Storage storage
```

### Duplicate-detection flow — where does the rule live?

Shows why "Crocin 500MG " vs "Crocin 500mg" deduplication is a **Service** responsibility, not Repository.
The Service normalizes + decides; the Repository only fetches by exact criteria.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as Router
    participant S as Service
    participant Repo as Repository

    C->>R: POST /medicines  name = "Crocin 500MG "
    R->>S: create(MedicineCreate)
    Note over S: normalize name → "crocin 500mg"
    S->>Repo: find_by_normalized_name("crocin 500mg")
    Repo-->>S: existing Medicine found
    Note over S: business rule: duplicates not allowed
    S-->>R: raise DuplicateMedicineError
    R-->>C: HTTP 409 Conflict
```

### Step 1.1 — venv + install ecosystem

How the system Python, the venv, the installed packages, requirements.txt, and .gitignore relate.

```mermaid
graph TD
    SysPy[System Python 3.11] -->|python -m venv venv| Venv

    subgraph Venv[venv folder - sealed kit]
        Pip[pip install]
        Pip --> FA[fastapi - reception software]
        Pip --> UV[uvicorn standard - the doorbell]
        Pip --> PD[pydantic - form validator]
    end

    Venv -->|pip freeze| Reqs[requirements.txt - committed to Git]
    Venv -.->|listed in| GI[.gitignore - venv stays OUT of Git]

    classDef sys fill:#e0e0e0,stroke:#424242,stroke-width:2px,color:#000
    classDef pip fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef pkg fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef reqs fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000
    classDef gi fill:#f8d7da,stroke:#b71c1c,stroke-width:2px,color:#000

    class SysPy sys
    class Pip pip
    class FA,UV,PD pkg
    class Reqs reqs
    class GI gi
```

### Local repo ↔ GitHub remote

How working files flow through .gitignore → staging → local history → remote (origin).

```mermaid
graph LR
    subgraph Laptop[Your Laptop]
        WD[Working Files] -->|.gitignore filters| Staged[Staged Files]
        Staged -->|git commit| LocalRepo[(Local .git)]
    end

    subgraph GitHub[GitHub]
        Origin[(origin remote<br/>anurag-main/...)]
    end

    LocalRepo -->|git push origin main| Origin
    Origin -->|git pull| LocalRepo

    Filtered[Filtered OUT<br/>venv .env pycache<br/>CLAUDE.md agents<br/>hooks skills .claude]
    WD -.->|never staged| Filtered

    classDef local fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef remote fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef filtered fill:#f8d7da,stroke:#b71c1c,stroke-width:2px,color:#000

    class WD,Staged,LocalRepo local
    class Origin remote
    class Filtered filtered
```

### Step 1.1 — requirements.txt reproducibility loop

Shows why we commit requirements.txt (NOT venv/) — so any teammate or future machine recreates the exact same package set with one command.

```mermaid
graph LR
    You[Your laptop] -->|pip install fastapi uvicorn pydantic| YouVenv[(your venv)]
    YouVenv -->|pip freeze| Req[requirements.txt]
    Req -->|git commit + push| Git[(GitHub origin)]
    Git -->|git clone + pull| Mate[Teammate laptop]
    Mate -->|pip install -r requirements.txt| MateVenv[(their venv)]
    MateVenv -.identical pkgs.-> YouVenv

    classDef you fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef mate fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef file fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000
    classDef git fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000

    class You,YouVenv you
    class Mate,MateVenv mate
    class Req file
    class Git git

```

### Step 1.2 — backend folder layout (the locked floor plan)

The directory structure for `pharmacy-core-backend/`. Each folder maps to one pharmacy zone with one clear responsibility.

```mermaid
graph TD
    Root[pharmacy-core-backend/]
    Root --> Venv[venv/ — gitignored]
    Root --> Req[requirements.txt — committed]
    Root --> EnvFiles[.env gitignored<br/>.env.example committed]
    Root --> App[app/]

    App --> Main[main.py — FastAPI entrypoint]
    App --> Exc[exceptions.py — custom errors]
    App --> Core[core/ — config & settings]
    App --> Routers[routers/ — HTTP layer]
    App --> Services[services/ — business logic]
    App --> Repos[repositories/ — storage layer]
    App --> Schemas[schemas/ — Pydantic models]

    classDef root fill:#a3e4a3,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef ent fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef folder fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef ignored fill:#f8d7da,stroke:#b71c1c,stroke-width:2px,color:#000
    classDef file fill:#fff,stroke:#1565c0,stroke-width:2px,color:#000

    class Root,App root
    class Main,Exc ent
    class Core,Routers,Services,Repos,Schemas folder
    class Venv ignored
    class Req,EnvFiles file

```

### Step 1.3 — GET /health endpoint flow

How a load balancer's /health probe travels through FastAPI's decorator into your function and back.

```mermaid
graph LR
    LB[Load balancer<br/>or uptime monitor] -->|GET /health every 5s| Decor

    subgraph App[FastAPI app on port 8000]
        Decor["@app.get('/health')<br/>decorator"]
        Decor --> Fn[health function]
        Fn -->|return dict| Resp[Response builder]
    end

    Resp -->|HTTP 200 application/json<br/>status:ok| LB

    classDef ext fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef route fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef fn fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef resp fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000

    class LB ext
    class Decor route
    class Fn fn
    class Resp resp
```

### Step 1.4 — Pydantic schema split (input vs output)

Why we never use one schema for both: input fields (MedicineCreate) ⊆ DB fields ⊆ output fields (MedicineOut), and some DB fields (cost_price, supplier_notes) never leave the repository.

```mermaid
graph TD
    Client[Client / Browser]

    Client -->|POST JSON| In[MedicineCreate input schema<br/>name mrp hsn_code manufacturer]
    In --> Svc[Service business logic]
    Svc <--> Repo[(Repository / DB<br/>FULL record: id name mrp hsn_code<br/>manufacturer cost_price<br/>supplier_notes created_at)]
    Svc --> Out[MedicineOut output schema<br/>id name mrp hsn_code<br/>manufacturer created_at]
    Out -->|response JSON| Client

    Repo -.->|fields that NEVER leave the repo| Danger[cost_price<br/>supplier_notes<br/>profit_margin]

    classDef ext fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef inp fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef svc fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef repo fill:#e0e0e0,stroke:#424242,stroke-width:2px,color:#000
    classDef outp fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000
    classDef danger fill:#f8d7da,stroke:#b71c1c,stroke-width:2px,color:#000

    class Client ext
    class In inp
    class Svc svc
    class Repo repo
    class Out outp
    class Danger danger
```

### Step 1.5 — Repository contract (service ↔ in-memory repo)

The 4 repo methods, and how the service's "normalize then ask" flow lands on `find_by_normalized_name`. The repo never decides; it only fetches/stores.

```mermaid
graph TB
    subgraph Service[Service layer - Pharmacist]
        Normalize[normalize input name]
        DecideDup[decide: is duplicate?]
        Normalize --> DecideDup
    end

    subgraph Repository[InMemoryMedicineRepository]
        Add[add — assigns id and created_at]
        Get[get_by_id]
        List[list_all]
        Find[find_by_normalized_name]
        Store[(_store: dict id → MedicineOut<br/>_next_id: int counter)]
        Add <--> Store
        Get <--> Store
        List <--> Store
        Find <--> Store
    end

    DecideDup -->|find_by_normalized_name<br/>'crocin 500mg'| Find
    Find -.->|MedicineOut or None| DecideDup

    classDef svc fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef repo fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef store fill:#e0e0e0,stroke:#424242,stroke-width:2px,color:#000
    classDef method fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000

    class Normalize,DecideDup svc
    class Repository repo
    class Add,Get,List,Find method
    class Store store
```

### POST /medicines — full request lifecycle

Shows what every layer DOES to the data on the way IN (Frontend → MedicineCreate → Service → Repository) and the way OUT (Repository attaches id+created_at → MedicineOut → Response → Frontend).

```mermaid
graph TB
    FE[Frontend / Client]
    FE -->|POST /medicines<br/>JSON: name mrp hsn_code manufacturer| Router

    subgraph Backend[FastAPI backend]
        Router[Router — receive HTTP]
        MC[MedicineCreate<br/>Pydantic validates JSON shape]
        Svc[Service<br/>normalize name + check duplicate]
        Repo[Repository<br/>assigns id + created_at,<br/>stores in _store]
        MO[MedicineOut<br/>full record with server fields]

        Router --> MC
        MC --> Svc
        Svc -->|primitive args:<br/>name mrp hsn_code manufacturer| Repo
        Repo --> MO
        MO --> Svc
        Svc --> Router
    end

    Router -->|HTTP 201<br/>JSON: id name mrp hsn_code<br/>manufacturer created_at| FE

    classDef ext fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef router fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef pyd fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef svc fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef repo fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000

    class FE ext
    class Router router
    class MC,MO pyd
    class Svc svc
    class Repo repo
```

### Step 1.6 — MedicineService.create_medicine decision flow

The 3 steps the service runs on every POST, and where each one routes if it short-circuits (duplicate → 409, clean → 201).

```mermaid
graph LR
    R[Router] -->|MedicineCreate| S1

    subgraph Service[MedicineService.create_medicine]
        S1[1 normalize name] --> S2[2 ask repo find_by_normalized_name]
        S2 -->|found| S3[raise DuplicateMedicineError]
        S2 -->|None| S4[3 call repo.add new record]
    end

    S3 -.->|caught by router| R409[HTTP 409 Conflict]
    S4 -->|MedicineOut| R201[HTTP 201 Created]

    classDef router fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef step fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef err fill:#f8d7da,stroke:#b71c1c,stroke-width:2px,color:#000
    classDef ok fill:#a3e4a3,stroke:#1b5e20,stroke-width:2px,color:#000

    class R router
    class S1,S2,S4 step
    class S3 err
    class R409 err
    class R201 ok
```

### Step 1.7 — Router with Depends() — full request lifecycle

Shows how FastAPI resolves Depends() per request, builds the service, calls the endpoint, and translates domain exceptions into HTTP status codes.

```mermaid
graph TB
    Client[Client] -->|POST /api/v1/medicines| FA[FastAPI app]

    subgraph App[main.py]
        FA -->|matches prefix| Router
    end

    subgraph RouterFile[app/routers/medicines.py]
        Router[APIRouter prefix=/api/v1/medicines]
        Router -->|on request| Resolve{Depends resolve}
        Resolve -->|calls get_repository| GR[get_repository returns shared InMemoryRepo]
        Resolve -->|calls get_service| GS[get_service builds MedicineService]
        GS --> EP[endpoint: create_medicine]
        GR --> GS
    end

    EP -->|MedicineCreate + service| Svc[MedicineService.create_medicine]
    Svc -->|MedicineOut OR DuplicateMedicineError| EP

    EP -->|success| OK[HTTP 201 JSON]
    EP -.->|catch DuplicateMedicineError| Err[raise HTTPException 409]
    Err --> ErrResp[HTTP 409 JSON: detail message]

    OK --> Client
    ErrResp --> Client

    classDef ext fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef router fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef dep fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef svc fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000
    classDef ok fill:#a3e4a3,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef err fill:#f8d7da,stroke:#b71c1c,stroke-width:2px,color:#000

    class Client,FA ext
    class Router,EP router
    class Resolve,GR,GS dep
    class Svc svc
    class OK ok
    class Err,ErrResp err
```

---

## Phase 2 — Persistent Storage (MySQL + SQLAlchemy + Alembic)

### Phase 2 step roadmap

The order matters: get DB connectivity working before models, models before migrations, migrations before sessions, sessions before the new repository.

```mermaid
graph TD
    A[2.1 DB setup<br/>SQLite or MySQL + driver] --> B[2.2 ERD design<br/>medicines batches customers sales]
    B --> C[2.3 SQLAlchemy 2.0 models<br/>Medicine ORM class]
    C --> D[2.4 Alembic init<br/>+ first migration]
    D --> E[2.5 DB session + Depends<br/>per-request session]
    E --> F[2.6 SQLAlchemyMedicineRepository<br/>same interface SQL backend]
    F --> G[2.7 Swap repos in router<br/>service file untouched]
    G --> H[2.8 Batch model + FEFO basics<br/>expiry-aware]
    H --> I[2.9 Phase 2 commit]
    I --> J[Phase 3: LangGraph AI]

    classDef start fill:#a3e4a3,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef todo fill:#fff,stroke:#1565c0,stroke-width:2px,color:#000
    classDef next fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000

    class A start
    class B,C,D,E,F,G,H,I todo
    class J next
```

### Step 2.2 — Full pharmacy ERD

Six entities, designed up front so we never refactor primary keys / foreign keys later.
Phase 2 implements only MEDICINES + BATCHES (steps 2.3–2.8); CUSTOMERS / SALES / SALE_ITEMS / USERS land in Phase 3.

```mermaid
erDiagram
    MEDICINES ||--o{ BATCHES : "stocked as"
    BATCHES ||--o{ SALE_ITEMS : "sold in"
    CUSTOMERS ||--o{ SALES : places
    SALES ||--|{ SALE_ITEMS : contains
    USERS ||--o{ SALES : "logged by"

    MEDICINES {
        int id PK
        string name
        string normalized_name UK "indexed for dedup"
        decimal mrp
        string hsn_code
        string manufacturer "nullable"
        datetime created_at
        datetime updated_at
    }

    BATCHES {
        int id PK
        int medicine_id FK
        string batch_number
        date expiry_date "indexed for FEFO"
        int quantity "remaining stock"
        decimal cost_price "INTERNAL never exposed"
        datetime created_at
    }

    CUSTOMERS {
        int id PK
        string name
        string phone UK "indexed"
        datetime created_at
    }

    SALES {
        int id PK
        int customer_id FK "nullable for walk-ins"
        int user_id FK "who rang it up"
        decimal total_amount
        datetime created_at "indexed for reports"
    }

    SALE_ITEMS {
        int id PK
        int sale_id FK
        int batch_id FK "FEFO-selected"
        int quantity
        decimal unit_price "MRP snapshot"
        decimal subtotal
    }

    USERS {
        int id PK
        string email UK
        string password_hash
        string role "pharmacist or admin"
        datetime created_at
    }
```

### Step 2.3 — Where each Medicine "shape" lives (HTTP / Domain / DB / Foundation)

The 3-way class separation senior backends always have. Conflating any two re-introduces the Phase-1 mistakes we already cured.

```mermaid
graph TB
    subgraph HTTP[HTTP layer — app/schemas/medicine.py]
        MC[MedicineCreate<br/>input contract]
        MO[MedicineOut<br/>output contract]
    end

    subgraph Domain[Domain layer — unchanged]
        Svc[MedicineService<br/>business rules]
    end

    subgraph DB[DB layer — app/models/medicine.py NEW]
        ORM[Medicine ORM<br/>maps to medicines table]
    end

    subgraph Foundation[Foundation — app/core/database.py NEW]
        Eng[engine + SessionLocal + Base]
    end

    MC -->|Pydantic validates| Svc
    Svc -->|domain reads/writes| ORM
    ORM -->|SELECT/INSERT via session| MySQL[(MySQL medicines table)]
    ORM -.->|from_attributes hook| MO
    MO -->|FastAPI serializes| Resp[HTTP JSON response]

    Eng -.->|provides Base + Session| ORM

    classDef http fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef svc fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef db fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef found fill:#ffe082,stroke:#e65100,stroke-width:2px,color:#000
    classDef mysql fill:#e0e0e0,stroke:#424242,stroke-width:2px,color:#000

    class MC,MO http
    class Svc svc
    class ORM db
    class Eng found
    class MySQL mysql
    class Resp http
```

### Step 2.5 — Per-request DB session lifecycle (yield-based Depends)

One Session per HTTP request: opened on entry, closed on exit even if the endpoint raised. Connections borrowed from the engine pool, returned on close.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant FA as FastAPI
    participant GD as get_db
    participant S as Session
    participant E as Engine + Pool
    participant DB as MySQL

    C->>FA: POST /api/v1/medicines
    FA->>GD: resolve Depends(get_db)
    GD->>S: SessionLocal()
    S->>E: borrow connection
    E-->>S: connection
    GD-->>FA: yield session
    FA->>S: endpoint uses session
    S->>DB: SELECT / INSERT
    DB-->>S: rows / row id
    S-->>FA: endpoint returns
    FA->>GD: post-yield cleanup
    GD->>S: session.close()
    S->>E: connection back to pool
    FA-->>C: HTTP 201 JSON
```

### Step 2.8 — Medicine 1:N Batches + FEFO selection

One medicine → many batches. FEFO query picks the batch with the soonest non-expired expiry that still has stock.

```mermaid
graph TD
    M[Crocin 500mg id=1]

    M -->|1:N| B1[B-001 qty=50 exp 2026-06-01]
    M -->|1:N| B2[B-002 qty=30 exp 2026-12-15]
    M -->|1:N| B3[B-003 qty=10 exp 2026-08-10]

    Q[FEFO query: next batch?]
    Q -->|WHERE medicine_id=1<br/>AND quantity > 0<br/>AND expiry_date > NOW<br/>ORDER BY expiry_date ASC<br/>LIMIT 1| B1

    classDef med fill:#bbdefb,stroke:#0d47a1,stroke-width:2px,color:#000
    classDef pick fill:#a3e4a3,stroke:#1b5e20,stroke-width:2px,color:#000
    classDef other fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef query fill:#c8e6c9,stroke:#1b5e20,stroke-width:2px,color:#000

    class M med
    class B1 pick
    class B2,B3 other
    class Q query
```

---

## Phase 3 / Step 3.1 — NVIDIA + Mistral-Nemotron smoke test (verified path)

The exact path traced during the verification call. Every future node call follows this same path — only the prompt content differs.

```mermaid
sequenceDiagram
    autonumber
    participant T as smoke test
    participant L as get_llm()
    participant C as app/ai/config.py
    participant V as ChatNVIDIA<br/>(langchain-nvidia-ai-endpoints)
    participant N as NVIDIA endpoint<br/>integrate.api.nvidia.com/v1

    T->>L: get_llm()
    L->>C: read LLM_PROVIDER + NVIDIA_API_KEY + MODEL_NAME
    C-->>L: nvidia, nvapi-..., mistralai/mistral-nemotron
    L->>L: _is_placeholder(key)? → False
    L->>V: ChatNVIDIA(model, api_key, temperature=0.0)
    V-->>L: client
    L-->>T: cached client (lru_cache size=1)
    T->>V: llm.invoke("Reply EXACTLY: pharmacy-ok")
    V->>N: POST /chat/completions<br/>Authorization: Bearer nvapi-...
    N-->>V: 200 OK<br/>{"choices":[{"message":{"content":"pharmacy-ok"}}]}
    V-->>T: AIMessage(content="pharmacy-ok")

    Note over T,N: SMOKE PASS — proves auth, routing, model existence,<br/>LangChain contract, and temperature determinism all good.
```

```mermaid
graph LR
    subgraph user[Your code — provider-agnostic]
        N1[extract_intent node]
        N2[resolve_medicine node]
        N3[select_batch node]
        N4[compute_pricing node]
    end

    subgraph factory[app/ai/llm.py — the only place that knows providers]
        GL{{"get_llm()<br/>cached"}}
        BN["_build_nvidia_client()"]
        BO["_build_openai_client()"]
    end

    subgraph providers[Hosted LLM providers]
        CN[ChatNVIDIA<br/>mistral-nemotron]
        CO[ChatOpenAI<br/>gpt-4o-mini]
    end

    N1 --> GL
    N2 --> GL
    N3 --> GL
    N4 --> GL
    GL -->|LLM_PROVIDER=nvidia| BN
    GL -->|LLM_PROVIDER=openai| BO
    BN --> CN
    BO --> CO

    classDef code fill:#fff5d6,stroke:#a86b00,stroke-width:2px,color:#000
    classDef router fill:#e3f0ff,stroke:#003a8c,stroke-width:2px,color:#000
    classDef provider fill:#e5fbe5,stroke:#1f7a1f,stroke-width:2px,color:#000

    class N1,N2,N3,N4 code
    class GL,BN,BO router
    class CN,CO provider
```

---

## Phase 3 / Step 3.2 — `ExtractedIntent` schema (the notebook with boxes)

### The candy-shop analogy → the schema shape

```mermaid
graph TB
    subgraph notebook[Notebook page = one MedicineItem]
        N1["Box 1<br/>Name<br/>'Crocin 500mg'"]
        N2["Box 2<br/>Quantity<br/>2"]
        N3["Box 3<br/>Unit<br/>'strip'"]
    end

    subgraph top[Top of stack of pages = ExtractedIntent]
        T1["Customer name<br/>'Anurag'"]
        T2["Customer phone<br/>'9876543210'"]
        T3["Items list<br/>= many MedicineItem pages"]
    end

    T3 -.contains many.-> notebook

    classDef box fill:#fff5d6,stroke:#a86b00,stroke-width:2px,color:#000
    classDef top fill:#e3f0ff,stroke:#003a8c,stroke-width:2px,color:#000
    class N1,N2,N3 box
    class T1,T2,T3 top
```

### What happens at runtime

```mermaid
sequenceDiagram
    autonumber
    participant U as Pharmacist input
    participant L as Maverick (LLM)
    participant P as Pydantic (the mom)
    participant S as ExtractedIntent

    U->>L: "2 strips Crocin 500mg for Anurag 9876543210"
    Note over L: LLM tries to fill the notebook<br/>(produces JSON)
    L->>P: JSON output
    Note over P: Mom checks every box<br/>- types correct?<br/>- nothing missing?<br/>- no extra boxes?
    alt Mom approves
        P-->>S: Valid ExtractedIntent instance
        S-->>U: Ready to use downstream
    else Mom rejects
        P-->>L: ValidationError → retry
    end
```

---

## Phase 3 / Step 3.2 — File 2 — System prompt = Rohit's instruction card

### How the prompt sits next to the schema

```mermaid
graph LR
    subgraph card[Rohit's instruction card<br/>= billing_prompts.py]
        R[Role: 'You are a strict order-taker']
        T[Task: 'Parse the sentence']
        RU[Rules: 'don't invent, lowercase, etc.']
        E[Examples: input → output]
    end

    subgraph notebook[The notebook<br/>= extracted_intent.py]
        SCH[Pydantic schema<br/>ExtractedIntent]
    end

    subgraph helper[Rohit at work<br/>= extract_intent node]
        L[LLM Maverick]
    end

    card -- glued to --> L
    notebook -- glued to --> L
    KID["Kid says:<br/>'2 strips Crocin for Anurag'"] --> L
    L --> OUT["Filled notebook<br/>= ExtractedIntent instance"]

    classDef card fill:#ffe5e5,stroke:#a83333,stroke-width:2px,color:#000
    classDef book fill:#fff5d6,stroke:#a86b00,stroke-width:2px,color:#000
    classDef helper fill:#e3f0ff,stroke:#003a8c,stroke-width:2px,color:#000
    classDef io fill:#e5fbe5,stroke:#1f7a1f,stroke-width:2px,color:#000

    class R,T,RU,E,card card
    class SCH,notebook book
    class L,helper helper
    class KID,OUT io
```

### The 5-section prompt structure (industry standard)

```mermaid
graph TB
    P["System prompt<br/>EXTRACT_INTENT_SYSTEM_PROMPT_V1"]
    P --> S1["1. ROLE<br/>'You are a strict pharmacy order-taker'"]
    P --> S2["2. TASK<br/>'Parse the sentence into ExtractedIntent fields'"]
    P --> S3["3. RULES<br/>'never invent, lowercase, leave optional fields null'"]
    P --> S4["4. OUTPUT FORMAT<br/>'Return JSON matching the schema, nothing else'"]
    P --> S5["5. EXAMPLES<br/>Few-shot: 1-3 input → output pairs"]

    classDef prompt fill:#ffe5e5,stroke:#a83333,stroke-width:2px,color:#000
    classDef section fill:#fff5d6,stroke:#a86b00,stroke-width:2px,color:#000
    class P prompt
    class S1,S2,S3,S4,S5 section
```

---

## Phase 3 / Step 3.2 — File 3 — `extract_intent` node (Rohit's work routine)

### Inside one call to the node

```mermaid
flowchart TD
    A["state in:<br/>pharmacist_input = '2 strips Crocin...'"] --> B{Empty<br/>input?}
    B -- yes --> Z["return:<br/>state.errors += ['empty input']"]
    B -- no --> C["llm = get_llm()<br/>= cached ChatNVIDIA Maverick"]
    C --> D["structured_llm =<br/>llm.with_structured_output(ExtractedIntent)"]
    D --> E["messages = [<br/>  SystemMessage(prompt),<br/>  HumanMessage(input)<br/>]"]
    E --> F["result = structured_llm.invoke(messages)"]
    F --> G["NVIDIA API call<br/>integrate.api.nvidia.com/v1<br/>(real LLM round trip)"]
    G --> H["Pydantic validates JSON<br/>→ ExtractedIntent instance"]
    H --> I["return:<br/>state.extracted_intent =<br/>result.model_dump()"]

    classDef start fill:#e3f0ff,stroke:#003a8c,stroke-width:2px,color:#000
    classDef step fill:#fff5d6,stroke:#a86b00,stroke-width:2px,color:#000
    classDef net fill:#ffe5e5,stroke:#a83333,stroke-width:2px,color:#000
    classDef out fill:#e5fbe5,stroke:#1f7a1f,stroke-width:2px,color:#000

    class A start
    class B,C,D,E,F,H step
    class G net
    class Z,I out
```

### How the 4 files for Step 3.2 fit together

```mermaid
graph TB
    subgraph state[Phase 3 / app/ai/state/]
        S["BillingState<br/>TypedDict"]
    end
    subgraph schemas[Phase 3 / app/ai/schemas/]
        SCH["ExtractedIntent<br/>+ MedicineItem"]
    end
    subgraph prompts[Phase 3 / app/ai/prompts/]
        PR["EXTRACT_INTENT_SYSTEM_PROMPT_V1"]
    end
    subgraph llm[Phase 3 / app/ai/]
        LL["get_llm()<br/>ChatNVIDIA Maverick"]
    end
    subgraph node[Phase 3 / app/ai/nodes/]
        N["extract_intent(state)"]
    end

    S -. read .-> N
    SCH -. wraps LLM .-> N
    PR -. SystemMessage .-> N
    LL -. invoked by .-> N
    N -. writes .-> S

    classDef def fill:#fff5d6,stroke:#a86b00,stroke-width:2px,color:#000
    classDef node fill:#e3f0ff,stroke:#003a8c,stroke-width:2px,color:#000
    class S,SCH,PR,LL def
    class N node
```

---
