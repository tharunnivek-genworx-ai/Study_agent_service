# src/api/control/study_agent/graph/graph.py
"""LangGraph definition for study material generation."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import StateGraph

from src.api.control.study_agent.nodes import (
    llamaparse_node,
    quality_check_node,
    resolve_instruction_node,
    study_agent_node,
)
from src.api.control.study_agent.states.state import StudyMaterialGraphState

_compiled_graph = None


def _route_after_resolver(
    state: StudyMaterialGraphState,
) -> Literal["llamaparse", "study_agent", "__end__"]:
    if state.get("error"):
        return "__end__"
    if state.get("skip_llamaparse"):
        return "study_agent"
    if state.get("has_reference_material") and state.get("reference_file_path"):
        return "llamaparse"
    return "study_agent"


def _route_after_llamaparse(
    state: StudyMaterialGraphState,
) -> Literal["study_agent", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "study_agent"


def _route_after_quality_check(
    state: StudyMaterialGraphState,
) -> Literal["study_agent", "__end__"]:
    """Route after quality check evaluation.

    - Pass  → END (content is good, present to mentor)
    - Fail + attempts remaining → study_agent (retry with QC feedback)
    - Fail + permanently failed → END (accept as-is, expose QC result)
    """
    if state.get("qc_passed"):
        return "__end__"
    if state.get("qc_failed_permanently"):
        return "__end__"
    # QC failed but retries remain — loop back to study_agent
    return "study_agent"


def build_study_material_graph() -> Any:
    """Build and compile the study material generation graph."""
    graph = StateGraph(StudyMaterialGraphState)

    graph.add_node("resolver", resolve_instruction_node)
    graph.add_node("llamaparse", llamaparse_node)
    graph.add_node("study_agent", study_agent_node)
    graph.add_node("quality_check", quality_check_node)

    graph.set_entry_point("resolver")
    graph.add_conditional_edges("resolver", _route_after_resolver)
    graph.add_conditional_edges("llamaparse", _route_after_llamaparse)
    graph.add_edge("study_agent", "quality_check")
    graph.add_conditional_edges("quality_check", _route_after_quality_check)

    return graph.compile()


def get_study_material_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_study_material_graph()
    return _compiled_graph
