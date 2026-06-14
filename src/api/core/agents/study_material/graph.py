"""LangGraph definition for study material generation."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.api.core.agents.study_material.nodes import (
    llamaparse_node,
    resolve_instruction_node,
    study_agent_node,
)
from src.api.core.agents.study_material.state import StudyMaterialGraphState

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


def build_study_material_graph() -> Any:
    """Build and compile the study material generation graph."""
    graph = StateGraph(StudyMaterialGraphState)

    graph.add_node("resolver", resolve_instruction_node)
    graph.add_node("llamaparse", llamaparse_node)
    graph.add_node("study_agent", study_agent_node)

    graph.set_entry_point("resolver")
    graph.add_conditional_edges("resolver", _route_after_resolver)
    graph.add_conditional_edges("llamaparse", _route_after_llamaparse)
    graph.add_edge("study_agent", END)

    return graph.compile()


def get_study_material_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_study_material_graph()
    return _compiled_graph
