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

from src.api.control.hint_agent.graph.resume_router import (
    is_resume_state,
    last_completed_node_from_state,
    resolve_resume_next_node,
)
from src.api.control.hint_agent.nodes import hint_nodes
from src.api.control.hint_agent.states.hint_state import HintGraphState

_compiled_graph = None


async def entry_router_node(
    state: HintGraphState,
) -> dict[str, Any]:
    """No-op entry node; routing is decided by conditional edges."""
    del state
    return {}


def _route_from_entry(
    state: HintGraphState,
) -> Literal[
    "load_hint_context",
    "build_hint_prompt_payload",
    "invoke_hint_llm",
    "parse_hint_output",
    "validate_hint_quality",
    "persist_hints_to_questions",
    "persist_hint_failure_diagnostics",
    "__end__",
]:
    if not is_resume_state(state):
        return "load_hint_context"
    next_node = resolve_resume_next_node(
        state,
        last_completed_node=last_completed_node_from_state(state),
    )
    if next_node == "__end__":
        return "__end__"
    return next_node  # type: ignore[return-value]


def _route_after_invoke(
    state: HintGraphState,
) -> Literal["parse_hint_output", "persist_hint_failure_diagnostics", "__end__"]:
    if state.get("terminal_llm_failure"):
        return "persist_hint_failure_diagnostics"
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

    graph.add_node("entry_router", entry_router_node)
    graph.add_node("load_hint_context", hint_nodes.load_hint_context)
    graph.add_node("build_hint_prompt_payload", hint_nodes.build_hint_prompt_payload)
    graph.add_node("invoke_hint_llm", hint_nodes.invoke_hint_llm)
    graph.add_node("parse_hint_output", hint_nodes.parse_hint_output)
    graph.add_node("validate_hint_quality", hint_nodes.validate_hint_quality)
    graph.add_node("persist_hints_to_questions", hint_nodes.persist_hints_to_questions)
    graph.add_node(
        "persist_hint_failure_diagnostics",
        hint_nodes.persist_hint_failure_diagnostics,
    )

    graph.set_entry_point("entry_router")
    graph.add_conditional_edges("entry_router", _route_from_entry)
    graph.add_edge("load_hint_context", "build_hint_prompt_payload")
    graph.add_edge("build_hint_prompt_payload", "invoke_hint_llm")
    graph.add_conditional_edges("invoke_hint_llm", _route_after_invoke)
    graph.add_conditional_edges("parse_hint_output", _route_after_parse)
    graph.add_conditional_edges("validate_hint_quality", _route_after_validate)
    graph.add_edge("persist_hints_to_questions", END)
    graph.add_edge("persist_hint_failure_diagnostics", END)

    return graph.compile()


def get_hint_generation_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_hint_generation_graph()
    return _compiled_graph


def reset_hint_generation_graph() -> None:
    """Clear the compiled graph cache (for tests)."""
    global _compiled_graph
    _compiled_graph = None
