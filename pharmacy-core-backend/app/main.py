"""FastAPI application entrypoint for the AI Pharmacy Ecosystem.

Boots the FastAPI app and (in later steps) wires together all routers.
Run locally with:  uvicorn app.main:app --reload
"""
from fastapi import FastAPI

app = FastAPI(
    title="AI Pharmacy Ecosystem",
    description="Production-grade pharmacy API: billing, expiry tracking, voice ordering, AI assistant.",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


# YOUR JOB (step 1.7): app.include_router(...) for medicines, customers, sales, etc.
