"""The inventory golden set as pytest cases, so a regression fails CI, not a report.

For the human-readable summary instead:

    python -m tests.evaluation.inventory_runner
"""

from __future__ import annotations

import pytest

from tests.evaluation.inventory_runner import PASS, SKIP, load_cases, run_case

pytestmark = pytest.mark.evaluation

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_inventory_golden_case(case, inventory_app_db):
    result = run_case(case)

    if result.status == SKIP:
        pytest.skip(result.reason)

    assert result.status == PASS, "\n".join(
        [f"{case['id']} ({case['category']}): {case['question']}", *result.failures]
    )


def test_every_case_has_the_required_fields():
    required = {"id", "question", "category", "planned_query", "requires_real_llm"}

    for case in CASES:
        missing = required - set(case)
        assert not missing, f"{case.get('id', '?')} is missing {sorted(missing)}"


def test_case_ids_are_unique():
    ids = [case["id"] for case in CASES]

    assert len(ids) == len(set(ids)), "duplicate inventory case id"


def test_every_planned_query_is_valid():
    """A case the planner could not legally produce would fail forever."""

    from pydantic import ValidationError

    from app.ai.schemas.inventory_query import InventoryRiskQuery

    for case in CASES:
        try:
            InventoryRiskQuery(**case["planned_query"])
        except ValidationError as exc:
            pytest.fail(f"{case['id']} plans an invalid query: {exc}")


def test_the_set_covers_the_capabilities_that_matter():
    """A set that never exercises dead stock or the expiry boundary would not notice
    them break."""

    categories = {case["category"] for case in CASES}

    assert {
        "basic",
        "dead_stock",
        "capital",
        "sorting",
        "prioritisation",
        "risk_level",
        "stock_age",
        "target_cover",
        "unsellable",
        "action_request",
        "out_of_scope",
    } <= categories


def test_the_set_guards_the_boundary_with_the_expiry_agent():
    """At least one case must assert that no expiry date leaks into the output. That
    boundary is what keeps the two dashboards from becoming the same screen."""

    assert any(
        (case.get("expect") or {}).get("no_expiry_dates") for case in CASES
    ), "no case asserts no_expiry_dates"
