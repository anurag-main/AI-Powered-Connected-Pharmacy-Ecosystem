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

---
