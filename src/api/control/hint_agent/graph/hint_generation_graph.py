"""LangGraph definition for hint generation (Graph 2).

Run after a mentor accepts a quiz draft. The graph owns only the LLM
orchestration and validation flow; the service layer invokes the compiled
graph with the AsyncSession threaded through the run config::

    graph = get_hint_generation_graph()
    final_state = await graph.ainvoke(
        initial_state,
        config={"configurable": {"session": session}},
    )
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, StateGraph

from src.api.control.hint_agent.nodes import hint_nodes
from src.api.control.hint_agent.states.hint_state import HintGraphState

_compiled_graph = None


def _route_after_invoke(
    state: HintGraphState,
) -> Literal["parse_hint_output", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "parse_hint_output"


def _route_after_parse(
    state: HintGraphState,
) -> Literal["validate_hint_quality", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "validate_hint_quality"


def _route_after_validate(
    state: HintGraphState,
) -> Literal["persist_hints_to_questions", "__end__"]:
    if state.get("error"):
        return "__end__"
    return "persist_hints_to_questions"


def build_hint_generation_graph() -> Any:
    """Build and compile the hint generation graph."""
    graph = StateGraph(HintGraphState)

    graph.add_node("load_hint_context", hint_nodes.load_hint_context)
    graph.add_node("build_hint_prompt_payload", hint_nodes.build_hint_prompt_payload)
    graph.add_node("invoke_hint_llm", hint_nodes.invoke_hint_llm)
    graph.add_node("parse_hint_output", hint_nodes.parse_hint_output)
    graph.add_node("validate_hint_quality", hint_nodes.validate_hint_quality)
    graph.add_node("persist_hints_to_questions", hint_nodes.persist_hints_to_questions)

    graph.set_entry_point("load_hint_context")
    graph.add_edge("load_hint_context", "build_hint_prompt_payload")
    graph.add_edge("build_hint_prompt_payload", "invoke_hint_llm")
    graph.add_conditional_edges("invoke_hint_llm", _route_after_invoke)
    graph.add_conditional_edges("parse_hint_output", _route_after_parse)
    graph.add_conditional_edges("validate_hint_quality", _route_after_validate)
    graph.add_edge("persist_hints_to_questions", END)

    return graph.compile()


def get_hint_generation_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_hint_generation_graph()
    return _compiled_graph
