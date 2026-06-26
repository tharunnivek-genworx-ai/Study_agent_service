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

from src.api.control.quiz_agent.nodes import quiz_nodes
from src.api.control.quiz_agent.states.quiz_state import QuizGraphState

_compiled_graph = None


def _route_after_load_context(
    state: QuizGraphState,
) -> Literal["load_existing_quiz_if_regenerate", "build_quiz_prompt_payload"]:
    if state.get("mode") == "regenerate":
        return "load_existing_quiz_if_regenerate"
    return "build_quiz_prompt_payload"


def _route_after_invoke(
    state: QuizGraphState,
) -> Literal["parse_quiz_output", "persist_quiz_draft", "__end__"]:
    if state.get("terminal_llm_failure"):
        return "persist_quiz_draft"
    if state.get("error"):
        return "__end__"
    return "parse_quiz_output"


def _route_after_parse(
    state: QuizGraphState,
) -> Literal["validate_quiz_structure", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "validate_quiz_structure"


def _route_after_validate(
    state: QuizGraphState,
) -> Literal["quality_check", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "quality_check"


def _route_after_quality_check(
    state: QuizGraphState,
) -> Literal["build_quiz_prompt_payload", "persist_quiz_draft"]:
    if state.get("qc_passed"):
        return "persist_quiz_draft"
    if state.get("qc_failed_permanently"):
        return "persist_quiz_draft"
    # Retry: loop back to rebuild the prompt payload with the QC feedback
    return "build_quiz_prompt_payload"


def build_quiz_generation_graph() -> Any:
    """Build and compile the quiz draft generation graph."""
    graph = StateGraph(QuizGraphState)

    graph.add_node("load_generation_context", quiz_nodes.load_generation_context)
    graph.add_node(
        "load_existing_quiz_if_regenerate",
        quiz_nodes.load_existing_quiz_if_regenerate,
    )
    graph.add_node("build_quiz_prompt_payload", quiz_nodes.build_quiz_prompt_payload)
    graph.add_node("invoke_quiz_llm", quiz_nodes.invoke_quiz_llm)
    graph.add_node("parse_quiz_output", quiz_nodes.parse_quiz_output)
    graph.add_node("validate_quiz_structure", quiz_nodes.validate_quiz_structure)
    graph.add_node("quality_check", quiz_nodes.quality_check_node)
    graph.add_node("persist_quiz_draft", quiz_nodes.persist_quiz_draft)

    graph.set_entry_point("load_generation_context")
    graph.add_conditional_edges("load_generation_context", _route_after_load_context)
    graph.add_edge("load_existing_quiz_if_regenerate", "build_quiz_prompt_payload")
    graph.add_edge("build_quiz_prompt_payload", "invoke_quiz_llm")
    graph.add_conditional_edges("invoke_quiz_llm", _route_after_invoke)
    graph.add_conditional_edges("parse_quiz_output", _route_after_parse)
    graph.add_conditional_edges("validate_quiz_structure", _route_after_validate)
    graph.add_conditional_edges("quality_check", _route_after_quality_check)
    graph.add_edge("persist_quiz_draft", END)

    return graph.compile()


def get_quiz_generation_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_quiz_generation_graph()
    return _compiled_graph
