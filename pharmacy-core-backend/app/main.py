"""FastAPI application entrypoint for the AI Pharmacy Ecosystem.

Boots the FastAPI app and wires together every domain router.
Run locally with:  uvicorn app.main:app --reload
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import billing as billing_router
from app.routers import medicines as medicines_router

app = FastAPI(
    title="AI Pharmacy Ecosystem",
    description="Production-grade pharmacy API: billing, expiry tracking, voice ordering, AI assistant.",
    version="0.1.0",
)

# CORS — the browser "guest list". The Next.js frontend runs on a DIFFERENT
# origin (http://localhost:3000) than this API (http://localhost:8000). Browsers
# block cross-origin requests unless the server explicitly allows them here.
# Dev-only: we whitelist the local frontend origins. In production this list is
# tightened to the real deployed frontend domain (never "*" with credentials).
_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",  # Next falls back here if 3000 is taken
    "http://127.0.0.1:3001",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],   # GET, POST, etc.
    allow_headers=["*"],   # Content-Type, Authorization, ...
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Register every domain router here. As we add customers, sales, batches, etc.,
# each gets its own file under app/routers/ and is included on one line below.
app.include_router(medicines_router.router)
app.include_router(billing_router.router)
