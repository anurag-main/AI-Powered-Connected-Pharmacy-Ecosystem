# AI Pharma Operations Intelligence Platform

## Career-Targeted Project Roadmap --- 15+ LPA AI/GenAI Engineer

> **Purpose of this document:** This is the execution roadmap for Claude
> Code / Claude Agent working on the AI Pharmacy Ecosystem. The goal is
> not merely to add features. The goal is to transform the project into
> a credible, production-shaped **Agentic AI + RAG + Backend + Data +
> Evaluation + DevOps** portfolio project that can support interviews
> for **15+ LPA AI Engineer / GenAI Engineer / Agentic AI Engineer roles
> in India**.

------------------------------------------------------------------------

# 0. NORTH STAR

## Career objective

Target roles:

-   AI Engineer
-   Generative AI Engineer
-   GenAI Application Engineer
-   Agentic AI Engineer
-   AI Backend Engineer
-   LLM Engineer
-   Applied AI Engineer

Target compensation:

> **15+ LPA**

The project must therefore demonstrate more than:

-   an LLM API call
-   a chatbot
-   a basic RAG demo
-   a toy multi-agent workflow

It must demonstrate:

1.  Strong Python engineering
2.  FastAPI backend design
3.  SQL/data modeling
4.  LLM integration
5.  RAG
6.  Agent orchestration
7.  Tool calling
8.  Multi-agent architecture
9.  Human-in-the-loop
10. Persistent memory
11. Evaluation
12. Observability
13. Security/RBAC
14. Caching
15. Async/background processing
16. Docker
17. CI/CD
18. Cloud deployment
19. Cost/latency awareness
20. Failure handling
21. Auditability
22. A real business problem

Current 2026 job postings strongly emphasize production RAG,
LangGraph/multi-agent orchestration, FastAPI/Python, evaluation,
observability, Docker/cloud deployment, security, human approval, and
production reliability. This roadmap therefore prioritizes those
capabilities instead of adding AI features for the sake of feature
count.

------------------------------------------------------------------------

# 1. PRODUCT POSITIONING

## Do NOT position the final project as

> "AI Pharmacy Billing System"

Billing is useful application functionality but is not the main AI value
proposition.

The current billing workflow is mostly deterministic:

-   medicine lookup
-   stock validation
-   FEFO
-   price lookup
-   transaction
-   receipt

Keep billing as a normal deterministic module.

Do not spend significant AI-development time on billing.

## Final positioning

Use:

> **AI Pharma Operations Intelligence Platform**

Alternative:

> **Agentic AI Platform for Pharmaceutical Operations**

One-line description:

> A production-oriented multi-agent AI platform that helps
> pharmaceutical operations teams forecast demand, identify inventory
> and expiry risk, optimize procurement, evaluate supplier risk, analyze
> business data, and retrieve trusted pharmaceutical knowledge using RAG
> with human approval and full observability.

------------------------------------------------------------------------

# 2. THE REAL BUSINESS PROBLEM

The system should evolve from a pharmacy POS into an **AI
decision-support platform**.

The core business loop:

``` text
Operational Data
      |
      v
Inventory + Sales + Purchases + Suppliers + Batches
      |
      v
Forecast / Risk / Analytics
      |
      v
AI Agents
      |
      v
Recommendations
      |
      v
Human Approval
      |
      v
Auditable Business Action
```

The AI must primarily:

> **observe -\> reason -\> recommend -\> explain -\> request approval**

It should NOT blindly:

> observe -\> reason -\> execute high-impact action

------------------------------------------------------------------------

# 3. FINAL AGENT PORTFOLIO

## Priority 1 --- Inventory Risk Agent

Responsibilities:

-   detect stock-out risk
-   detect overstock
-   calculate days of cover
-   calculate safety stock
-   identify slow-moving products
-   identify abnormal demand
-   identify inventory concentration
-   recommend inventory actions

Example:

``` text
Product: Product X

Current usable stock: 5,200
Forecast 30-day demand: 12,400
Supplier lead time: 14 days
Safety stock: 2,000

Risk:
HIGH

Recommendation:
Purchase approximately 9,000 units.

Reason:
Projected inventory falls below safety stock before expected replenishment.
```

Important:

All arithmetic must be deterministic.

LLM should explain and reason over results, not calculate financial
quantities itself.

------------------------------------------------------------------------

# 4. PRIORITY 2 --- DEMAND FORECAST AGENT

This is one of the most important additions.

## Inputs

-   historical sales
-   product
-   date
-   seasonality
-   recent velocity
-   stock-outs
-   supplier lead time
-   current inventory
-   optional promotions/events

## Outputs

``` text
forecast_horizon
predicted_demand
confidence_interval
stockout_probability
recommended_safety_stock
recommended_order_quantity
explanation
```

## Architecture

``` text
Sales History
     |
     v
Data Preparation
     |
     v
Forecast Model
     |
     v
Demand Prediction
     |
     +----> Confidence
     |
     +----> Stock-out Risk
     |
     +----> Safety Stock
     |
     v
Inventory Agent
```

Do not make the LLM the forecasting model.

Use Python/statistical/ML logic for numerical forecasting.

Use the LLM for:

-   explanation
-   scenario interpretation
-   recommendation narrative
-   user interaction

------------------------------------------------------------------------

# 5. PRIORITY 3 --- EXPIRY RISK AGENT

This is a highly suitable use case because the existing database already
has batch expiry, quantity, cost price, and sales information.

## Responsibilities

-   identify batches approaching expiry
-   calculate inventory value at risk
-   estimate quantity likely to remain unsold
-   rank batches by financial risk
-   identify products with repeated expiry
-   suggest actions

## Example

``` text
Batch: B-1024
Expiry: 42 days
Quantity: 20,000
Cost/unit: ₹82

Inventory value: ₹16.4 lakh

Expected sales before expiry: 7,500
Projected leftover: 12,500

Potential value at risk: ₹10.25 lakh
```

Possible recommendations:

1.  Increase allocation
2.  Transfer inventory
3.  Prioritize sales
4.  Return to supplier
5.  Discount where commercially/legal appropriate
6.  Continue monitoring

High-impact action requires human approval.

------------------------------------------------------------------------

# 6. PRIORITY 4 --- PROCUREMENT AGENT

## Responsibilities

Given a demand/risk situation:

-   determine what needs to be purchased
-   determine how much
-   determine when
-   compare suppliers
-   consider price
-   consider lead time
-   consider supplier reliability
-   consider quality history
-   recommend supplier allocation

Example:

``` text
Required quantity: 10,000

Supplier A:
price = ₹72
lead time = 7 days
on-time rate = 94%

Supplier B:
price = ₹68
lead time = 18 days
on-time rate = 76%

Supplier C:
price = ₹74
lead time = 6 days
on-time rate = 98%
```

The agent should explain total decision tradeoffs instead of selecting
the cheapest supplier blindly.

------------------------------------------------------------------------

# 7. PRIORITY 5 --- SUPPLIER RISK AGENT

Create a supplier scorecard.

Possible dimensions:

-   on-time delivery
-   average lead time
-   lead-time variance
-   price variance
-   purchase volume
-   return rate
-   quality incidents
-   cancellation rate
-   historical stock-out contribution

Example:

``` text
Supplier Risk Score

Delivery reliability       62%
Lead-time volatility       HIGH
Quality incident rate      HIGH
Price volatility           MEDIUM

Overall risk: HIGH

Recommendation:
Reduce dependency and identify secondary supplier.
```

The scoring logic must be deterministic and explainable.

------------------------------------------------------------------------

# 8. PRIORITY 6 --- QUALITY / DEVIATION AGENT

This is the bridge from pharmacy operations toward genuine
pharmaceutical-industry workflows.

## Future data

-   deviation reports
-   SOPs
-   batch records
-   CAPA records
-   raw-material information
-   equipment logs
-   historical investigations
-   product specifications

## Workflow

``` text
Quality Event
     |
     v
Retrieve Similar Deviations
     |
     v
Retrieve Relevant SOPs
     |
     v
Retrieve Batch Information
     |
     v
Retrieve Supplier/Material History
     |
     v
Reason Over Evidence
     |
     v
Potential Root Causes
     |
     v
CAPA Suggestions
     |
     v
Human QA Review
```

The agent must never autonomously close a deviation or approve a CAPA.

------------------------------------------------------------------------

# 9. PRIORITY 7 --- PHARMA KNOWLEDGE RAG AGENT

Build a serious RAG system.

Knowledge sources may include:

-   SOPs
-   product documentation
-   internal quality procedures
-   regulatory guidance
-   training documents
-   deviation history
-   CAPA history
-   supplier documents
-   product specifications

The agent must return:

-   answer
-   sources
-   document IDs
-   relevant sections
-   confidence/grounding information
-   refusal when evidence is insufficient

Example:

``` text
Question:
"What is the approved procedure for a temperature excursion?"

Answer:
...

Sources:
SOP-204
Temperature-Excursion-Procedure.pdf
Section 4.2
```

No unsupported claims.

------------------------------------------------------------------------

# 10. PRIORITY 8 --- BUSINESS INTELLIGENCE AGENT

Keep the existing BI Agent.

However, fix it before adding more features.

Current known issues from the project QA report include:

-   cross-conversation memory failure
-   missing date/period filtering
-   unsafe memory persistence
-   no memory deduplication
-   missing ranking/breakdown capabilities
-   reflection limitations

These are more important than adding another agent.

## Required BI capabilities

The BI Agent should answer:

``` text
What were sales last month?
Which products grew the most?
Which products have the highest margin?
Which suppliers caused the most delays?
What is the expiry value at risk?
Which products are slow moving?
What is the purchase-to-sales ratio?
```

Repository support must include:

-   date filters
-   grouping
-   ranking
-   top-N
-   comparisons
-   trend queries

------------------------------------------------------------------------

# 11. SUPERVISOR AGENT

Only implement the Supervisor AFTER the specialist agents have
meaningful capabilities.

## Architecture

``` text
                         USER
                           |
                           v
                     SUPERVISOR
                           |
       +---------+---------+---------+---------+---------+
       |         |                   |                   |
       v         v                   v                   v
 Inventory   Forecast           Procurement           Quality
   Agent       Agent               Agent               Agent
       |         |                   |                   |
       +---------+-------------------+-------------------+
                           |
                           v
                    Analytics / RAG
                           |
                           v
                  Recommendation
                           |
                           v
                    Human Approval
```

## Supervisor responsibilities

The supervisor should:

1.  classify intent
2.  choose specialist agent
3.  pass structured state
4.  prevent unauthorized tool access
5.  maintain handoff count
6.  stop loops
7.  collect specialist results
8.  ask another specialist when necessary
9.  synthesize final response
10. route high-impact actions to approval

Do not create a free-for-all agent swarm.

Use explicit routing.

------------------------------------------------------------------------

# 12. HUMAN-IN-THE-LOOP

Human approval is a core production capability.

Require approval for:

-   purchase orders
-   supplier changes
-   inventory transfers
-   pricing changes
-   CAPA recommendations
-   external communication
-   destructive operations
-   regulatory/quality decisions

Pattern:

``` text
Agent
  |
  v
Recommendation
  |
  v
Evidence
  |
  v
Risk/Confidence
  |
  v
Human Approval
  |
  +---- Reject
  |
  +---- Modify
  |
  +---- Approve
```

Use LangGraph interrupt/pause/resume patterns where appropriate.

Every approval should be auditable.

------------------------------------------------------------------------

# 13. RAG ARCHITECTURE

Do not stop at:

``` text
PDF -> embedding -> Chroma -> LLM
```

Build production-shaped RAG:

``` text
Documents
   |
   v
Ingestion
   |
   v
Parsing
   |
   v
Chunking
   |
   v
Metadata extraction
   |
   v
Embeddings
   |
   v
Vector store
   |
   +---- keyword/BM25 search
   |
   +---- semantic search
   |
   v
Hybrid retrieval
   |
   v
Reranking
   |
   v
Context assembly
   |
   v
LLM
   |
   v
Grounded answer + citations
```

Metadata should include where possible:

``` text
document_id
document_type
product_id
department
version
effective_date
expiry_date
section
access_scope
```

Implement metadata filtering and access control.

------------------------------------------------------------------------

# 14. EVALUATION --- NON-NEGOTIABLE

A 15+ LPA portfolio project must answer:

> "How do you know your AI works?"

Create an evaluation suite.

## RAG evaluation

Measure:

-   retrieval recall
-   context relevance
-   answer faithfulness
-   citation correctness
-   answer relevance

## Agent evaluation

Measure:

-   correct routing
-   tool selection
-   argument correctness
-   final answer correctness
-   refusal correctness
-   approval routing
-   loop termination

## Business agent evaluation

Create fixed scenarios:

``` text
Scenario 001:
Stock-out risk

Expected:
Inventory Agent

Scenario 002:
Supplier comparison

Expected:
Procurement + Supplier Risk

Scenario 003:
SOP question

Expected:
RAG Agent

Scenario 004:
Expiry exposure

Expected:
Expiry Agent
```

Use a combination of:

-   deterministic assertions
-   LLM-as-judge
-   human-reviewed golden datasets

------------------------------------------------------------------------

# 15. OBSERVABILITY

LangSmith must actually work.

Do not merely put environment variables in `.env`.

Track:

-   trace ID
-   user ID
-   tenant/business ID
-   agent
-   node
-   tool
-   model
-   latency
-   input tokens
-   output tokens
-   estimated cost
-   errors
-   retries
-   retrieved documents
-   final result
-   approval events

You should be able to answer:

> "Why did the agent produce this answer?"

from a trace.

------------------------------------------------------------------------

# 16. SECURITY

Implement:

## Authentication

-   JWT access token
-   refresh token
-   password hashing

## RBAC

Roles:

``` text
ADMIN
PHARMACIST
PROCUREMENT
QUALITY
ANALYST
VIEWER
```

Tool permissions must depend on role.

Example:

``` text
Viewer:
READ only

Analyst:
READ + analytics

Procurement:
READ + procurement recommendations

Admin:
approval/write capabilities
```

## AI-specific security

Implement:

-   prompt injection awareness
-   tool allowlists
-   structured tool arguments
-   server-side authorization
-   tenant/business isolation
-   secret management
-   audit logs
-   PII protection

Never allow the LLM to decide authorization.

------------------------------------------------------------------------

# 17. DATA ARCHITECTURE

Current MySQL architecture is good.

Extend it carefully.

Potential additional tables:

``` text
users
roles
permissions
audit_logs
forecast_results
supplier_scores
supplier_events
quality_events
deviations
capa_records
documents
document_chunks
agent_runs
approvals
```

Do not add tables without a real requirement.

------------------------------------------------------------------------

# 18. REDIS

Use Redis for actual reasons.

Implement:

-   medicine/product cache
-   frequently requested analytics cache
-   rate limiting
-   session/short-lived state where appropriate
-   distributed locks where required
-   background job coordination if needed

Demonstrate cache invalidation.

Example:

``` text
GET product
    |
Redis hit -> return
    |
Redis miss
    |
MySQL
    |
set Redis
```

On write:

``` text
UPDATE product
      |
invalidate cache
```

------------------------------------------------------------------------

# 19. BACKGROUND JOBS

Add asynchronous/background processing where useful.

Good candidates:

-   document ingestion
-   embedding generation
-   evaluation runs
-   forecast generation
-   supplier scoring
-   expiry scans
-   scheduled reports

Do not create background jobs merely to say "async".

------------------------------------------------------------------------

# 20. PROACTIVE AGENTS

After request-driven agents work, introduce one scheduled workflow.

Example:

``` text
Every morning
     |
     v
Expiry Risk Agent
     |
     v
Inventory Risk Agent
     |
     v
Forecast Agent
     |
     v
Daily Risk Report
```

Possible notification:

``` text
Today's Risk Summary

3 products likely to stock out
7 batches approaching expiry
₹4.2L inventory at risk
2 supplier risks increased
```

This demonstrates event/cron-triggered agents rather than only
chatbot-triggered agents.

------------------------------------------------------------------------

# 21. MCP

Build an MCP server around safe pharmacy/pharma tools.

Expose read-only tools first:

``` text
get_inventory
get_product
get_sales
get_supplier
get_forecast
get_expiry_risk
get_supplier_risk
search_knowledge
```

Then demonstrate:

``` text
MCP Client
    |
    v
Pharma MCP Server
    |
    v
Controlled Tools
    |
    v
Backend Services
```

Write operations should require explicit approval.

------------------------------------------------------------------------

# 22. API DESIGN

FastAPI must look production-ready.

Requirements:

-   versioned APIs
-   Pydantic request/response models
-   structured error responses
-   authentication middleware
-   authorization
-   request IDs
-   pagination
-   filtering
-   validation
-   async endpoints where appropriate
-   OpenAPI documentation
-   health endpoint
-   readiness endpoint

Example:

``` text
/api/v1/inventory
/api/v1/forecast
/api/v1/expiry-risk
/api/v1/procurement
/api/v1/suppliers
/api/v1/quality
/api/v1/knowledge
/api/v1/analytics
/api/v1/agents
/api/v1/approvals
```

------------------------------------------------------------------------

# 23. DOCKER

Containerize:

``` text
frontend
backend
mysql
redis
vector database
worker
```

Use Docker Compose for local development.

Add:

-   healthchecks
-   persistent volumes
-   environment variables
-   separate dev/prod configuration

------------------------------------------------------------------------

# 24. CI/CD

GitHub Actions:

``` text
push
 |
 v
Lint
 |
 v
Unit tests
 |
 v
Integration tests
 |
 v
AI evaluation suite
 |
 v
Build Docker image
 |
 v
Security checks
 |
 v
Deploy
```

Important:

AI evaluation should be treated as part of CI, not an afterthought.

------------------------------------------------------------------------

# 25. CLOUD DEPLOYMENT

Deploy at least one complete environment.

Preferred:

-   AWS / Azure / GCP

Minimum production-shaped architecture:

``` text
Internet
   |
HTTPS
   |
Reverse Proxy / Load Balancer
   |
FastAPI
   |
+-------+-------+-------+
|       |       |       |
MySQL Redis Vector DB
|
Worker
```

If budget is limited, VPS deployment is acceptable for the portfolio
project, but the architecture should remain cloud-portable.

------------------------------------------------------------------------

# 26. PERFORMANCE & COST ENGINEERING

This is important for interviews.

Track:

-   model latency
-   API latency
-   token usage
-   estimated cost
-   cache hit rate
-   retrieval latency
-   database query latency

Implement:

### Model routing

Use a cheaper model for:

-   classification
-   simple extraction
-   summarization

Use stronger models for:

-   complex reasoning
-   quality investigation
-   difficult RAG synthesis

### Caching

Cache:

-   deterministic analytics
-   embeddings
-   repeated retrieval results where safe
-   product lookups

### Prompt discipline

Do not send entire database results to the LLM.

------------------------------------------------------------------------

# 27. TESTING

## Backend

-   unit tests
-   repository tests
-   service tests
-   API tests
-   integration tests

## Agents

-   node tests
-   tool tests
-   routing tests
-   state transition tests
-   failure tests

## RAG

-   retrieval tests
-   citation tests
-   hallucination tests
-   adversarial questions

## End-to-end

Example:

``` text
User question
 -> API
 -> Supervisor
 -> Agent
 -> Tool
 -> DB
 -> Agent
 -> Approval
 -> API
 -> UI
```

Test the whole path.

------------------------------------------------------------------------

# 28. FRONTEND

The frontend should demonstrate the AI system rather than just CRUD.

Core screens:

### Dashboard

Show:

-   inventory risk
-   expiry risk
-   forecast
-   supplier risk
-   procurement recommendations

### AI Operations Chat

Show:

-   user query
-   supervisor routing
-   specialist agents
-   tool calls
-   evidence
-   final recommendation

### Approval Center

Show:

``` text
Pending Approval

Purchase Recommendation
₹7.4 lakh

Reason:
...

Evidence:
...

[Approve]
[Modify]
[Reject]
```

### Knowledge Center

RAG interface with citations.

### Agent Trace View

Show:

``` text
Supervisor
  |
  +-- Forecast Agent
  |      |
  |      +-- forecast_tool
  |
  +-- Procurement Agent
         |
         +-- supplier_tool
```

This is a strong interview demonstration.

------------------------------------------------------------------------

# 29. KEEP BILLING SIMPLE

Billing remains:

``` text
Billing API
   |
Medicine lookup
   |
FEFO
   |
Price
   |
Transaction
```

No autonomous Billing Agent.

It can remain in the application because it demonstrates:

-   transactions
-   database integrity
-   FEFO
-   deterministic business logic

But it should not be presented as the main AI innovation.

------------------------------------------------------------------------

# 30. PROJECT PHASES

## Phase 0 --- Architecture cleanup

Status: START HERE

Tasks:

-   preserve working functionality
-   remove unnecessary billing-agent focus
-   define new domain boundaries
-   establish agent interfaces
-   define shared state
-   define tool registry
-   define approval model
-   document architecture

Deliverable:

> Clean baseline before adding new agents.

------------------------------------------------------------------------

## Phase 1 --- Fix BI Agent

Tasks:

-   fix user/business identity
-   fix date filtering
-   add grouping
-   add ranking
-   add top-N
-   fix memory confidence gate
-   deduplicate memory
-   test cross-session memory
-   improve refusal behavior
-   add evaluation cases

Exit condition:

> BI Agent passes the defined regression suite.

------------------------------------------------------------------------

## Phase 2 --- Expiry Risk Agent

Tasks:

-   expiry repository queries
-   risk calculation
-   financial exposure calculation
-   ranking
-   recommendations
-   approval workflow
-   tests

Exit condition:

> User can identify the highest-value expiry risks and understand why.

------------------------------------------------------------------------

## Phase 3 --- Forecast Agent

Tasks:

-   prepare time-series dataset
-   establish baseline model
-   forecast
-   confidence interval
-   evaluation metrics
-   stock-out prediction
-   API
-   tests

Exit condition:

> Forecast has measurable accuracy and is not LLM-generated arithmetic.

------------------------------------------------------------------------

## Phase 4 --- Inventory Risk Agent

Combine:

``` text
Forecast
+
Inventory
+
Lead time
+
Safety stock
```

Output:

``` text
Stock-out risk
Overstock risk
Recommended action
```

------------------------------------------------------------------------

## Phase 5 --- Supplier Risk Agent

Tasks:

-   supplier metrics
-   scoring
-   historical performance
-   reliability
-   quality/return signals
-   ranking
-   explanation

------------------------------------------------------------------------

## Phase 6 --- Procurement Agent

Combine:

``` text
Inventory Risk
+
Forecast
+
Supplier Risk
```

Generate:

``` text
What
How much
When
From whom
Why
```

with approval.

------------------------------------------------------------------------

## Phase 7 --- Supervisor

Only now implement multi-agent routing.

Requirements:

-   structured RoutingDecision
-   conditional routing
-   handoff count
-   loop prevention
-   shared state
-   specialist result aggregation
-   human approval routing

------------------------------------------------------------------------

## Phase 8 --- Pharma RAG

Build full RAG pipeline:

``` text
ingestion
chunking
metadata
embeddings
hybrid retrieval
reranking
grounding
citations
evaluation
```

------------------------------------------------------------------------

## Phase 9 --- Quality Agent

Use RAG + structured quality data.

Implement:

-   deviation search
-   similar-case retrieval
-   SOP retrieval
-   root-cause candidates
-   CAPA suggestions
-   human QA approval

------------------------------------------------------------------------

## Phase 10 --- Security + Production Backend

Implement:

-   JWT
-   RBAC
-   audit logs
-   tenant/business isolation
-   tool permissions
-   rate limiting
-   Redis
-   secure secrets

------------------------------------------------------------------------

## Phase 11 --- Evaluation + Observability

Implement:

-   LangSmith
-   tracing
-   evaluation datasets
-   regression tests
-   LLM-as-judge
-   retrieval metrics
-   agent metrics
-   latency/cost tracking

------------------------------------------------------------------------

## Phase 12 --- Docker + CI/CD

Implement:

-   Docker
-   Compose
-   GitHub Actions
-   tests
-   eval gate
-   image build
-   deployment

------------------------------------------------------------------------

## Phase 13 --- Cloud Deployment

Deploy the complete system.

Requirements:

-   HTTPS
-   monitoring
-   logs
-   health checks
-   backups
-   environment configuration
-   rollback strategy

------------------------------------------------------------------------

## Phase 14 --- MCP

Implement controlled MCP access to business tools.

------------------------------------------------------------------------

## Phase 15 --- Proactive AI

Add scheduled:

> Daily Pharma Operations Risk Brief

This should demonstrate event-driven/proactive agents.

------------------------------------------------------------------------

# 31. WHAT NOT TO BUILD

Do NOT waste project time on:

-   generic chatbot UI
-   AI-generated billing
-   unnecessary 10-agent swarm
-   autonomous purchasing without approval
-   fake AI calculations
-   random prompt engineering demos
-   unnecessary fine-tuning
-   image generation
-   generic sentiment analysis
-   meaningless voice features
-   20 agents with overlapping responsibilities
-   features without evaluation
-   features without a business reason

Quality \> quantity.

------------------------------------------------------------------------

# 32. ENGINEERING RULES FOR CLAUDE

Claude MUST follow these rules.

## Rule 1 --- Do not break working functionality

Before changing architecture:

-   inspect existing implementation
-   understand dependencies
-   run relevant tests
-   make incremental changes

Never rewrite working modules without a clear reason.

## Rule 2 --- Deterministic first

If a value can be calculated by code:

> use code.

Examples:

-   price
-   stock
-   margin
-   forecast calculations
-   risk score
-   dates
-   quantities
-   permissions

Do not ask an LLM to calculate business-critical numbers.

## Rule 3 --- LLM only for fuzzy tasks

Good LLM tasks:

-   interpretation
-   classification
-   explanation
-   summarization
-   reasoning over retrieved evidence
-   planning
-   ambiguous language

## Rule 4 --- Structured outputs

All agent decisions must use typed schemas.

Never rely on:

``` text
if "approve" in response:
```

Use Pydantic/structured output.

## Rule 5 --- Human approval for consequential actions

Never allow an LLM to directly perform high-impact business actions.

## Rule 6 --- Every agent needs evaluation

No new agent is considered complete until it has:

-   unit tests
-   integration tests
-   representative scenarios
-   failure scenarios
-   evaluation dataset

## Rule 7 --- Every agent needs observability

Trace:

-   input
-   routing
-   tools
-   retrieval
-   model
-   latency
-   cost
-   output
-   errors

## Rule 8 --- Every agent must have a bounded loop

Examples:

``` text
MAX_REFLECTIONS = 2
MAX_HANDOFFS = 5
MAX_TOOL_CALLS = N
```

No uncontrolled agent loops.

## Rule 9 --- Fail honestly

If evidence is insufficient:

> say that evidence is insufficient.

Do not hallucinate.

## Rule 10 --- Preserve layer boundaries

``` text
Router
  ->
Service
  ->
Agent/Domain logic
  ->
Repository
  ->
Database
```

Repositories own database access.

## Rule 11 --- No fake production readiness

Do not mark something production-ready because:

-   it runs locally
-   an LLM answered once
-   a demo works

Production readiness requires:

-   tests
-   evaluation
-   security
-   observability
-   error handling
-   deployment
-   documentation

------------------------------------------------------------------------

# 33. DEFINITION OF DONE

A feature is DONE only if:

``` text
[ ] Business problem clearly defined
[ ] Architecture documented
[ ] Database changes migrated
[ ] API implemented
[ ] Service layer implemented
[ ] Agent implemented if needed
[ ] Tools implemented
[ ] Structured outputs implemented
[ ] Human approval implemented if required
[ ] Unit tests
[ ] Integration tests
[ ] Evaluation cases
[ ] Failure cases
[ ] Observability
[ ] Security considered
[ ] Documentation
[ ] Frontend demonstration
```

------------------------------------------------------------------------

# 34. INTERVIEW READINESS CHECKLIST

Before claiming the project is complete, I must be able to explain:

## Python

-   async vs sync
-   typing
-   Pydantic
-   exceptions
-   dependency injection
-   concurrency

## FastAPI

-   routing
-   middleware
-   dependency injection
-   authentication
-   async endpoints
-   error handling
-   API versioning

## SQL

-   joins
-   indexes
-   transactions
-   isolation
-   query optimization
-   aggregation
-   time-series queries

## LangGraph

-   state
-   nodes
-   edges
-   conditional routing
-   reducers
-   checkpointing
-   interrupts
-   persistence
-   supervisor architecture

## RAG

-   chunking
-   embeddings
-   vector search
-   metadata filtering
-   hybrid retrieval
-   reranking
-   grounding
-   citations
-   evaluation

## LLM

-   structured outputs
-   function/tool calling
-   context windows
-   token cost
-   model selection
-   prompt injection
-   hallucination control

## Production AI

-   tracing
-   evaluation
-   latency
-   cost
-   retries
-   rate limits
-   caching
-   guardrails
-   human approval

## DevOps

-   Docker
-   CI/CD
-   deployment
-   environment variables
-   secrets
-   monitoring
-   rollback

------------------------------------------------------------------------

# 35. REQUIRED PORTFOLIO DEMO

The final demo should tell one story.

## Scenario

User asks:

> "What products are at risk over the next 30 days and what should we
> purchase?"

### Step 1

Supervisor receives request.

### Step 2

Supervisor routes to:

``` text
Forecast Agent
Inventory Agent
```

### Step 3

Forecast calculates demand.

### Step 4

Inventory calculates stock-out risk.

### Step 5

Supervisor routes high-risk products to:

``` text
Procurement Agent
Supplier Risk Agent
```

### Step 6

Procurement recommends:

``` text
Product
Quantity
Date
Supplier
Reason
```

### Step 7

Supplier Risk explains supplier selection.

### Step 8

Supervisor produces final recommendation.

### Step 9

Human approval appears.

### Step 10

Approval is persisted and audited.

### Step 11

LangSmith trace shows the entire execution.

This one workflow demonstrates:

-   FastAPI
-   SQL
-   Python
-   forecasting
-   agents
-   LangGraph
-   tools
-   multi-agent orchestration
-   RAG if evidence is required
-   human-in-the-loop
-   persistence
-   evaluation
-   observability
-   frontend
-   security
-   production architecture

That is much more valuable in an interview than demonstrating ten
disconnected agents.

------------------------------------------------------------------------

# 36. FINAL TARGET ARCHITECTURE

``` text
                         ┌─────────────────────┐
                         │      Next.js        │
                         │ Dashboard / AI Chat │
                         │ Risk / Approvals    │
                         └──────────┬──────────┘
                                    |
                                    v
                         ┌─────────────────────┐
                         │    FastAPI Gateway  │
                         │ Auth / RBAC / APIs  │
                         └──────────┬──────────┘
                                    |
                  ┌─────────────────┴─────────────────┐
                  |                                   |
                  v                                   v
          Pharma Core APIs                       AI Gateway
                  |                                   |
                  |                                   v
                  |                            ┌─────────────┐
                  |                            │ SUPERVISOR  │
                  |                            └──────┬──────┘
                  |                                   |
                  |        ┌──────────┬─────────┬─────┼─────┬──────────┐
                  |        v          v         v     v     v          v
                  |   Inventory   Forecast  Procurement Supplier  Quality
                  |     Agent       Agent      Agent      Risk      Agent
                  |                                           Agent
                  |        └──────────┬─────────┬──────────────┘
                  |                   |
                  |                   v
                  |            Analytics Agent
                  |                   |
                  |                   v
                  |              RAG Agent
                  |                   |
                  └───────────────────┼───────────────────────┐
                                      |
                        ┌─────────────┴──────────────┐
                        |                            |
                        v                            v
                     MySQL                        Redis
                        |                            |
                        └────────────┬───────────────┘
                                     |
                                     v
                              Vector Database
                                     |
                                     v
                              Pharma Knowledge
```

Cross-cutting:

``` text
Authentication
RBAC
Audit Logs
Human Approval
Evaluation
LangSmith Tracing
Cost Tracking
Rate Limiting
Caching
CI/CD
Docker
Cloud Deployment
```

------------------------------------------------------------------------

# 37. CAREER STRATEGY

This project should not try to prove:

> "I know every AI technology."

It should prove:

> **"I can take a real business problem, design an AI system, build it
> with Python/FastAPI/LangGraph/RAG, integrate data and tools, evaluate
> it, secure it, observe it, and deploy it."**

That is the target signal for a 15+ LPA AI/GenAI engineering profile.

Current 2026 AI-engineering postings repeatedly emphasize exactly this
combination: Python/FastAPI, production RAG, LangGraph/agent
orchestration, tool integration, evaluation, observability, security,
Docker/cloud, and reliable deployment. Do not optimize this project
around model novelty alone.

------------------------------------------------------------------------

# 38. PRIORITY ORDER --- DO NOT DEVIATE WITHOUT A REASON

``` text
1. Fix BI Agent
        ↓
2. Expiry Risk Agent
        ↓
3. Forecast Agent
        ↓
4. Inventory Risk Agent
        ↓
5. Supplier Risk Agent
        ↓
6. Procurement Agent
        ↓
7. Supervisor
        ↓
8. Production RAG
        ↓
9. Quality Agent
        ↓
10. Evaluation
        ↓
11. Observability
        ↓
12. Security / RBAC
        ↓
13. Redis / caching
        ↓
14. Docker
        ↓
15. CI/CD
        ↓
16. Cloud deployment
        ↓
17. MCP
        ↓
18. Proactive scheduled agents
```

If time becomes limited, prioritize **1--12** over adding more business
agents.

------------------------------------------------------------------------

# 39. SOURCE-BASED INDUSTRY SIGNALS

This roadmap is informed by current 2026 job requirements and
pharmaceutical AI use cases.

Examples of current AI-engineering roles emphasize:

-   Python/FastAPI
-   LangGraph
-   multi-agent orchestration
-   RAG
-   vector search
-   evaluation
-   LangSmith/observability
-   Docker/cloud
-   security
-   human-in-the-loop
-   production reliability

Examples: - Acyuta Technologies Senior AI Engineer role - Nexaminds
LangChain/LangGraph deployment role - EPAM Senior AI Engineer ---
Agentic and RAG Systems - Cognizant AI Engineer ---
Python/LangChain/LangGraph

The pharmaceutical direction is also credible: current research
discusses AI/ML for pharmaceutical manufacturing, including process
monitoring, anomaly detection, advanced controls, and computer vision,
with GMP/GxP considerations.

Do not claim this project is a validated GxP production system. It is a
production-shaped portfolio system demonstrating engineering patterns
applicable to regulated environments.

------------------------------------------------------------------------

# 40. CLAUDE EXECUTION INSTRUCTION

When Claude is asked to continue development:

1.  Read this file first.
2.  Read `PROJECT_OVERVIEW.md`.
3.  Inspect the existing implementation before changing it.
4.  Identify the current phase.
5.  Work only on the highest-priority incomplete milestone unless the
    user explicitly overrides it.
6.  Do not create unnecessary agents.
7.  Do not reintroduce an AI billing agent as a priority.
8.  Preserve deterministic business logic.
9.  Add tests with every meaningful feature.
10. Add evaluation cases for every AI feature.
11. Add tracing for every agent.
12. Do not claim completion without verifying the feature.
13. Do not silently change architecture.
14. Document important architectural decisions.
15. Prefer production-quality implementation over demo shortcuts.
16. If a requested feature conflicts with this roadmap, explain the
    tradeoff before implementing it.
17. Optimize for the final career objective: **15+ LPA AI/GenAI
    engineering readiness**.

------------------------------------------------------------------------

# 41. FINAL SUCCESS CRITERIA

The project is considered career-ready when I can confidently
demonstrate:

``` text
REAL BUSINESS PROBLEM
        +
REAL DATA
        +
PYTHON/FastAPI
        +
SQL
        +
LLM
        +
RAG
        +
TOOLS
        +
LANGGRAPH
        +
MULTI-AGENT SUPERVISOR
        +
HUMAN APPROVAL
        +
MEMORY
        +
EVALUATION
        +
OBSERVABILITY
        +
SECURITY
        +
REDIS
        +
DOCKER
        +
CI/CD
        +
CLOUD DEPLOYMENT
        +
MCP
        +
MEASURABLE RESULTS
```

The final project should feel like a **small production AI platform**,
not a collection of AI demos.
