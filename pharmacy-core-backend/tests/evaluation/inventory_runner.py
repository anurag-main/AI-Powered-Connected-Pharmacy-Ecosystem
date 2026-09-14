"""Evaluation harness for the Inventory Risk Agent.

    python -m tests.evaluation.inventory_runner          # fake LLM (default, offline)
    python -m tests.evaluation.inventory_runner --real   # real provider, real cost

WHAT THIS GRADES
----------------
Like the expiry harness and unlike the BI one, this asserts **actual computed
values** — capital at risk in rupees, days of cover, which medicine ranks first. That
is possible because the whole calculation is deterministic: given the same stock and
sales, the report is identical every time, whatever the model says.

So in fake-LLM mode the planner is scripted from each case's ``planned_query``, and
the harness then checks that the deterministic pipeline produced the right numbers.
That is a genuine correctness suite, not just a plumbing check.

``--real`` additionally grades the planner's own choice of query against
``planned_query``.

Cases marked ``requires_real_llm`` test model judgement — refusing to take an action,
redirecting a question that belongs to the expiry agent. They are skipped in fake mode
and reported as skipped, never as passed.
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

from app.ai.schemas.inventory_analysis import InventoryAnalysis
from app.ai.schemas.inventory_query import InventoryRiskQuery
from tests.fakes import FakeLLM

CASES_PATH = Path(__file__).parent / "inventory_risk_cases.json"

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

_LLM_NODE_MODULES = (
    "app.ai.nodes.inventory_planner",
    "app.ai.nodes.inventory_analyzer",
)


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


@dataclass
class CaseResult:
    case_id: str
    category: str
    status: str
    failures: list[str] = field(default_factory=list)
    reason: str = ""

    def __str__(self) -> str:
        line = f"{self.case_id:<9} {self.status:<5} {self.category}"
        if self.reason:
            line += f"  ({self.reason})"
        for failure in self.failures:
            line += f"\n              - {failure}"
        return line


# ---------------------------------------------------------------------------
# Scripted LLM
# ---------------------------------------------------------------------------


@contextmanager
def _scripted_llm(case: dict[str, Any]) -> Iterator[FakeLLM]:
    """Patch both inventory nodes' LLM with a fake scripted for this case.

    ``unittest.mock.patch`` rather than pytest's monkeypatch, so the harness also runs
    straight from the command line.
    """

    llm = FakeLLM(
        responses={
            InventoryRiskQuery: InventoryRiskQuery(**case["planned_query"]),
            InventoryAnalysis: InventoryAnalysis(
                summary=f"Scripted analysis for {case['id']}.",
                confidence=0.9,
            ),
        }
    )

    patches = [patch(f"{module}.get_llm", lambda: llm) for module in _LLM_NODE_MODULES]
    for active in patches:
        active.start()
    try:
        yield llm
    finally:
        for active in patches:
            active.stop()


@contextmanager
def _no_patching() -> Iterator[None]:
    yield


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_state(case: dict[str, Any], state: dict, *, real_llm: bool) -> list[str]:
    """Return failure descriptions — empty means the case passed."""

    failures: list[str] = []
    expect = case.get("expect") or {}
    report = state.get("report")
    query = state.get("query")

    # Universal invariants, true for every case.
    if report is None:
        return ["no report was produced"]

    answer = state.get("answer", "")
    if not isinstance(answer, str) or not answer.strip():
        failures.append("no answer was produced")

    confidence = state.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:
        failures.append(f"confidence out of range: {confidence!r}")

    if not report.notes:
        failures.append("report carries no notes, so caveats cannot reach the user")

    # Capital at risk can never exceed what the shop actually holds. If it does, the
    # dead-stock branch is double-counting and the headline figure is nonsense.
    if report.total_capital_at_risk > report.total_inventory_value:
        failures.append(
            f"capital at risk {report.total_capital_at_risk} exceeds inventory value "
            f"{report.total_inventory_value}"
        )

    by_name = {item.medicine_name: item for item in report.items}

    if real_llm:
        expected_query = InventoryRiskQuery(**case["planned_query"])
        if query.risk_level != expected_query.risk_level:
            failures.append(
                f"planner chose risk_level {query.risk_level}, "
                f"expected {expected_query.risk_level}"
            )
        if query.sort != expected_query.sort:
            failures.append(
                f"planner chose sort {query.sort}, expected {expected_query.sort}"
            )
        if query.target_cover_days != expected_query.target_cover_days:
            failures.append(
                f"planner chose target_cover_days {query.target_cover_days}, "
                f"expected {expected_query.target_cover_days}"
            )

    # -- deterministic expectations -------------------------------------

    if "medicines" in expect:
        if set(by_name) != set(expect["medicines"]):
            failures.append(
                f"returned {sorted(by_name)}, expected {sorted(expect['medicines'])}"
            )

    if "min_medicines" in expect and len(report.items) < expect["min_medicines"]:
        failures.append(
            f"returned {len(report.items)} medicines, expected at least "
            f"{expect['min_medicines']}"
        )

    if "first_medicine" in expect:
        actual = report.items[0].medicine_name if report.items else None
        if actual != expect["first_medicine"]:
            failures.append(
                f"top-ranked medicine {actual}, expected {expect['first_medicine']}"
            )

    for key in (
        "medicines_reviewed",
        "items_matching_filter",
        "total_capital_at_risk",
        "total_inventory_value",
    ):
        if key in expect and getattr(report, key) != expect[key]:
            failures.append(f"{key} {getattr(report, key)}, expected {expect[key]}")

    if "counts_by_risk" in expect and report.counts_by_risk != expect["counts_by_risk"]:
        failures.append(
            f"counts_by_risk {report.counts_by_risk}, expected {expect['counts_by_risk']}"
        )

    if "risk_levels" in expect:
        allowed = set(expect["risk_levels"])
        wrong = {
            item.medicine_name: item.risk_level.value
            for item in report.items
            if item.risk_level.value not in allowed
        }
        if wrong:
            failures.append(f"unexpected risk levels: {wrong}")

    for name, fields in (expect.get("item") or {}).items():
        item = by_name.get(name)
        if item is None:
            failures.append(f"expected {name} in the report")
            continue
        for field_name, expected_value in fields.items():
            actual = getattr(item, field_name)
            actual = actual.value if hasattr(actual, "value") else actual
            if actual != expected_value:
                failures.append(
                    f"{name}.{field_name} = {actual}, expected {expected_value}"
                )

    if "note_contains" in expect:
        if not any(expect["note_contains"] in note for note in report.notes):
            failures.append(f"no note containing {expect['note_contains']!r}")

    # The boundary with the expiry agent, asserted rather than trusted.
    if expect.get("no_expiry_dates"):
        leaked = [
            (item.medicine_name, reason)
            for item in report.items
            for reason in item.risk_reasons
            if "expir" in reason.lower()
        ]
        if leaked:
            failures.append(f"reasons mention expiry: {leaked}")

    return failures


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def run_case(case: dict[str, Any], *, real_llm: bool = False) -> CaseResult:
    from langchain_core.messages import HumanMessage

    from app.ai.graphs.inventory_graph import get_inventory_graph

    if case.get("requires_real_llm") and not real_llm:
        return CaseResult(
            case_id=case["id"],
            category=case["category"],
            status=SKIP,
            reason="needs a real LLM; run with --real",
        )

    config = {"configurable": {"thread_id": f"inventory-eval-{case['id']}"}}
    payload = {"messages": [HumanMessage(content=case["question"])]}

    context = _no_patching() if real_llm else _scripted_llm(case)

    try:
        with context:
            state = get_inventory_graph().invoke(payload, config=config)
    except Exception as exc:  # noqa: BLE001 — a crash is a failed case, not a crash
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

    Seeds relative to today, because the graph always assesses against today.
    """

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401
    from app.core.database import Base
    from app.core.time_range import today
    from tests._environment import TEST_DATABASE_URL, assert_not_production_database
    from tests.factories import seed_inventory_scenario

    assert_not_production_database(TEST_DATABASE_URL)

    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    session = sessionmaker(bind=engine)()
    try:
        seed_inventory_scenario(session, today())
    finally:
        session.close()
        engine.dispose()


def run_all(*, real_llm: bool = False) -> list[CaseResult]:
    return [run_case(case, real_llm=real_llm) for case in load_cases()]


def format_report(results: list[CaseResult], *, real_llm: bool) -> str:
    lines = [
        "",
        f"INVENTORY RISK EVALUATION  ({'real LLM' if real_llm else 'fake LLM'})",
        "=" * 62,
    ]
    lines.extend(str(result) for result in results)

    passed = sum(1 for r in results if r.status == PASS)
    failed = sum(1 for r in results if r.status == FAIL)
    skipped = sum(1 for r in results if r.status == SKIP)

    lines.append("=" * 62)
    lines.append(f"{passed}/{passed + failed} graded cases passed  ({skipped} skipped)")

    if failed:
        lines.append("")
        lines.append("Failed: " + ", ".join(r.case_id for r in results if r.status == FAIL))

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the inventory-risk golden set.")
    parser.add_argument(
        "--real",
        action="store_true",
        help="use the configured LLM provider instead of the fake (costs money)",
    )
    args = parser.parse_args()

    if args.real:
        import os

        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("LLM_PROVIDER", None)

    setup_database()
    results = run_all(real_llm=args.real)
    print(format_report(results, real_llm=args.real))

    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
