# 🏥 AI-Powered Connected Pharmacy Ecosystem
### Production-Grade Tech Stack & Architecture Document

---

## 📌 Table of Contents

1. [Project Vision](#1-project-vision)
2. [Core Product Modules](#2-core-product-modules)
3. [Final Recommended Tech Stack](#3-final-recommended-tech-stack)
4. [Development Architecture](#4-development-architecture)
5. [Production Deployment Architecture](#5-production-deployment-architecture)
6. [AI Workflow Architecture](#6-ai-workflow-architecture)
7. [LangGraph Multi-Agent Architecture](#7-langgraph-multi-agent-architecture)
8. [Event-Driven Workflow](#8-event-driven-workflow)
9. [Database Architecture](#9-database-architecture)
10. [Folder Structure](#10-folder-structure)
11. [Learning Roadmap](#11-learning-roadmap)
12. [Engineering Principles](#12-engineering-principles)
13. [Stack Summary](#13-final-stack-summary)

---

## 1. Project Vision

> **AI Operating System for Pharmacies & Chronic Healthcare**

A production-grade AI platform combining:

- 🎙️ Voice-based pharmacy billing
- 📦 Inventory automation
- 🔮 AI refill prediction
- 👴 Elderly medicine reminders
- 🗣️ Regional-language voice AI (Marathi / Hindi)
- 🤖 Multi-agent orchestration
- ☁️ SaaS pharmacy management

---

## 2. Core Product Modules

### 🏪 Pharmacy Side

| Module | Features |
|---|---|
| Voice Billing | Speak medicines, auto-generate bills |
| Invoice Generation | PDF invoices, GST-ready |
| Inventory Management | Real-time stock tracking |
| Batch & Expiry Tracking | Auto-alerts before expiry |
| Supplier Management | PO generation, supplier contacts |
| Customer Management | Customer profiles, purchase history |

### 📱 Customer Side

| Module | Features |
|---|---|
| Medicine Tracking | Daily intake tracking |
| Refill Prediction | AI-predicted refill dates |
| Voice Reminders | Marathi / Hindi reminders |
| Family Notifications | Alerts to family members |
| WhatsApp Alerts | Automated WhatsApp messages |

### 🤖 AI Layer

| Module | Features |
|---|---|
| Voice Understanding | Marathi / Hinglish STT |
| Medicine Extraction | NLP-based medicine parsing |
| Agent Orchestration | LangGraph multi-agent |
| RAG Knowledge System | Medicine knowledge retrieval |
| Reminder Intelligence | Smart reminder scheduling |

---

## 3. Final Recommended Tech Stack

### Frontend Stack

```
Pharmacy Dashboard  →  Next.js + JavaScript + TailwindCSS + ShadCN UI
Customer Mobile App →  React Native
```

> ⚠️ **Note:** JavaScript is used throughout — no TypeScript.

### Backend Stack

```
Core Backend  →  FastAPI (Python 3.12+)
```

**Why FastAPI?**
- ✅ Excellent Python ecosystem
- ✅ Async support (perfect for AI tasks)
- ✅ AI-friendly integrations
- ✅ High performance with Uvicorn

### Database Stack

```
Primary DB    →  MySQL
Cache Layer   →  Redis
Vector DB     →  ChromaDB (→ Pinecone / Qdrant later)
```

### AI Stack

```
Agent Orchestration  →  LangGraph
LLM Provider         →  OpenAI (GPT-4.1 / GPT-4o)
Embeddings           →  OpenAI Embeddings
```

### Voice AI Stack

```
Speech-To-Text  →  Deepgram / Whisper / Google Speech
Text-To-Speech  →  ElevenLabs / Azure Speech / Google TTS
```

### Communication Stack

```
WhatsApp   →  Twilio WhatsApp API  OR  Meta WhatsApp Cloud API
Calling    →  Twilio / Exotel
```

### DevOps Stack

```
Containerization  →  Docker
Orchestration     →  Docker Compose
CI/CD             →  GitHub Actions
Reverse Proxy     →  NGINX
Hosting           →  VPS (Hetzner / DigitalOcean) → AWS / Azure
```

---

## 4. Development Architecture

> ✅ Start with **Modular Monolith** — NOT microservices.

**Why Modular Monolith first?**
- Easier learning curve
- Easier debugging
- Faster development cycles
- Less infrastructure complexity
- Ideal for startups & MVPs

```mermaid
graph TD
    A[🖥️ Next.js Frontend]
    B[⚙️ FastAPI Backend]

    C[💳 Billing Module]
    D[📦 Inventory Module]
    E[⏰ Reminder Module]
    F[🎙️ Voice AI Module]
    G[🤖 LangGraph Agent Module]

    H[(🗄️ MySQL)]
    I[(⚡ Redis)]
    J[(🔍 ChromaDB)]

    K[🧠 OpenAI APIs]

    A --> B

    B --> C
    B --> D
    B --> E
    B --> F
    B --> G

    C --> H
    D --> H
    E --> H

    B --> I

    G --> J
    G --> K

    style A fill:#3b82f6,color:#fff
    style B fill:#10b981,color:#fff
    style G fill:#8b5cf6,color:#fff
    style K fill:#f59e0b,color:#fff
    style H fill:#ef4444,color:#fff
    style I fill:#ef4444,color:#fff
    style J fill:#ef4444,color:#fff
```

---

## 5. Production Deployment Architecture

```mermaid
graph TD
    A[👨‍💻 Developer Push]
    --> B[🐙 GitHub Repository]

    B --> C[⚙️ GitHub Actions CI/CD]

    C --> D[🐳 Docker Build]

    D --> E[📦 Docker Image Registry]

    E --> F[🖥️ VPS Server]

    F --> G[🔀 NGINX Reverse Proxy]

    G --> H[🌐 Next.js Container]
    G --> I[⚙️ FastAPI Container]

    I --> J[(🗄️ MySQL)]
    I --> K[(⚡ Redis)]
    I --> L[(🔍 ChromaDB)]

    style A fill:#6366f1,color:#fff
    style C fill:#f59e0b,color:#fff
    style D fill:#3b82f6,color:#fff
    style G fill:#10b981,color:#fff
    style J fill:#ef4444,color:#fff
    style K fill:#ef4444,color:#fff
    style L fill:#ef4444,color:#fff
```

---

## 6. AI Workflow Architecture

```mermaid
graph TD
    A[🎙️ Voice Input]
    --> B[📝 Speech-To-Text\nDeepgram / Whisper]

    B --> C[🌐 Language Normalization\nMarathi / Hinglish → English]

    C --> D[💊 Medicine Extraction Agent\nNLP + LLM]

    D --> E[💳 Billing Agent\nInvoice Generation]

    E --> F[📦 Inventory Agent\nStock Deduction]

    F --> G[📅 Expiry Agent\nBatch Validation]

    G --> H[⏰ Reminder Agent\nSchedule Creation]

    H --> I[🔔 Voice Reminder\nElevenLabs / Azure TTS]

    style A fill:#6366f1,color:#fff
    style B fill:#3b82f6,color:#fff
    style C fill:#3b82f6,color:#fff
    style D fill:#8b5cf6,color:#fff
    style E fill:#8b5cf6,color:#fff
    style F fill:#8b5cf6,color:#fff
    style G fill:#8b5cf6,color:#fff
    style H fill:#8b5cf6,color:#fff
    style I fill:#10b981,color:#fff
```

---

## 7. LangGraph Multi-Agent Architecture

```mermaid
graph TD
    A[🧠 LangGraph Orchestrator]

    A --> B[💊 Medicine Extraction Agent]
    A --> C[💳 Billing Agent]
    A --> D[📦 Inventory Agent]
    A --> E[📅 Expiry Agent]
    A --> F[⏰ Reminder Agent]

    B --> G[🔧 Medicine Tool\nSearch + Validate]
    C --> H[🔧 Invoice Tool\nGenerate + Store]
    D --> I[🔧 Inventory Tool\nDeduct + Update]
    E --> J[🔧 Expiry Tool\nCheck + Alert]
    F --> K[🔧 Voice Tool\nSchedule + Notify]

    A --> L[(💾 Agent State\nLangGraph Memory)]

    style A fill:#8b5cf6,color:#fff
    style B fill:#3b82f6,color:#fff
    style C fill:#3b82f6,color:#fff
    style D fill:#3b82f6,color:#fff
    style E fill:#3b82f6,color:#fff
    style F fill:#3b82f6,color:#fff
    style G fill:#10b981,color:#fff
    style H fill:#10b981,color:#fff
    style I fill:#10b981,color:#fff
    style J fill:#10b981,color:#fff
    style K fill:#10b981,color:#fff
    style L fill:#f59e0b,color:#fff
```

---

## 8. Event-Driven Workflow

```mermaid
graph TD
    A[📄 Invoice Created]
    --> B[📦 Inventory Updated\nAuto stock deduction]

    A --> C[💊 Medicine Usage Created\nDaily dose tracking begins]

    C --> D[⏰ Reminder Schedule Generated\nAI calculates refill date]

    B --> E[🚨 Low Stock Alert\nThreshold breached]

    E --> F[📧 Supplier Notification\nAuto PO or WhatsApp alert]

    D --> G[📱 WhatsApp Reminder\nSent to patient / family]

    D --> H[📞 Voice Call Reminder\nMarathi / Hindi call]

    style A fill:#6366f1,color:#fff
    style E fill:#ef4444,color:#fff
    style F fill:#f59e0b,color:#fff
    style G fill:#10b981,color:#fff
    style H fill:#10b981,color:#fff
```

---

## 9. Database Architecture

```mermaid
erDiagram

    CUSTOMER ||--o{ INVOICE : has
    INVOICE ||--o{ INVOICE_ITEM : contains
    MEDICINE ||--o{ INVENTORY : tracked_in
    MEDICINE ||--o{ BATCH : contains
    CUSTOMER ||--o{ MEDICINE_USAGE : tracks
    INVOICE_ITEM }o--|| MEDICINE : references
    BATCH }o--|| INVENTORY : linked_to

    CUSTOMER {
        uuid id PK
        string name
        string phone
        string language
        string whatsapp_number
        date created_at
    }

    MEDICINE {
        uuid id PK
        string name
        string generic_name
        string strength
        string manufacturer
        string category
    }

    INVENTORY {
        uuid id PK
        uuid medicine_id FK
        int quantity
        int reorder_level
        date last_updated
    }

    BATCH {
        uuid id PK
        uuid medicine_id FK
        string batch_number
        date expiry_date
        int quantity
        decimal purchase_price
    }

    INVOICE {
        uuid id PK
        uuid customer_id FK
        decimal total
        decimal gst_amount
        string status
        date created_at
    }

    INVOICE_ITEM {
        uuid id PK
        uuid invoice_id FK
        uuid medicine_id FK
        int quantity
        decimal unit_price
        decimal total_price
    }

    MEDICINE_USAGE {
        uuid id PK
        uuid customer_id FK
        uuid medicine_id FK
        int daily_usage
        date start_date
        date expected_finish_date
        boolean reminder_active
    }
```

---

## 10. Folder Structure

```
project-root/
│
├── 🌐 frontend/                     # Next.js (JavaScript)
│   ├── app/
│   │   ├── (dashboard)/
│   │   ├── (billing)/
│   │   └── (inventory)/
│   ├── components/
│   ├── lib/
│   └── public/
│
├── ⚙️ backend/                      # FastAPI (Python)
│   ├── app/
│   │   ├── api/                     # Route handlers
│   │   │   ├── v1/
│   │   │   │   ├── billing.py
│   │   │   │   ├── inventory.py
│   │   │   │   ├── customers.py
│   │   │   │   └── reminders.py
│   │   ├── agents/                  # LangGraph agents
│   │   │   ├── medicine_extraction.py
│   │   │   ├── billing_agent.py
│   │   │   ├── inventory_agent.py
│   │   │   └── reminder_agent.py
│   │   ├── services/                # Business logic
│   │   ├── repositories/            # DB access layer
│   │   ├── models/                  # SQLAlchemy models
│   │   ├── schemas/                 # Pydantic schemas
│   │   ├── workflows/               # LangGraph workflows
│   │   ├── ai/                      # AI utilities
│   │   ├── voice/                   # STT / TTS
│   │   └── core/                    # Config, DB, security
│   ├── tests/
│   └── requirements.txt
│
├── 📱 mobile/                       # React Native app
│   ├── src/
│   │   ├── screens/
│   │   ├── components/
│   │   └── services/
│
├── 🐳 docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── Dockerfile.nginx
│
├── 🔀 nginx/
│   └── nginx.conf
│
├── 📚 docs/
│   └── architecture.md
│
└── docker-compose.yml
```

---

## 11. Learning Roadmap

```mermaid
gantt
    title AI Pharmacy Platform - Learning & Build Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 0 - Foundation
    Docker Basics           :a1, 2025-01-01, 14d
    MySQL + FastAPI          :a2, after a1, 14d
    GitHub Actions CI/CD     :a3, after a2, 7d

    section Phase 1 - Pharmacy Backend
    SQLAlchemy + Alembic     :b1, after a3, 14d
    Billing & Invoices       :b2, after b1, 14d
    Inventory Management     :b3, after b2, 14d

    section Phase 2 - Production Deploy
    NGINX + VPS Setup        :c1, after b3, 10d
    Docker Compose Deploy    :c2, after c1, 7d

    section Phase 3 - AI Integration
    LangGraph Basics         :d1, after c2, 14d
    Medicine Extraction Agent:d2, after d1, 14d

    section Phase 4 - RAG System
    Embeddings + ChromaDB    :e1, after d2, 14d
    Medicine Knowledge Base  :e2, after e1, 14d

    section Phase 5 - Advanced AI
    Voice AI (STT + TTS)     :f1, after e2, 21d
    Multi-Agent Workflows    :f2, after f1, 21d
    Reminder Intelligence    :f3, after f2, 14d
```

### Phase Details

#### 🔵 Phase 0 — Foundation
- **Learn:** Docker, MySQL, FastAPI, GitHub Actions
- **Build:** Basic backend, CRUD APIs, Dockerized dev environment

#### 🟢 Phase 1 — Pharmacy Backend
- **Learn:** SQLAlchemy, Alembic migrations, JWT authentication, DB transactions
- **Build:** Billing module, Inventory module, Invoice generation

#### 🟡 Phase 2 — Production Deployment
- **Learn:** NGINX configuration, VPS deployment, Docker Compose, CI/CD pipelines
- **Deploy:** Full backend + frontend on live server

#### 🟣 Phase 3 — AI Integration
- **Learn:** LangGraph, Tool calling, Agent state management, Workflow graphs
- **Build:** Medicine extraction workflow

#### 🔴 Phase 4 — RAG System
- **Learn:** Embeddings, text chunking, vector retrieval, semantic search
- **Build:** Medicine knowledge assistant with ChromaDB

#### ⚫ Phase 5 — Advanced AI
- **Build:** Reminder Agent, Voice AI (Marathi/Hindi), Full multi-agent orchestration

---

## 12. Engineering Principles

> These are the non-negotiables for building a production-grade system.

| # | Principle | Description |
|---|---|---|
| 1 | 🧠 **Learn While Building** | Do not blindly generate or copy code. Understand every line. |
| 2 | 🚀 **Deploy Early** | Production exposure teaches real-world engineering skills. |
| 3 | 🏗️ **Keep Architecture Simple** | Avoid premature microservices. Start modular monolith. |
| 4 | 🔀 **Separate Business & AI Logic** | Not everything needs AI. Keep boundaries clear. |
| 5 | 🔭 **Build Production Thinking** | Focus on: reliability, scalability, maintainability, observability. |

---

## 13. Final Stack Summary

| Layer | Technology | Notes |
|---|---|---|
| 🌐 Frontend | Next.js (JavaScript) | No TypeScript |
| 📱 Mobile | React Native | Patient-facing app |
| ⚙️ Backend | FastAPI (Python 3.12+) | REST + async |
| 🗄️ Database | MySQL | Primary operational DB |
| ⚡ Cache | Redis | Sessions, rate limiting |
| 🔍 Vector DB | ChromaDB → Pinecone | RAG & AI memory |
| 🤖 AI Orchestration | LangGraph | Multi-agent workflows |
| 🧠 LLM | OpenAI GPT-4.1 / GPT-4o | Reasoning & extraction |
| 🐳 Containerization | Docker + Docker Compose | Dev & prod |
| ⚙️ CI/CD | GitHub Actions | Automated pipelines |
| 🔀 Reverse Proxy | NGINX | HTTPS + routing |
| 🖥️ Hosting | VPS → AWS / Azure | Scale when ready |
| 🎙️ Voice AI | Whisper + ElevenLabs | STT + TTS |
| 📲 Messaging | Twilio / WhatsApp API | Reminders + alerts |

---

## 🎯 Final Vision

> This platform is **not** just pharmacy software, a chatbot, or a reminder app.

It is an:

### 🏥 AI-Powered Pharmacy & Chronic Healthcare Operating System

Combining:

- ⚙️ **Operational Automation** — Billing, inventory, invoices
- 🤖 **AI Workflows** — LangGraph multi-agent orchestration
- 🗣️ **Regional Voice Intelligence** — Marathi / Hindi AI
- 🏥 **Healthcare Coordination** — Refill prediction, family alerts
- 🔗 **Multi-Agent Orchestration** — Stateful, event-driven AI

Into **one connected ecosystem** built for Bharat. 🇮🇳

---

*Document Version: 1.0 | Stack: JavaScript + Python + FastAPI + LangGraph*
