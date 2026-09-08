"""The expiry golden set as pytest cases, so a regression fails CI, not a report.

For the human-readable summary instead:

    python -m tests.evaluation.expiry_runner
"""

from __future__ import annotations

import pytest

from tests.evaluation.expiry_runner import PASS, SKIP, load_cases, run_case

pytestmark = pytest.mark.evaluation

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_expiry_golden_case(case, expiry_app_db):
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

    assert len(ids) == len(set(ids)), "duplicate expiry case id"


def test_every_planned_query_is_valid():
    """A case the planner could not legally produce would fail forever."""

    from pydantic import ValidationError

    from app.ai.schemas.expiry_query import ExpiryRiskQuery

    for case in CASES:
        try:
            ExpiryRiskQuery(**case["planned_query"])
        except ValidationError as exc:
            pytest.fail(f"{case['id']} plans an invalid query: {exc}")


def test_the_set_covers_the_capabilities_that_matter():
    """A set that never exercises FEFO or missing data would not notice them break."""

    categories = {case["category"] for case in CASES}

    assert {
        "basic",
        "window",
        "risk_level",
        "prioritisation",
        "excess",
        "fefo",
        "missing_data",
        "action_request",
    } <= categories
