"""Evaluation harness for the Business Intelligence agent.

Runs every case in ``golden_cases.json`` through the real compiled graph and applies
deterministic checks to the resulting state.

    python -m tests.evaluation.runner          # fake LLM (default, free, offline)
    python -m tests.evaluation.runner --real   # real provider, real cost

WHAT THIS DOES AND DOES NOT MEASURE
-----------------------------------
In the default fake-LLM mode the planner is *scripted* from each case's
``planned_capabilities``. The harness therefore does not grade the model's routing —
it grades the pipeline around it: that the plan is honoured by the fetcher, that no
tool silently fails, that an answer is produced with a confidence in range, and that
the reflection loop stays inside its cap. That is a genuine regression suite for the
graph, and it is honest about not being a model-quality benchmark.

Cases marked ``requires_real_llm`` depend on model judgement (refusing an action,
admitting missing data). They are SKIPPED in fake mode and reported as skipped —
never counted as passes.

``--real`` uses the configured provider and grades the planner's own routing against
``planned_capabilities``. It costs money and is not part of ``pytest``.

Deliberately no LLM-as-judge yet. Deterministic checks first; a judge is only worth
adding once there is something it can grade that these checks cannot.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

import tests._environment  # noqa: F401  — rewrites env before `app` is imported

from app.ai.graphs.business_graph import MAX_REFLECTIONS, get_business_graph
from app.ai.schemas.business_analysis import BusinessAnalysis
from app.ai.schemas.memory import MemoryExtraction
from app.ai.schemas.planner import PlannerOutput
from app.ai.schemas.reflection import ReflectionOutput
from tests.fakes import FakeLLM, FakeMemoryRepository

GOLDEN_CASES_PATH = Path(__file__).parent / "golden_cases.json"

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

_LLM_NODE_MODULES = (
    "app.ai.nodes.business_planner",
    "app.ai.nodes.business_analyzer",
    "app.ai.nodes.business_reflector",
    "app.ai.nodes.memory_extractor",
)


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def load_cases() -> list[dict[str, Any]]:
    payload = json.loads(GOLDEN_CASES_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


@dataclass
class CaseResult:
    case_id: str
    category: str
    status: str
    failures: list[str] = field(default_factory=list)
    reason: str = ""

    def __str__(self) -> str:
        line = f"{self.case_id:<8} {self.status:<5} {self.category}"
        if self.reason:
            line += f"  ({self.reason})"
        for failure in self.failures:
            line += f"\n             - {failure}"
        return line


# ---------------------------------------------------------------------------
# Scripted LLM
# ---------------------------------------------------------------------------


@contextmanager
def _scripted_llm(case: dict[str, Any]) -> Iterator[FakeLLM]:
    """Patch every BI node's LLM with a fake scripted for this case.

    ``unittest.mock.patch`` rather than pytest's monkeypatch, so the harness also
    works when invoked straight from the command line.
    """

    llm = FakeLLM(
        responses={
            PlannerOutput: PlannerOutput(tasks=list(case["planned_capabilities"])),
            BusinessAnalysis: BusinessAnalysis(
                summary=f"Scripted analysis for {case['id']}.",
                key_insights=[],
                recommendations=[],
                confidence=0.9,
            ),
            ReflectionOutput: ReflectionOutput(
                sufficient=True, missing_tasks=[], reason="Complete."
            ),
            MemoryExtraction: MemoryExtraction(memories=[]),
        }
    )

    memory = FakeMemoryRepository()

    with patch.multiple(
        "app.ai.nodes.memory_retriever", get_repository=lambda: memory
    ), patch.multiple("app.ai.nodes.memory_persistor", get_repository=lambda: memory):
        patches = [patch(f"{module}.get_llm", lambda: llm) for module in _LLM_NODE_MODULES]
        for active in patches:
            active.start()
        try:
            yield llm
        finally:
            for active in patches:
                active.stop()


@contextmanager
def _isolated_memory() -> Iterator[FakeMemoryRepository]:
    """Real-LLM mode still must not write into the developer's vector store."""

    memory = FakeMemoryRepository()
    with patch.multiple(
        "app.ai.nodes.memory_retriever", get_repository=lambda: memory
    ), patch.multiple("app.ai.nodes.memory_persistor", get_repository=lambda: memory):
        yield memory


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_state(case: dict[str, Any], state: dict[str, Any], *, real_llm: bool) -> list[str]:
    """Return a list of failure descriptions — empty means the case passed."""

    failures: list[str] = []
    behavior = case["expected_behavior"]
    plan = state.get("plan", [])
    metrics = state.get("business_metrics", {})
    answer = state.get("answer", "")
    confidence = state.get("confidence")

    # Universal invariants — true for every case, whatever it asks.
    if not isinstance(answer, str) or not answer.strip():
        failures.append("no answer was produced")

    if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        failures.append(f"confidence out of range: {confidence!r}")

    reflections = state.get("reflection_count", 0)
    if reflections > MAX_REFLECTIONS:
        failures.append(
            f"reflection loop exceeded its cap: {reflections} > {MAX_REFLECTIONS}"
        )

    if behavior == "answer_from_business_data":
        # The plan must actually drive the fetch. This is the contract that breaks
        # if planner and fetcher drift apart.
        if set(metrics) != set(plan):
            failures.append(
                f"plan {sorted(plan)} does not match fetched metrics {sorted(metrics)}"
            )

        if not plan:
            failures.append("expected business data, but the plan was empty")

        failed_tools = [name for name, value in metrics.items() if "error" in value]
        if failed_tools:
            failures.append(f"tool(s) returned an error: {failed_tools}")

        if real_llm:
            expected = set(case["planned_capabilities"])
            if set(plan) != expected:
                failures.append(
                    f"planner chose {sorted(plan)}, expected {sorted(expected)}"
                )

    elif behavior == "no_business_data_needed":
        if plan:
            failures.append(f"expected no capabilities, planner chose {sorted(plan)}")
        if metrics:
            failures.append(f"expected no metrics, fetched {sorted(metrics)}")

    else:
        failures.append(f"unknown expected_behavior: {behavior!r}")

    return failures


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def run_case(case: dict[str, Any], *, real_llm: bool = False) -> CaseResult:
    """Run one golden case through the real graph and grade the resulting state."""

    from langchain_core.messages import HumanMessage

    if case.get("requires_real_llm") and not real_llm:
        return CaseResult(
            case_id=case["id"],
            category=case["category"],
            status=SKIP,
            reason="needs a real LLM; run with --real",
        )

    config = {"configurable": {"thread_id": f"eval-{case['id']}"}}
    payload = {"messages": [HumanMessage(content=case["question"])]}

    context = _isolated_memory() if real_llm else _scripted_llm(case)

    try:
        with context:
            state = get_business_graph().invoke(payload, config=config)
    except Exception as exc:  # noqa: BLE001 — any crash is a failed case, not a crash
        return CaseResult(
            case_id=case["id"],
            category=case["category"],
            status=FAIL,
            failures=[f"graph raised {type(exc).__name__}: {exc}"],
        )

    failures = check_state(case, state, real_llm=real_llm)

    return CaseResult(
        case_id=case["id"],
        category=case["category"],
        status=FAIL if failures else PASS,
        failures=failures,
    )


def setup_database() -> None:
    """Build and seed the temp SQLite database — CLI mode only.

    Under pytest the ``clean_database``/``seeded_db`` fixtures do this instead.
    """

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401  — registers every table
    from app.core.database import Base
    from tests._environment import TEST_DATABASE_URL, assert_not_production_database
    from tests.factories import seed_scenario

    assert_not_production_database(TEST_DATABASE_URL)

    engine = create_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}
    )
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    session = sessionmaker(bind=engine)()
    try:
        seed_scenario(session)
    finally:
        session.close()
        engine.dispose()


def run_all(*, real_llm: bool = False) -> list[CaseResult]:
    return [run_case(case, real_llm=real_llm) for case in load_cases()]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def format_report(results: list[CaseResult], *, real_llm: bool) -> str:
    lines = [
        "",
        f"BI GOLDEN EVALUATION  ({'real LLM' if real_llm else 'fake LLM'})",
        "=" * 60,
    ]
    lines.extend(str(result) for result in results)

    passed = sum(1 for r in results if r.status == PASS)
    failed = sum(1 for r in results if r.status == FAIL)
    skipped = sum(1 for r in results if r.status == SKIP)
    graded = passed + failed

    lines.append("=" * 60)
    lines.append(f"{passed}/{graded} graded cases passed  ({skipped} skipped)")

    if failed:
        lines.append("")
        lines.append("Failed: " + ", ".join(r.case_id for r in results if r.status == FAIL))

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the BI golden evaluation set.")
    parser.add_argument(
        "--real",
        action="store_true",
        help="use the configured LLM provider instead of the fake (costs money)",
    )
    args = parser.parse_args()

    if args.real:
        # Undo the fake key the test environment installed, so the real provider
        # settings from .env apply.
        import os

        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("LLM_PROVIDER", None)

    setup_database()
    results = run_all(real_llm=args.real)
    print(format_report(results, real_llm=args.real))

    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
