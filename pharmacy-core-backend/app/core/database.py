"""Database engine + session factory + declarative Base.

Created once at process start. Three things live here:
- engine: process-wide connection pool to MySQL (one per app).
- SessionLocal: a factory — each call SessionLocal() opens a fresh session
  (used per HTTP request via Depends() in step 2.5).
- Base: every ORM model inherits this. Alembic reads Base.metadata to autogenerate migrations.

This file is the SINGLE place that knows the DATABASE_URL. The rest of the app
imports SessionLocal/Base from here and stays storage-agnostic.
"""
import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — replaced by pydantic-settings in a later step.

    We don't want to add python-dotenv as a dependency just for one file.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


# Load .env from the backend root (the directory that contains the `app` package).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_load_dotenv(_BACKEND_ROOT / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Create a .env file at pharmacy-core-backend/.env "
        "with DATABASE_URL=mysql+pymysql://root:PASSWORD@127.0.0.1:3306/pharmacy_dev"
    )

# Engine: process-wide. ONE per app instance.
#   echo=False         — don't log every SQL statement (flip True when debugging).
#   pool_pre_ping=True — silently checks each pooled connection is alive before handing it
#                        to a request. Survives MySQL's 8-hour idle disconnect without errors.
#   pool_recycle=3600  — proactively replace connections older than 1h, also for idle timeouts.
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Session factory. Each SessionLocal() is a fresh, short-lived session.
#   autoflush=False  — we control when SQL flushes to DB (cleaner mental model).
#   autocommit=False — required: we want explicit commit() / rollback().
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base every ORM model in app/models/ inherits from.

    Carries the metadata registry — Alembic reads Base.metadata to know which
    tables / columns / indexes exist when generating migrations.
    """


def get_db() -> Iterator[Session]:
    """FastAPI dependency that yields a session per HTTP request.

    Used by endpoint functions like:
        def my_endpoint(db: Session = Depends(get_db)):
            ...

    Why yield instead of return:
    - FastAPI runs code BEFORE yield on the way in (open session, borrow connection).
    - FastAPI runs code AFTER yield on the way out (close session, return connection).
    - The `finally` block runs even if the endpoint raised — connection never leaks.

    One session per request. NOT one per app (concurrent requests would step on each
    other's identity map). NOT one per repo method (would exhaust the connection pool).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
