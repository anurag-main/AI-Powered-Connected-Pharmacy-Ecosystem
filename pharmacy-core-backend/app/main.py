"""FastAPI application entrypoint for the AI Pharmacy Ecosystem.

Boots the FastAPI app and wires together every domain router.
Run locally with:  uvicorn app.main:app --reload
"""
from fastapi import FastAPI

from app.routers import medicines as medicines_router

app = FastAPI(
    title="AI Pharmacy Ecosystem",
    description="Production-grade pharmacy API: billing, expiry tracking, voice ordering, AI assistant.",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Register every domain router here. As we add customers, sales, batches, etc.,
# each gets its own file under app/routers/ and is included on one line below.
app.include_router(medicines_router.router)
