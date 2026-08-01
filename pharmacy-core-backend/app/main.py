"""FastAPI application entrypoint for the AI Pharmacy Ecosystem.

Boots the FastAPI app and wires together every domain router.
Run locally with: uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import billing as billing_router
from app.routers import business as business_router
from app.routers import medicines as medicines_router
from app.routers import reorder as reorder_router
from app.routers import tool_agent as tool_agent_router

app = FastAPI(
    title="AI Pharmacy Ecosystem",
    description=(
        "Production-grade pharmacy API: billing, expiry tracking, "
        "voice ordering, AI assistant."
    ),
    version="0.1.0",
)

# ------------------------------------------------------------------------
# CORS
# ------------------------------------------------------------------------

_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------------
# Health Check
# ------------------------------------------------------------------------

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# ------------------------------------------------------------------------
# API Routers
# ------------------------------------------------------------------------

app.include_router(medicines_router.router)
app.include_router(billing_router.router)
app.include_router(reorder_router.router)
app.include_router(business_router.router)

# Native LangGraph Tool Calling Agent
app.include_router(tool_agent_router.router)