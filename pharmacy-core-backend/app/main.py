"""FastAPI application entrypoint for the AI Pharmacy Ecosystem.

Boots the FastAPI app and wires together every domain router.
Run locally with: uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging_config import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.tracing import log_tracing_status
from app.routers import billing as billing_router
from app.routers import business as business_router
from app.routers import medicines as medicines_router
from app.routers import reorder as reorder_router
from app.routers import tool_agent as tool_agent_router

# Before the app object exists, so startup and import-time warnings are formatted too.
configure_logging()

# Says out loud, on every boot, whether traces are actually being sent — an API key
# without a tracing flag silently produces nothing, which is how this project ran for
# months believing it had tracing.
log_tracing_status()

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
    # Cross-origin responses hide non-simple headers from JavaScript unless they are
    # explicitly exposed. Without this the browser receives X-Request-ID but the
    # frontend cannot read it, so a user could never quote it in a bug report.
    expose_headers=["X-Request-ID"],
)

# ------------------------------------------------------------------------
# Correlation + access logging
# ------------------------------------------------------------------------

# Starlette runs middleware in reverse registration order, so adding this AFTER CORS
# puts it OUTSIDE it: the request id is bound before CORS runs and is still bound
# while the response headers are written, which is what lets X-Request-ID be set on
# every response, rejected preflights included.
app.add_middleware(RequestContextMiddleware)


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