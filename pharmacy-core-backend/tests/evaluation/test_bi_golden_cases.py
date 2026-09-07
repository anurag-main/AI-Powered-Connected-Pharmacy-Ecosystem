"""The golden set as pytest cases, so a regression fails CI rather than a report.

One test per case, named by id, so a failure says which question broke. The harness
in ``runner.py`` does the work; this file only supplies the database fixture and
turns each result into an assertion.

For the human-readable summary instead:

    python -m tests.evaluation.runner
"""

from __future__ import annotations

import pytest

from tests.evaluation.runner import PASS, SKIP, load_cases, run_case

pytestmark = pytest.mark.evaluation

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_golden_case(case, seeded_app_db):
    result = run_case(case)

    if result.status == SKIP:
        pytest.skip(result.reason)

    assert result.status == PASS, "\n".join(
        [f"{case['id']} ({case['category']}): {case['question']}", *result.failures]
    )


def test_every_case_has_the_required_fields():
    """A malformed case would silently grade nothing."""

    required = {
        "id",
        "question",
        "category",
        "expected_behavior",
        "planned_queries",
        "requires_real_llm",
    }

    for case in CASES:
        missing = required - set(case)
        assert not missing, f"{case.get('id', '?')} is missing {sorted(missing)}"


def test_case_ids_are_unique():
    ids = [case["id"] for case in CASES]

    assert len(ids) == len(set(ids)), "duplicate golden case id"


def test_every_planned_query_is_valid():
    """Guards against aspirational cases the system cannot serve.

    A case demanding a category breakdown would fail forever and train everyone to
    ignore a red suite. BusinessQuery validation is the same gate the planner faces,
    so constructing each one here proves the case is answerable in principle.
    """

    from pydantic import ValidationError

    from app.ai.schemas.business_query import BusinessQuery

    for case in CASES:
        for raw in case["planned_queries"]:
            try:
                BusinessQuery(**raw)
            except ValidationError as exc:
                pytest.fail(f"{case['id']} plans an invalid query {raw}: {exc}")


def test_the_set_covers_every_capability_class():
    """A regression set that never exercises ranking would not notice it breaking."""

    categories = {case["category"] for case in CASES}

    assert {
        "sales",
        "date_filtering",
        "ranking",
        "grouping",
        "combined",
        "off_topic",
    } <= categories
