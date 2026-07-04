# src/api/control/study_agent/graph/graph.py
"""LangGraph definition for study material generation.

Graph flow (happy path):

    entry_router → resolver → [llamaparse] → concept_checklist
        → study_agent ⇄ quality_check → END
QC retry loop:
    quality_check (fail) → study_agent (patch|insert|full_regen) → quality_check

Resume: ``entry_router`` uses ``resolve_resume_next_node`` to skip completed nodes.

See ``resume_router.route_after_study_agent`` and ``_route_after_quality_check``
for conditional edge logic.
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import StateGraph

from src.api.control.study_agent.graph.resume_router import (
    is_resume_state,
    last_completed_node_from_state,
    resolve_resume_next_node,
    route_after_study_agent,
)
from src.api.control.study_agent.nodes import (
    concept_checklist_node,
    llamaparse_node,
    quality_check_node,
    resolve_instruction_node,
    study_agent_node,
)
from src.api.control.study_agent.states.state import StudyMaterialGraphState

_compiled_graph = None


async def entry_router_node(
    state: StudyMaterialGraphState,
) -> dict[str, Any]:
    """No-op entry node; routing is decided by conditional edges."""
    del state
    return {}


def _route_from_entry(
    state: StudyMaterialGraphState,
) -> Literal[
    "resolver",
    "llamaparse",
    "concept_checklist",
    "study_agent",
    "quality_check",
    "__end__",
]:
    if not is_resume_state(state):
        return "resolver"
    next_node = resolve_resume_next_node(
        state,
        last_completed_node=last_completed_node_from_state(state),
    )
    if next_node == "__end__":
        return "__end__"
    return next_node  # type: ignore[return-value]


def _route_after_resolver(
    state: StudyMaterialGraphState,
) -> Literal["llamaparse", "concept_checklist", "__end__"]:
    if state.get("error"):
        return "__end__"
    if state.get("skip_llamaparse"):
        return "concept_checklist"
    if state.get("has_reference_material") and state.get("reference_file_path"):
        return "llamaparse"
    return "concept_checklist"


def _route_after_llamaparse(
    state: StudyMaterialGraphState,
) -> Literal["concept_checklist", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "concept_checklist"


def _route_after_concept_checklist(
    state: StudyMaterialGraphState,
) -> Literal["study_agent", "__end__"]:
    if state.get("terminal_llm_failure"):
        return "__end__"
    if state.get("error"):
        return "__end__"
    return "study_agent"


def _route_after_study_agent(
    state: StudyMaterialGraphState,
) -> Literal["quality_check", "__end__", "study_agent"]:
    return route_after_study_agent(state)


def _route_after_quality_check(
    state: StudyMaterialGraphState,
) -> Literal["study_agent", "quality_check", "__end__"]:
    """Route after quality check evaluation.

    - Pass  → END
    - Infra failure with attempts remaining → retry QC only (same content)
    - Deterministic or QC content fail + attempts remaining → study_agent (scoped retry)
    - Fail + permanently failed → END (accept as-is, expose QC result)
    """
    if state.get("qc_passed"):
        return "__end__"
    if state.get("qc_failed_permanently"):
        return "__end__"

    qc_result = state.get("qc_result") or {}
    if isinstance(qc_result, dict) and qc_result.get("qcInfraError"):
        return "quality_check"

    return "study_agent"


def build_study_material_graph() -> Any:
    """Build and compile the study material generation graph."""
    graph = StateGraph(StudyMaterialGraphState)

    graph.add_node("entry_router", entry_router_node)
    graph.add_node("resolver", resolve_instruction_node)
    graph.add_node("llamaparse", llamaparse_node)
    graph.add_node("concept_checklist", concept_checklist_node)
    graph.add_node("study_agent", study_agent_node)
    graph.add_node("quality_check", quality_check_node)

    graph.set_entry_point("entry_router")
    graph.add_conditional_edges("entry_router", _route_from_entry)
    graph.add_conditional_edges("resolver", _route_after_resolver)
    graph.add_conditional_edges("llamaparse", _route_after_llamaparse)
    graph.add_conditional_edges("concept_checklist", _route_after_concept_checklist)
    graph.add_conditional_edges("study_agent", _route_after_study_agent)
    graph.add_conditional_edges("quality_check", _route_after_quality_check)

    return graph.compile()


def get_study_material_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_study_material_graph()
    return _compiled_graph


def reset_study_material_graph() -> None:
    """Clear the compiled graph cache (for tests)."""
    global _compiled_graph
    _compiled_graph = None
