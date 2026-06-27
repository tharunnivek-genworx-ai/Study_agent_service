"""LangGraph definition for quiz draft generation (Graph 1).

The graph owns only the LLM orchestration and validation flow. Business-level
orchestration (auth, request shaping, response mapping) stays in the service
layer, which invokes the compiled graph with the AsyncSession threaded through
the run config::

    graph = get_quiz_generation_graph()
    final_state = await graph.ainvoke(
        initial_state,
        config={"configurable": {"session": session}},
    )
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.api.control.quiz_agent.nodes import (
    MAX_QC_ATTEMPTS,
    deterministic_validate_node,
    load_existing_quiz_if_regenerate,
    load_generation_context,
    parse_quiz_output,
    persist_quiz_draft,
    quality_check_node,
    quiz_generator_node,
)
from src.api.control.quiz_agent.states.quiz_state import QuizGraphState

_compiled_graph = None


def _route_after_load_context(
    state: QuizGraphState,
) -> Literal["load_existing_quiz_if_regenerate", "quiz_generator"]:
    if state.get("mode") == "regenerate":
        return "load_existing_quiz_if_regenerate"
    return "quiz_generator"


def _route_after_quiz_generator(
    state: QuizGraphState,
) -> Literal[
    "parse_quiz_output",
    "deterministic_validate",
    "persist_quiz_draft",
    "__end__",
]:
    if state.get("terminal_llm_failure"):
        return "persist_quiz_draft"
    if state.get("error"):
        return "__end__"
    if state.get("parsed_questions") is not None:
        return "deterministic_validate"
    return "parse_quiz_output"


def _route_after_parse(
    state: QuizGraphState,
) -> Literal["deterministic_validate", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "deterministic_validate"


def _route_after_deterministic_validate(
    state: QuizGraphState,
) -> Literal["quiz_generator", "quality_check", "persist_quiz_draft"]:
    if state.get("struct_validation_passed"):
        return "quality_check"
    if state.get("qc_failed_permanently"):
        return "persist_quiz_draft"
    return "quiz_generator"


def _route_after_quality_check(
    state: QuizGraphState,
) -> Literal["quiz_generator", "quality_check", "persist_quiz_draft"]:
    if state.get("qc_passed"):
        return "persist_quiz_draft"
    if state.get("qc_failed_permanently"):
        return "persist_quiz_draft"

    qc_result = state.get("qc_result") or {}
    qc_attempt = state.get("qc_attempt") or 0
    if (
        isinstance(qc_result, dict)
        and qc_result.get("qcInfraError")
        and qc_attempt < MAX_QC_ATTEMPTS
    ):
        return "quality_check"

    return "quiz_generator"


def build_quiz_generation_graph() -> Any:
    """Build and compile the quiz draft generation graph."""
    graph = StateGraph(QuizGraphState)

    graph.add_node("load_generation_context", load_generation_context)
    graph.add_node(
        "load_existing_quiz_if_regenerate",
        load_existing_quiz_if_regenerate,
    )
    graph.add_node("quiz_generator", quiz_generator_node)
    graph.add_node("parse_quiz_output", parse_quiz_output)
    graph.add_node(
        "deterministic_validate",
        deterministic_validate_node,
    )
    graph.add_node("quality_check", quality_check_node)
    graph.add_node("persist_quiz_draft", persist_quiz_draft)

    graph.set_entry_point("load_generation_context")
    graph.add_conditional_edges("load_generation_context", _route_after_load_context)
    graph.add_edge("load_existing_quiz_if_regenerate", "quiz_generator")
    graph.add_conditional_edges("quiz_generator", _route_after_quiz_generator)
    graph.add_conditional_edges("parse_quiz_output", _route_after_parse)
    graph.add_conditional_edges(
        "deterministic_validate",
        _route_after_deterministic_validate,
    )
    graph.add_conditional_edges("quality_check", _route_after_quality_check)
    graph.add_edge("persist_quiz_draft", END)

    return graph.compile()


def get_quiz_generation_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_quiz_generation_graph()
    return _compiled_graph
