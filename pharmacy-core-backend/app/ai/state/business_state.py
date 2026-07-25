"""Shared state for the Business Intelligence Agent."""

from typing import TypedDict


class BusinessState(TypedDict, total=False):
    """
    Shared state passed between all Business Intelligence nodes.
    """

    # ----------------------------
    # User Input
    # ----------------------------
    question: str

    # ----------------------------
    # Planner
    # ----------------------------
    plan: list[str]

    # ----------------------------
    # Data collected from tools
    # ----------------------------
    business_metrics: dict

    # ----------------------------
    # AI Analysis
    # ----------------------------
    answer: str
    confidence: float

    # ----------------------------
    # Reflection
    # ----------------------------
    reflection: str
    retry: bool

    # ----------------------------
    # Errors
    # ----------------------------
    errors: list[str]

    # ----------------------------
    # Future (Observability)
    # ----------------------------
    execution_time_ms: int
    agent_version: str