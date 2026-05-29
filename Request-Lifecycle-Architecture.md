# AI Pharmacy Ecosystem - Complete Request Lifecycle Architecture

## Project Structure

```text id="8a1ttc"
app/
│
├── main.py
│
├── routers/
│   └── medicines.py
│
├── services/
│   └── medicine_service.py
│
├── repositories/
│   └── medicine_repository.py
│
├── schemas/
│   └── medicine.py
│
└── exceptions.py
```

---

# Startup Wiring (Application Boot)

When you run:

```bash id="8j0ayr"
uvicorn app.main:app --reload
```

Python executes:

```python id="wxkgt7"
app/main.py
```

---

## Import Flow

```mermaid
graph TD

Uvicorn["uvicorn app.main:app"]

Uvicorn --> Main["main.py"]

Main --> ImportRouter["from app.routers import medicines"]

ImportRouter --> Medicines["medicines.py"]

Medicines --> APIRouter["router = APIRouter(...)"]

Main --> IncludeRouter["app.include_router(router)"]

IncludeRouter --> FastAPIApp["FastAPI Route Registry"]

FastAPIApp --> Ready["Application Ready"]
```

---

# Dependency Wiring

Inside medicines.py

```python id="3r8w5d"
_repository = InMemoryMedicineRepository()
```

Creates:

```text id="gjlwmc"
ONE repository object
shared by all requests
```

---

Dependency Graph

```mermaid
graph TD

Repo["InMemoryMedicineRepository"]

GetRepo["get_repository()"]

GetService["get_service()"]

Service["MedicineService"]

Repo --> GetRepo

GetRepo --> GetService

GetService --> Service
```

---

# Complete POST Request Flow

Client sends:

```http id="1xzv6l"
POST /api/v1/medicines
```

Body:

```json id="evuixq"
{
  "name": "Dolo",
  "mrp": 50,
  "hsn_code": "3004",
  "manufacturer": "Micro Labs"
}
```

---

# Runtime Request Lifecycle

```mermaid
sequenceDiagram

participant Client
participant FastAPI
participant Router
participant Depends
participant Service
participant Repository
participant Store

Client->>FastAPI: POST /api/v1/medicines

FastAPI->>Router: Match Route

Router->>Depends: Need MedicineService

Depends->>Repository: get_repository()

Repository-->>Depends: _repository

Depends->>Service: get_service(repo)

Service-->>Depends: MedicineService

Depends-->>Router: Inject service

Router->>Service: create_medicine(payload)

Service->>Service: normalize_medicine_name()

Service->>Repository: find_by_normalized_name()

Repository->>Store: Search Dict

Store-->>Repository: None

Repository-->>Service: None

Service->>Repository: add(...)

Repository->>Store: Save MedicineOut

Store-->>Repository: MedicineOut

Repository-->>Service: MedicineOut

Service-->>Router: MedicineOut

Router-->>FastAPI: MedicineOut

FastAPI-->>Client: HTTP 201 JSON
```

---

# Detailed Layer Responsibilities

## Layer 1 - Router

File:

```text id="7wgmsr"
app/routers/medicines.py
```

Functions:

```python id="2b06v4"
create_medicine()

list_medicines()

get_medicine()
```

Responsibilities:

```text id="vqsd9k"
Receive HTTP requests

Convert JSON → MedicineCreate

Call Service

Convert Exceptions → HTTP Errors

Return JSON Response
```

Never:

```text id="6f0zmg"
SQL

Database

Business Logic
```

---

## Layer 2 - Service

File:

```text id="jtvd6o"
app/services/medicine_service.py
```

Functions:

```python id="4th4c9"
create_medicine()

get_medicine()

list_medicines()

normalize_medicine_name()
```

Responsibilities:

```text id="5ulv7r"
Business Rules

Duplicate Check

Validation Beyond Pydantic

Future Pricing Logic

Future FEFO Logic
```

Never:

```text id="m98fgd"
HTTP

Status Codes

Database Queries
```

---

## Layer 3 - Repository

File:

```text id="yw48d7"
app/repositories/medicine_repository.py
```

Functions:

```python id="rtnf3v"
add()

get_by_id()

list_all()

find_by_normalized_name()
```

Responsibilities:

```text id="e6p2gx"
Store Data

Fetch Data

Update Data

Delete Data
```

Never:

```text id="67gtly"
Duplicate Logic

Pricing Logic

HTTP Logic
```

---

# create_medicine() Call Chain

```mermaid
graph TD

A["Router.create_medicine()"]

B["Service.create_medicine()"]

C["normalize_medicine_name()"]

D["Repository.find_by_normalized_name()"]

E["DuplicateMedicineError"]

F["Repository.add()"]

G["MedicineOut"]

A --> B

B --> C

C --> D

D -->|Exists| E

D -->|Not Exists| F

F --> G
```

---

# get_medicine() Call Chain

```mermaid
graph TD

A["Router.get_medicine()"]

B["Service.get_medicine()"]

C["Repository.get_by_id()"]

D["MedicineOut"]

E["None"]

F["HTTP 404"]

A --> B

B --> C

C --> D

C --> E

E --> F
```

---

# list_medicines() Call Chain

```mermaid
graph TD

A["Router.list_medicines()"]

B["Service.list_medicines()"]

C["Repository.list_all()"]

D["List[MedicineOut]"]

A --> B

B --> C

C --> D
```

---

# Current In-Memory Storage

Repository currently stores:

```python id="5i8g6r"
_store = {
    1: MedicineOut(...),
    2: MedicineOut(...),
}
```

Visual:

```mermaid
graph LR

Repository --> Dict["_store dict"]

Dict --> M1["Medicine #1"]

Dict --> M2["Medicine #2"]

Dict --> M3["Medicine #3"]
```

---

# Future Architecture (Phase 2)

Nothing changes in Router.

Nothing changes in Service.

Only Repository changes.

Today:

```mermaid
graph TD

Router --> Service

Service --> InMemoryRepository

InMemoryRepository --> Dict
```

Tomorrow:

```mermaid
graph TD

Router --> Service

Service --> MySQLRepository

MySQLRepository --> MySQL
```

This is the reason the 3-layer architecture exists.

---

# Ultimate Mental Model

```text id="0xsyh1"
Client
   ↓
FastAPI
   ↓
Router
   ↓
Service
   ↓
Repository
   ↓
Database
   ↓
Repository
   ↓
Service
   ↓
Router
   ↓
FastAPI
   ↓
Client
```

Every request follows this exact path.
