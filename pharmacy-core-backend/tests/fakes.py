"""Test doubles — chiefly the fake LLM.

Why a fake at all
-----------------
Every BI node calls ``get_llm().with_structured_output(Schema).invoke(messages)``.
Left alone, running the test suite would make real OpenAI calls: slow, costly, and
non-deterministic, so no assertion about the graph could ever be stable.

``FakeLLM`` implements only the slice of ``BaseChatModel`` the nodes actually touch
and answers by *schema class*, because that is how a node identifies what it wants:
the planner asks for a ``PlannerOutput``, the analyzer for a ``BusinessAnalysis``.

Deliberately NOT a mini-LLM. It scripts responses and records calls; it does not
try to understand questions. Anything a fake could "decide" would be testing the
fake, not the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.documents import Document

from app.ai.schemas.business_analysis import BusinessAnalysis
from app.ai.memory.memory_policy import normalize_fact
from app.ai.schemas.memory import MemoryExtraction
from app.ai.schemas.business_query import BusinessQuery, Metric, PlannerOutput
from app.ai.schemas.reflection import ReflectionOutput

# A scripted response is either a ready-made object or a callable that receives the
# messages the node passed in and returns one. The callable form lets a test vary
# the answer per turn (e.g. reflector unsatisfied on the first pass, satisfied next).
Response = Any | Callable[[list], Any]


@dataclass
class LLMCall:
    """One recorded invocation, for assertions about what a node asked for."""

    schema: type
    messages: list


class FakeLLM:
    """Stands in for the provider client returned by ``app.ai.llm.get_llm``."""

    def __init__(
        self,
        responses: dict[type, Response] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.responses: dict[type, Response] = dict(responses or {})
        # When set, every invocation raises it — used by the LLM-failure tests.
        self.error = error
        self.calls: list[LLMCall] = []

    # -- the slice of BaseChatModel the nodes use ---------------------------

    def with_structured_output(self, schema: type, **_: object) -> "_StructuredFakeLLM":
        return _StructuredFakeLLM(self, schema)

    def bind_tools(self, tools: list, **_: object) -> "FakeLLM":
        raise NotImplementedError(
            "FakeLLM does not script tool-calling yet. The native tool-calling graph "
            "(business_tool_graph) is untested; add binding support when it is covered."
        )

    def invoke(self, messages: list, **_: object) -> Any:
        raise NotImplementedError(
            "FakeLLM only supports structured output. A node called .invoke() directly; "
            "script it explicitly if that call is intended."
        )

    # -- helpers for assertions ---------------------------------------------

    def calls_for(self, schema: type) -> list[LLMCall]:
        return [call for call in self.calls if call.schema is schema]

    def call_count(self, schema: type) -> int:
        return len(self.calls_for(schema))

    # -- internal ------------------------------------------------------------

    def _resolve(self, schema: type, messages: list) -> Any:
        self.calls.append(LLMCall(schema=schema, messages=messages))

        if self.error is not None:
            raise self.error

        if schema not in self.responses:
            raise AssertionError(
                f"FakeLLM has no scripted response for {schema.__name__}. "
                f"Scripted: {[s.__name__ for s in self.responses]}. "
                f"Add one to the fixture, or the node under test is asking for "
                f"something the test did not anticipate."
            )

        response = self.responses[schema]
        return response(messages) if callable(response) else response


@dataclass
class _StructuredFakeLLM:
    """What ``with_structured_output`` returns — invoke resolves via the parent."""

    parent: FakeLLM
    schema: type

    def invoke(self, messages: list, **_: object) -> Any:
        return self.parent._resolve(self.schema, messages)


# ---------------------------------------------------------------------------
# Default script
# ---------------------------------------------------------------------------


def default_responses(
    queries: list[BusinessQuery] | None = None,
) -> dict[type, Response]:
    """A working script for every BI node: plan → analyze → reflect → extract.

    Tests override only the entry they care about, so a planner test does not have
    to describe an analysis it never inspects. The default plan is a single overall
    sales query — the simplest thing the pipeline can be asked to do.
    """

    plan = queries if queries is not None else [BusinessQuery(metric=Metric.SALES)]

    return {
        PlannerOutput: PlannerOutput(queries=list(plan)),
        BusinessAnalysis: BusinessAnalysis(
            summary="Total sales are 30.00 across 2 orders.",
            key_insights=[],
            recommendations=[],
            confidence=0.9,
        ),
        # sufficient=True ends the reflection loop after one pass, which is the
        # normal path. Tests that exercise the loop override this.
        ReflectionOutput: ReflectionOutput(
            sufficient=True,
            missing_queries=[],
            reason="All requested data was retrieved.",
        ),
        MemoryExtraction: MemoryExtraction(memories=[]),
    }


# ---------------------------------------------------------------------------
# Fake memory store
# ---------------------------------------------------------------------------


@dataclass
class FakeMemoryRepository:
    """In-memory stand-in for the ChromaDB-backed ``MemoryRepository``.

    Reproduces the behaviour that matters: scope filtering on BOTH write and read.
    Scope isolation is the property under test, so the fake must enforce it exactly
    as the real store does rather than quietly returning everything.
    """

    documents: list[Document] = field(default_factory=list)

    def save_memory(self, memory, scope) -> None:
        self.documents.append(
            Document(
                page_content=memory.fact,
                metadata={
                    **scope.as_metadata(),
                    "category": memory.category,
                    "confidence": memory.confidence,
                    "normalized": normalize_fact(memory.fact),
                },
            )
        )

    def search_memories(self, query: str, scope, k: int = 5) -> list[Document]:
        # No embeddings in tests: return everything in this scope, capped at k.
        # Relevance ranking is Chroma's job and is not what these tests exercise.
        return self._in_scope(scope)[:k]

    def existing_normalized_facts(self, scope) -> set[str]:
        return {
            doc.metadata.get("normalized", "") for doc in self._in_scope(scope)
        }

    def _in_scope(self, scope) -> list[Document]:
        wanted = scope.as_filter()
        return [
            doc
            for doc in self.documents
            if all(doc.metadata.get(key) == value for key, value in wanted.items())
        ]
