"""LangSmith configuration reporting.

Entirely offline. Nothing here contacts LangSmith, needs an account, or asserts that a
trace was delivered — that is the one part of observability only a real credential can
confirm, and it is documented as such rather than faked with a mock that would prove
nothing.

What *can* be verified locally is the configuration logic, and that is worth testing
precisely because getting it wrong is silent: the project ran for months with an API
key, no tracing flag, and zero traces, while believing tracing was on.
"""

from __future__ import annotations

import logging

import pytest

from app.core.tracing import log_tracing_status, tracing_status

pytestmark = pytest.mark.unit

_ALL_VARS = (
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING",
    "LANGSMITH_API_KEY",
    "LANGCHAIN_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGCHAIN_PROJECT",
    "LANGSMITH_ENDPOINT",
    "LANGCHAIN_ENDPOINT",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Start from no tracing configuration at all."""

    for name in _ALL_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# The flag is what turns tracing on
# ---------------------------------------------------------------------------


def test_no_configuration_means_tracing_is_off(clean_env):
    status = tracing_status()

    assert status["enabled"] is False
    assert status["api_key_present"] is False


def test_an_api_key_alone_does_not_enable_tracing(clean_env):
    """THE bug this module exists for. A key without a flag traces nothing."""

    clean_env.setenv("LANGCHAIN_API_KEY", "lsv2_pt_placeholder")
    clean_env.setenv("LANGCHAIN_PROJECT", "ai-pharmacy-ecosystem")

    status = tracing_status()

    assert status["enabled"] is False
    assert status["api_key_present"] is True


@pytest.mark.parametrize(
    "flag_var",
    [
        "LANGSMITH_TRACING_V2",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_TRACING",
        "LANGCHAIN_TRACING",
    ],
)
def test_any_of_the_four_flag_names_enables_tracing(clean_env, flag_var):
    """Matches the namespaces the installed langsmith actually searches."""

    clean_env.setenv(flag_var, "true")

    status = tracing_status()

    assert status["enabled"] is True
    assert status["flag_var"] == flag_var


@pytest.mark.parametrize("value", ["false", "1", "yes", "TRUE ", ""])
def test_only_the_literal_string_true_enables_tracing(clean_env, value):
    """The library compares to "true" exactly; "1" and "yes" do nothing.

    A plausible-looking value that silently disables tracing is the whole trap.
    """

    clean_env.setenv("LANGSMITH_TRACING", value)

    assert tracing_status()["enabled"] is False


def test_the_langsmith_namespace_wins_over_langchain(clean_env):
    clean_env.setenv("LANGCHAIN_PROJECT", "legacy-name")
    clean_env.setenv("LANGSMITH_PROJECT", "current-name")

    assert tracing_status()["project"] == "current-name"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_the_api_key_is_never_returned_or_logged(clean_env, caplog):
    """The status object is logged; it must carry presence, never the secret."""

    secret = "lsv2_pt_this_must_never_appear_anywhere"
    clean_env.setenv("LANGSMITH_API_KEY", secret)
    clean_env.setenv("LANGSMITH_TRACING", "true")

    with caplog.at_level(logging.INFO):
        status = log_tracing_status()

    assert secret not in repr(status)

    blob = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert secret not in blob


def test_a_key_without_a_flag_produces_a_warning(clean_env, caplog):
    """The misconfiguration must announce itself at every boot, not stay silent."""

    clean_env.setenv("LANGCHAIN_API_KEY", "lsv2_pt_placeholder")

    with caplog.at_level(logging.WARNING):
        log_tracing_status()

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert "tracing_disabled_despite_api_key" in warnings


def test_a_flag_without_a_key_produces_a_warning(clean_env, caplog):
    clean_env.setenv("LANGSMITH_TRACING", "true")

    with caplog.at_level(logging.WARNING):
        log_tracing_status()

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert "tracing_enabled_without_api_key" in warnings


def test_a_correct_configuration_produces_no_warning(clean_env, caplog):
    clean_env.setenv("LANGSMITH_TRACING", "true")
    clean_env.setenv("LANGSMITH_API_KEY", "lsv2_pt_placeholder")
    clean_env.setenv("LANGSMITH_PROJECT", "ai-pharmacy-ecosystem")

    with caplog.at_level(logging.WARNING):
        status = log_tracing_status()

    assert status["enabled"] is True
    assert status["project"] == "ai-pharmacy-ecosystem"
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_tests_themselves_never_enable_tracing():
    """The suite must not send traces anywhere, whatever is in the developer's .env."""

    import os

    assert os.environ.get("LANGCHAIN_TRACING_V2") == "false"
    assert tracing_status()["enabled"] is False
