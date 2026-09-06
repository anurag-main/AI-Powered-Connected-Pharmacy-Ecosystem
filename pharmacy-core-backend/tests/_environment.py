"""Test environment setup — imported for its side effects, before any ``app`` import.

Lives in its own module because two entry points need it: ``conftest.py`` for pytest,
and ``tests/evaluation/runner.py`` when the evaluation suite is run straight from the
command line. Importing it twice is harmless; the assignments are idempotent.

Leading underscore keeps pytest from collecting it as a test module.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TEST_DB_PATH = Path(tempfile.gettempdir()) / "pharmacy_test.sqlite3"
TEST_DATABASE_URL = f"sqlite+pysqlite:///{TEST_DB_PATH.as_posix()}"


def configure() -> None:
    """Point the process at throwaway infrastructure. Must run before ``import app``."""

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    # The provider factory validates the key before building a client. Tests never
    # reach a real provider — every call goes through FakeLLM — but a placeholder-
    # looking key would make get_llm() raise, which is the failure we want rather
    # than a silent live call.
    os.environ["LLM_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = "sk-test-fake-key-not-used"
    # Never emit traces from a test run, whatever the developer's .env says.
    os.environ["LANGCHAIN_TRACING_V2"] = "false"


def assert_not_production_database(url: str) -> None:
    if not url.startswith("sqlite"):
        raise RuntimeError(
            f"Refusing to run tests against {url!r}. The suite drops and recreates "
            "every table; pointing it at MySQL would destroy real data."
        )


configure()
