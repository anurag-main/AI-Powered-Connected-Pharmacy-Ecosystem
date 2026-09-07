"""What may be written to long-term memory, decided in code rather than by the model.

WHY A POLICY AT ALL
-------------------
The extractor is an LLM asked "is anything here worth remembering?", and whatever it
answers used to be written verbatim and permanently. That is the model authorising its
own writes. The QA pass found the consequences: an off-topic remark about an election
stored as a "User Preference", and a period-mislabelled sales figure stored as fact —
both then available to be cited as ground truth in later turns.

So the model still *proposes*; this module *decides*. Three deterministic gates.

1. CONFIDENCE
   The extractor scores its own confidence 0.0-1.0. Observed in the QA pass: the
   election remark scored **0.7**, legitimate facts scored **0.9**. The threshold has
   to sit above the observed false positive and below the observed true positives, so
   it is 0.8 — a number taken from measured behaviour, not picked because it looks
   round. If the extractor is later retuned, re-measure before moving it.

2. CATEGORY
   ``category`` is free text from the model. An allowlist keeps the store to kinds of
   fact this system has a reason to recall, and stops a new invented category
   silently becoming a new class of stored data.

3. SHAPE
   Empty, whitespace-only, or absurdly long facts are junk regardless of confidence.

A rejected memory is logged with its reason. Silent dropping would be its own bug —
"why doesn't it remember?" needs an answer in the logs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.ai.schemas.memory import MemoryFact

logger = logging.getLogger("app.ai.memory")

# Above the 0.7 false positive observed in QA, below the 0.9 of genuine facts.
MIN_CONFIDENCE = 0.8

# Kinds of fact worth carrying between turns.
ALLOWED_CATEGORIES = frozenset(
    {
        "business",     # "we are a retail pharmacy in Pune"
        "preference",   # "I want reports monthly"
        "goal",         # "I want to cut expiry losses this quarter"
        "constraint",   # "I never stock schedule X drugs"
    }
)

# Long enough for a real sentence, short enough that nobody pastes a report in.
MIN_FACT_LENGTH = 10
MAX_FACT_LENGTH = 500

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class PolicyDecision:
    """Whether a candidate may be stored, and why not when it may not."""

    accepted: bool
    reason: str = ""


def normalize_fact(fact: str) -> str:
    """Canonical form used for duplicate detection.

    Lowercased, whitespace collapsed, trailing punctuation dropped — so
    "I prefer monthly reports." and "i prefer  monthly reports" are one memory rather
    than two. Deliberately literal: this catches restatements of the same sentence,
    which is the duplicate that actually occurs when a fact is repeated across turns.
    Genuine paraphrase ("monthly reporting is my preference") needs embedding
    similarity and is recorded as future work in docs/business_queries.md.
    """

    return _WHITESPACE.sub(" ", fact).strip().lower().rstrip(".!?")


def evaluate(memory: MemoryFact) -> PolicyDecision:
    """Decide whether one candidate memory may be persisted."""

    fact = (memory.fact or "").strip()

    if len(fact) < MIN_FACT_LENGTH:
        return PolicyDecision(False, "fact_too_short")

    if len(fact) > MAX_FACT_LENGTH:
        return PolicyDecision(False, "fact_too_long")

    category = (memory.category or "").strip().lower()
    if category not in ALLOWED_CATEGORIES:
        return PolicyDecision(False, "category_not_allowed")

    if memory.confidence < MIN_CONFIDENCE:
        return PolicyDecision(False, "confidence_below_threshold")

    return PolicyDecision(True)


def filter_persistable(
    memories: list[MemoryFact], existing_normalized: set[str]
) -> tuple[list[MemoryFact], list[tuple[MemoryFact, str]]]:
    """Split candidates into those to store and those to reject, with reasons.

    ``existing_normalized`` holds the normalized form of what this scope already
    knows, so a repeat of a stored fact is dropped as a duplicate. Duplicates within
    the same batch are collapsed too.
    """

    accepted: list[MemoryFact] = []
    rejected: list[tuple[MemoryFact, str]] = []
    seen = set(existing_normalized)

    for memory in memories:
        decision = evaluate(memory)

        if not decision.accepted:
            rejected.append((memory, decision.reason))
            continue

        normalized = normalize_fact(memory.fact)
        if normalized in seen:
            rejected.append((memory, "duplicate"))
            continue

        seen.add(normalized)
        accepted.append(memory)

    return accepted, rejected


def log_rejections(rejected: list[tuple[MemoryFact, str]]) -> None:
    """Record what was refused, so "why didn't it remember?" is answerable.

    The fact text itself is never logged — it is user content. The category,
    confidence and reason are enough to tell whether the gate behaved correctly.
    """

    for memory, reason in rejected:
        logger.info(
            "memory_rejected",
            extra={
                "reason": reason,
                "category": memory.category,
                "confidence": memory.confidence,
            },
        )
