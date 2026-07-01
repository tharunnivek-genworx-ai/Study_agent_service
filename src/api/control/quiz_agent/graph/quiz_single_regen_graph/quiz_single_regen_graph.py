"""LangGraph definition for quiz single-question regeneration."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.api.control.quiz_agent.graph.quiz_single_regen_graph.resume_router import (
    is_resume_state,
    last_completed_node_from_state,
    resolve_resume_next_node,
)
from src.api.control.quiz_agent.nodes.quiz_single_regen_graph import (
    build_quiz_single_regen_prompt_node,
    deterministic_validate_question_patches,
    invoke_quiz_single_regen_llm,
    load_quiz_single_regen_context,
    parse_quiz_single_regen_output,
    persist_question_patches,
)
from src.api.control.quiz_agent.states.quiz_single_regen_graph.quiz_single_regen_state import (
    QuizSingleRegenGraphState,
)

_compiled_graph = None


async def entry_router_node(
    state: QuizSingleRegenGraphState,
) -> dict[str, Any]:
    """No-op entry node; routing is decided by conditional edges."""
    del state
    return {}


def _route_from_entry(
    state: QuizSingleRegenGraphState,
) -> Literal[
    "load_quiz_single_regen_context",
    "build_quiz_single_regen_prompt",
    "invoke_quiz_single_regen_llm",
    "parse_quiz_single_regen_output",
    "deterministic_validate_question_patches",
    "persist_question_patches",
    "__end__",
]:
    if not is_resume_state(state):
        return "load_quiz_single_regen_context"
    next_node = resolve_resume_next_node(
        state,
        last_completed_node=last_completed_node_from_state(state),
    )
    if next_node == "__end__":
        return "__end__"
    return next_node  # type: ignore[return-value]


def _route_after_invoke(
    state: QuizSingleRegenGraphState,
) -> Literal["parse_quiz_single_regen_output", "__end__"]:
    if state.get("terminal_llm_failure") or state.get("error"):
        return "__end__"
    return "parse_quiz_single_regen_output"


def _route_after_parse(
    state: QuizSingleRegenGraphState,
) -> Literal["deterministic_validate_question_patches", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "deterministic_validate_question_patches"


def _route_after_validate(
    state: QuizSingleRegenGraphState,
) -> Literal["persist_question_patches", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "persist_question_patches"


def build_quiz_single_regen_graph() -> Any:
    """Build and compile the quiz single-question regeneration graph."""
    graph = StateGraph(QuizSingleRegenGraphState)

    graph.add_node("entry_router", entry_router_node)
    graph.add_node(
        "load_quiz_single_regen_context",
        load_quiz_single_regen_context,
    )
    graph.add_node(
        "build_quiz_single_regen_prompt",
        build_quiz_single_regen_prompt_node,
    )
    graph.add_node(
        "invoke_quiz_single_regen_llm",
        invoke_quiz_single_regen_llm,
    )
    graph.add_node(
        "parse_quiz_single_regen_output",
        parse_quiz_single_regen_output,
    )
    graph.add_node(
        "deterministic_validate_question_patches",
        deterministic_validate_question_patches,
    )
    graph.add_node(
        "persist_question_patches",
        persist_question_patches,
    )

    graph.set_entry_point("entry_router")
    graph.add_conditional_edges("entry_router", _route_from_entry)
    graph.add_edge(
        "load_quiz_single_regen_context",
        "build_quiz_single_regen_prompt",
    )
    graph.add_edge(
        "build_quiz_single_regen_prompt",
        "invoke_quiz_single_regen_llm",
    )
    graph.add_conditional_edges("invoke_quiz_single_regen_llm", _route_after_invoke)
    graph.add_conditional_edges(
        "parse_quiz_single_regen_output",
        _route_after_parse,
    )
    graph.add_conditional_edges(
        "deterministic_validate_question_patches",
        _route_after_validate,
    )
    graph.add_edge("persist_question_patches", END)

    return graph.compile()


def get_quiz_single_regen_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_quiz_single_regen_graph()
    return _compiled_graph


def reset_quiz_single_regen_graph() -> None:
    """Clear the compiled graph cache (for tests)."""
    global _compiled_graph
    _compiled_graph = None
