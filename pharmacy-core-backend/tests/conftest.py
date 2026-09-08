"""Shared fixtures.

TEST DATABASE STRATEGY
----------------------
The suite runs against a temporary **file-based SQLite** database, created once per
session in the OS temp directory and deleted at the end.

Why a file and not ``sqlite://`` (in-memory): an in-memory SQLite database belongs to
a single connection, so the app's engine and the test's engine would each get their
own empty copy — and the BI fetcher runs its tools in a ``ThreadPoolExecutor``, i.e.
on other connections again. A file is shared by every connection and every thread
without any pool trickery, and on SQLite it is still fast.

Why this is safe: ``DATABASE_URL`` is overwritten **before ``app`` is imported for the
first time**, so ``app.core.database`` builds its one process-wide engine against the
temp file. There is no code path back to the developer's MySQL, and
``_assert_not_production_database`` fails the whole session if that ever stops being
true. Nothing here mutates the real ``.env``.

Schema comes from ``Base.metadata.create_all`` rather than Alembic: the suite tests
application behaviour, not the migration chain. Migrations deserve their own test and
a MySQL container — noted as debt in ``docs/testing.md``.
"""

from __future__ import annotations

import pytest

# Imported FIRST, for its side effects: it rewrites DATABASE_URL and the provider
# settings before anything under `app` is imported. Import order is load-bearing here.
from tests._environment import (  # noqa: E402
    TEST_DATABASE_URL as _TEST_DATABASE_URL,
    TEST_DB_PATH as _TEST_DB_PATH,
    assert_not_production_database as _assert_not_production_database,
)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

import app.models  # noqa: E402,F401  — registers every table on Base.metadata
from app.ai.nodes import memory_persistor, memory_retriever  # noqa: E402
from app.core.database import Base  # noqa: E402
from app.core.logging_config import configure_logging  # noqa: E402
from tests.factories import seed_expiry_scenario, seed_scenario  # noqa: E402
from tests.fakes import FakeLLM, FakeMemoryRepository, default_responses  # noqa: E402

# Node modules that did `from app.ai.llm import get_llm`. That binds the function
# *by value* into each module's namespace, so patching `app.ai.llm.get_llm` alone
# would not reach them — each module must be patched individually.
_LLM_NODE_MODULES = (
    "app.ai.nodes.business_planner",
    "app.ai.nodes.business_analyzer",
    "app.ai.nodes.business_reflector",
    "app.ai.nodes.memory_extractor",
    "app.ai.nodes.expiry_planner",
    "app.ai.nodes.expiry_analyzer",
)


# Installed once, at collection time. configure_logging() replaces the root handlers,
# so letting it run lazily during a test (on the first `app.main` import) would rip out
# pytest's caplog handler mid-test. Running it here makes the ordering deterministic.
# The record factory it installs is what puts request_id/run_id on caplog's records.
configure_logging(level="DEBUG")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def engine():
    _assert_not_production_database(_TEST_DATABASE_URL)

    test_engine = create_engine(
        _TEST_DATABASE_URL,
        # The fetcher calls tools from worker threads; without this SQLite refuses
        # a connection created on one thread and used on another.
        connect_args={"check_same_thread": False},
    )

    yield test_engine

    # Two engines hold this file: this one, and the process-wide engine that
    # `app.core.database` built at import. Windows refuses to unlink a file with an
    # open handle, so both must be disposed before cleanup.
    test_engine.dispose()

    from app.core.database import engine as app_engine

    app_engine.dispose()

    try:
        _TEST_DB_PATH.unlink(missing_ok=True)
    except PermissionError:
        # A stray handle should not fail an otherwise green run; the next session
        # recreates the schema from scratch anyway.
        pass


@pytest.fixture(autouse=True)
def clean_database(engine):
    """Drop and recreate every table before each test.

    Blunt, and correct. Wrapping each test in a rolled-back transaction is the
    faster idiom, but it only isolates a *single* session — the BI graph opens its
    own sessions on worker threads, which would not see uncommitted rows. On SQLite
    a full rebuild of ten tables costs single-digit milliseconds.
    """

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(engine) -> Session:
    """A session for tests that talk to repositories directly."""

    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_db(db_session) -> Session:
    """``db_session`` with the fixed scenario from ``tests/factories.py`` loaded."""

    seed_scenario(db_session)
    return db_session


@pytest.fixture
def seeded_app_db(seeded_db):
    """Scenario data visible to code that opens its *own* session.

    The BI tools call ``SessionLocal()`` themselves rather than receiving a session,
    so they read through the app engine. Both engines point at the same temp file,
    so seeding through ``seeded_db`` is enough — this fixture exists to say so at the
    point of use instead of leaving the reader to infer it.
    """

    return seeded_db


@pytest.fixture
def expiry_as_of() -> "date":
    """The date the expiry scenario is built around.

    A fixed Wednesday rather than the real clock, so no expiry test changes meaning
    overnight or fails on the first of a month.
    """

    from datetime import date

    return date(2026, 9, 16)


@pytest.fixture
def expiry_db(db_session, expiry_as_of):
    """``db_session`` with the expiry scenario loaded, relative to ``expiry_as_of``.

    For unit tests, which pass ``as_of`` explicitly into the service.
    """

    seed_expiry_scenario(db_session, expiry_as_of)
    return db_session


@pytest.fixture
def expiry_app_db(db_session):
    """The expiry scenario anchored to the REAL today.

    Tests that drive the graph or the endpoint need this. Production always assesses
    against today — there is deliberately no way to pass ``as_of`` through the graph,
    since a caller choosing the reference date could quietly produce a report about
    a day that never happened. The scenario is defined in relative days, so every
    derived figure is identical whichever day it runs on.
    """

    from app.core.time_range import today

    seed_expiry_scenario(db_session, today())
    return db_session


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_llm(monkeypatch) -> FakeLLM:
    """Replace the provider client in every BI node with a scripted fake.

    Autouse is deliberately avoided: a test that needs the LLM should say so, and a
    test that accidentally reaches one should fail loudly on a missing API key rather
    than pass against a fake it never asked for.
    """

    llm = FakeLLM(responses=default_responses())

    for module_path in _LLM_NODE_MODULES:
        monkeypatch.setattr(f"{module_path}.get_llm", lambda: llm)

    return llm


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_memory(monkeypatch) -> FakeMemoryRepository:
    """Keep every test away from the real ChromaDB store at ``memory_db/``.

    Autouse *is* right here: the cost of forgetting is that a test writes junk into
    the developer's real long-term memory and bills real embedding calls to do it.
    """

    repository = FakeMemoryRepository()

    monkeypatch.setattr(memory_retriever, "get_repository", lambda: repository)
    monkeypatch.setattr(memory_persistor, "get_repository", lambda: repository)

    return repository


# ---------------------------------------------------------------------------
# Graph / HTTP
# ---------------------------------------------------------------------------


@pytest.fixture
def thread_id(request) -> str:
    """A conversation id unique to each test.

    ``get_business_graph()`` is ``lru_cache``d and its ``MemorySaver`` therefore
    outlives a single test. Sharing a thread id would leak one test's conversation
    history into the next.
    """

    return f"test-{request.node.name}"


@pytest.fixture
def client():
    """FastAPI test client over the real app, including its real routers."""

    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    def _override_get_db():
        from app.core.database import SessionLocal

        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
