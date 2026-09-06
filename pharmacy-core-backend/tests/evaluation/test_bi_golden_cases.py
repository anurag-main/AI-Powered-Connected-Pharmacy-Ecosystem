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
        "planned_capabilities",
        "requires_real_llm",
    }

    for case in CASES:
        missing = required - set(case)
        assert not missing, f"{case.get('id', '?')} is missing {sorted(missing)}"


def test_case_ids_are_unique():
    ids = [case["id"] for case in CASES]

    assert len(ids) == len(set(ids)), "duplicate golden case id"


def test_no_case_asks_for_a_capability_that_does_not_exist():
    """Guards against writing aspirational cases the repository cannot serve.

    A case demanding date filtering or per-product ranking would fail forever and
    train everyone to ignore a red suite.
    """

    from app.ai.tools.business_tools import TOOL_REGISTRY

    for case in CASES:
        unknown = set(case["planned_capabilities"]) - set(TOOL_REGISTRY)
        assert not unknown, f"{case['id']} plans unknown capabilities: {sorted(unknown)}"
