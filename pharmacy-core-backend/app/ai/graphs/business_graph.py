"""Business Intelligence Agent graph."""

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from app.ai.nodes.business_analyzer import (
    business_analyzer,
)
from app.ai.nodes.business_fetcher import (
    business_fetcher,
)
from app.ai.nodes.business_finalizer import (
    business_finalizer,
)
from app.ai.nodes.business_planner import (
    business_planner,
)
from app.ai.nodes.business_reflector import (
    business_reflector,
)
from app.ai.nodes.memory_extractor import (
    memory_extractor,
)
from app.ai.nodes.memory_persistor import (
    memory_persistor,
)
from app.ai.nodes.memory_retriever import (
    memory_retriever,
)
from app.ai.schemas.memory import MemoryFact
from app.ai.state.business_state import (
    BusinessState,
)

MAX_REFLECTIONS = 2

# The `memories` field on BusinessState holds MemoryFact (Pydantic) objects,
# and MemorySaver checkpoints that state via msgpack. Without registering the
# type, LangGraph warns on every load that it will BLOCK deserializing this
# unregistered type in a future version. Explicitly allow-listing MemoryFact
# here keeps checkpointing working exactly as before, with no behaviour change.
_CHECKPOINT_SERDE = JsonPlusSerializer(
    allowed_msgpack_modules=[MemoryFact],
)


def should_retry(
    state: BusinessState,
) -> str:
    """
    Decide whether another reflection cycle is required.
    """

    if (
        state["retry"]
        and state["reflection_count"] < MAX_REFLECTIONS
    ):
        return "retry"

    return "finish"


@lru_cache(maxsize=1)
def get_business_graph():
    """
    Build and compile the Business Intelligence Agent graph.
    """

    graph = StateGraph(BusinessState)

    # -----------------------------------------------------
    # Nodes
    # -----------------------------------------------------

    graph.add_node(
        "memory_retriever",
        memory_retriever,
    )

    graph.add_node(
        "planner",
        business_planner,
    )

    graph.add_node(
        "fetcher",
        business_fetcher,
    )

    graph.add_node(
        "analyzer",
        business_analyzer,
    )

    graph.add_node(
        "reflector",
        business_reflector,
    )

    graph.add_node(
        "finalizer",
        business_finalizer,
    )

    graph.add_node(
        "memory_extractor",
        memory_extractor,
    )

    graph.add_node(
        "memory_persistor",
        memory_persistor,
    )

    # -----------------------------------------------------
    # Main Flow
    # -----------------------------------------------------

    graph.add_edge(
        START,
        "memory_retriever",
    )

    graph.add_edge(
        "memory_retriever",
        "planner",
    )

    graph.add_edge(
        "planner",
        "fetcher",
    )

    graph.add_edge(
        "fetcher",
        "analyzer",
    )

    graph.add_edge(
        "analyzer",
        "reflector",
    )

    # -----------------------------------------------------
    # Reflection Loop
    # -----------------------------------------------------

    graph.add_conditional_edges(
        "reflector",
        should_retry,
        {
            "retry": "fetcher",
            "finish": "finalizer",
        },
    )

    # -----------------------------------------------------
    # Long-Term Memory
    # -----------------------------------------------------

    graph.add_edge(
        "finalizer",
        "memory_extractor",
    )

    graph.add_edge(
        "memory_extractor",
        "memory_persistor",
    )

    graph.add_edge(
        "memory_persistor",
        END,
    )

    return graph.compile(
        checkpointer=MemorySaver(serde=_CHECKPOINT_SERDE),
    )