"""Reorder maths — the deterministic core of the Smart Reorder Agent.

Pure functions with no database and no LLM, which is exactly why they belong at the
bottom of the pyramid: they are the cheapest tests in the suite and they guard the
project's central rule — arithmetic that decides money is computed in Python, never
by a model.
"""

from __future__ import annotations

import math

import pytest

from app.ai.tools.reorder_tools import (
    MAX_REORDER_QTY,
    days_of_cover,
    is_qty_sane,
    suggest_reorder_qty,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# days_of_cover
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stock", "velocity", "expected"),
    [
        (5, 1, 5.0),
        (100, 4, 25.0),
        (0, 2, 0.0),
        (7, 2, 3.5),
    ],
)
def test_days_of_cover(stock, velocity, expected):
    assert days_of_cover(stock, velocity) == expected


def test_days_of_cover_treats_a_non_selling_medicine_as_infinite():
    """The divide-by-zero guard. Infinite cover means "never reorder", which is the
    right default: a medicine with no sales must not trigger a purchase."""

    assert days_of_cover(10, 0) == math.inf


def test_days_of_cover_guards_against_negative_velocity():
    """Velocity cannot be negative, but a bad query could produce one; it must hit
    the same guard rather than returning a negative day count."""

    assert days_of_cover(10, -1) == math.inf


# ---------------------------------------------------------------------------
# suggest_reorder_qty
# ---------------------------------------------------------------------------


def test_suggest_reorder_qty_covers_lead_time_plus_safety():
    # 2/day for (3 lead + 2 safety) days = 10 units.
    assert suggest_reorder_qty(2, 3, 2) == 10


def test_suggest_reorder_qty_rounds_up():
    """Stock is discrete: ordering 4.2 units means ordering 5, never 4 — rounding
    down would under-order every single time."""

    assert suggest_reorder_qty(1.4, 2, 1) == 5  # 1.4 x 3 = 4.2 -> 5


def test_suggest_reorder_qty_is_zero_for_a_non_selling_medicine():
    assert suggest_reorder_qty(0, 3, 2) == 0


def test_suggest_reorder_qty_returns_a_whole_number():
    assert isinstance(suggest_reorder_qty(1.4, 2, 1), int)


# ---------------------------------------------------------------------------
# is_qty_sane
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("qty", [1, 10, MAX_REORDER_QTY])
def test_is_qty_sane_accepts_plausible_orders(qty):
    assert is_qty_sane(qty) is True


@pytest.mark.parametrize("qty", [0, -1, MAX_REORDER_QTY + 1, 9_000_000])
def test_is_qty_sane_rejects_impossible_orders(qty):
    """The self-correction net. A hallucinated or miscalculated 9,000,000-unit order
    must never reach the pharmacist as a proposal."""

    assert is_qty_sane(qty) is False
