"""The memory write policy — where the model stops authorising its own writes.

Two of the QA pass's critical findings live here: a 0.7-confidence off-topic remark
stored as a durable preference, and near-identical facts accumulating as separate
documents. These tests pin the gates that stop both.
"""

from __future__ import annotations

import logging

import pytest

from app.ai.memory.memory_policy import (
    ALLOWED_CATEGORIES,
    MAX_FACT_LENGTH,
    MIN_CONFIDENCE,
    evaluate,
    filter_persistable,
    log_rejections,
    normalize_fact,
)
from app.ai.memory.memory_repository import MemoryScope
from app.ai.schemas.memory import MemoryFact

pytestmark = pytest.mark.unit


def fact(
    text: str = "The pharmacy operates from Pune.",
    category: str = "business",
    confidence: float = 0.9,
) -> MemoryFact:
    return MemoryFact(fact=text, category=category, confidence=confidence)


# ---------------------------------------------------------------------------
# Confidence gate
# ---------------------------------------------------------------------------


def test_a_confident_fact_is_accepted():
    assert evaluate(fact(confidence=0.9)).accepted


def test_a_fact_exactly_at_the_threshold_is_accepted():
    assert evaluate(fact(confidence=MIN_CONFIDENCE)).accepted


def test_the_qa_false_positive_is_now_rejected():
    """The specific regression.

    The QA pass observed an off-topic remark about an election stored as a "User
    Preference" with confidence 0.7. The threshold sits above that measured value,
    so the same input is now refused.
    """

    decision = evaluate(fact(confidence=0.7))

    assert not decision.accepted
    assert decision.reason == "confidence_below_threshold"


@pytest.mark.parametrize("confidence", [0.0, 0.1, 0.5, 0.79])
def test_low_confidence_facts_are_rejected(confidence):
    assert not evaluate(fact(confidence=confidence)).accepted


def test_the_threshold_sits_between_the_observed_false_and_true_positives():
    """Documents where the number came from: above the 0.7 junk, below the 0.9
    genuine facts. Not a round number picked by feel."""

    assert 0.7 < MIN_CONFIDENCE <= 0.9


# ---------------------------------------------------------------------------
# Category allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category", sorted(ALLOWED_CATEGORIES))
def test_every_allowed_category_is_accepted(category):
    assert evaluate(fact(category=category)).accepted


@pytest.mark.parametrize(
    "category",
    ["User Preference", "opinion", "politics", "metric", "random", ""],
)
def test_a_category_outside_the_allowlist_is_rejected(category):
    """`category` is free text from the model, so a new invented category must not
    silently become a new class of stored data."""

    decision = evaluate(fact(category=category))

    assert not decision.accepted
    assert decision.reason == "category_not_allowed"


def test_category_matching_ignores_case_and_padding():
    assert evaluate(fact(category="  Business  ")).accepted


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "ok", "short"])
def test_junk_facts_are_rejected(text):
    assert not evaluate(fact(text=text)).accepted


def test_an_enormous_fact_is_rejected():
    """Nobody should be able to paste a report into long-term memory."""

    decision = evaluate(fact(text="x" * (MAX_FACT_LENGTH + 1)))

    assert not decision.accepted
    assert decision.reason == "fact_too_long"


# ---------------------------------------------------------------------------
# Normalization and deduplication
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("I prefer monthly reports.", "I prefer monthly reports"),
        ("I prefer monthly reports.", "i prefer monthly reports."),
        ("I prefer  monthly   reports.", "I prefer monthly reports."),
        ("  I prefer monthly reports.  ", "I prefer monthly reports."),
        ("I prefer monthly reports!", "I prefer monthly reports?"),
    ],
)
def test_restatements_normalize_to_the_same_form(first, second):
    assert normalize_fact(first) == normalize_fact(second)


def test_genuinely_different_facts_do_not_collide():
    assert normalize_fact("We are in Pune.") != normalize_fact("We are in Mumbai.")


def test_a_duplicate_of_a_stored_fact_is_dropped():
    existing = {normalize_fact("The pharmacy operates from Pune.")}

    accepted, rejected = filter_persistable([fact()], existing_normalized=existing)

    assert accepted == []
    assert rejected[0][1] == "duplicate"


def test_duplicates_within_one_batch_are_collapsed():
    """The extractor can restate the same fact twice in one pass."""

    accepted, rejected = filter_persistable(
        [fact(), fact(text="the pharmacy operates from pune")],
        existing_normalized=set(),
    )

    assert len(accepted) == 1
    assert rejected[0][1] == "duplicate"


def test_semantic_paraphrase_is_not_caught():
    """An honest limit. Deterministic normalization catches restatements, not
    rewrites — "monthly reporting is my preference" is a different string. Embedding
    similarity would catch it and is recorded as future work rather than pretended.
    """

    accepted, _ = filter_persistable(
        [
            fact(text="I prefer monthly reports.", category="preference"),
            fact(text="Monthly reporting is my preference.", category="preference"),
        ],
        existing_normalized=set(),
    )

    assert len(accepted) == 2, "both stored — paraphrase detection is not implemented"


# ---------------------------------------------------------------------------
# Filtering as a whole
# ---------------------------------------------------------------------------


def test_a_mixed_batch_is_split_correctly():
    candidates = [
        fact(text="The pharmacy operates from Pune.", confidence=0.95),
        fact(text="The election is coming up soon.", category="opinion", confidence=0.7),
        fact(text="The owner wants monthly reports.", category="preference", confidence=0.85),
        fact(text="Sales were 653281 rupees.", category="business", confidence=0.5),
    ]

    accepted, rejected = filter_persistable(candidates, existing_normalized=set())

    assert len(accepted) == 2
    assert {memory.fact for memory in accepted} == {
        "The pharmacy operates from Pune.",
        "The owner wants monthly reports.",
    }
    assert {reason for _, reason in rejected} == {
        "category_not_allowed",
        "confidence_below_threshold",
    }


def test_an_empty_batch_is_handled():
    assert filter_persistable([], existing_normalized=set()) == ([], [])


# ---------------------------------------------------------------------------
# Rejection logging
# ---------------------------------------------------------------------------


def test_rejections_are_logged_so_the_gate_is_debuggable(caplog):
    """"Why doesn't it remember that?" must have an answer in the logs."""

    with caplog.at_level(logging.INFO):
        log_rejections([(fact(confidence=0.2), "confidence_below_threshold")])

    record = [r for r in caplog.records if r.getMessage() == "memory_rejected"][-1]
    assert record.reason == "confidence_below_threshold"
    assert record.confidence == 0.2


def test_the_fact_text_is_never_logged(caplog):
    """Memories are user content; the reason and score are enough to debug the gate."""

    secret = "The owner is negotiating a confidential merger."

    with caplog.at_level(logging.DEBUG):
        log_rejections([(fact(text=secret, confidence=0.2), "confidence_below_threshold")])

    blob = "\n".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert secret not in blob


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def test_a_scope_requires_a_thread_id():
    """An unscoped write would be readable from every conversation."""

    with pytest.raises(ValueError, match="non-empty thread_id"):
        MemoryScope(thread_id="")


def test_a_whitespace_thread_id_is_rejected():
    with pytest.raises(ValueError, match="non-empty thread_id"):
        MemoryScope(thread_id="   ")


def test_the_scope_filter_and_metadata_agree():
    """Write tagging and read filtering must use the same fields, or isolation
    depends on a coincidence."""

    scope = MemoryScope(thread_id="conv-1")

    assert scope.as_filter() == {"thread_id": "conv-1"}
    assert scope.as_metadata() == scope.as_filter()


def test_scopes_compare_by_value():
    assert MemoryScope(thread_id="a") == MemoryScope(thread_id="a")
    assert MemoryScope(thread_id="a") != MemoryScope(thread_id="b")
