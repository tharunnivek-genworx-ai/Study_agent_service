"""LangGraph definition for hint generation (Graph 2).

Run after a mentor accepts a quiz draft. The graph owns only the LLM
orchestration and validation flow; the service layer invokes the compiled
graph with the AsyncSession threaded through the run config::

    graph = get_hint_generation_graph()
    final_state = await graph.ainvoke(
        initial_state,
        config={"configurable": {"session": session}},
    )

Pipeline flow
-------------
1. **entry_router** — passthrough node whose only job is to branch on fresh vs
   resume entry (see ``resume_router``).
2. **load_hint_context** — load quiz questions, domain metadata, and access
   checks from the DB.
3. **build_hint_prompt_payload** — assemble system/user messages via the hint
   prompt builder.
4. **invoke_hint_llm** — call Groq with rotation; on hard LLM failure, set
   ``terminal_llm_failure`` for the diagnostics path.
5. **parse_hint_output** — parse the JSON array returned by the LLM.
6. **validate_hint_quality** — enforce hint rules, retry per-question on
   quality failures, and stage DB writes (uncommitted).
7. **persist_hints_to_questions** — commit hint writes and merge QC
   diagnostics onto the quiz.
8. **persist_hint_failure_diagnostics** — terminal path when the LLM call
   fails irrecoverably; records diagnostics without touching hints.

Node sequence (happy path)
--------------------------
::

    entry_router
        → load_hint_context
        → build_hint_prompt_payload
        → invoke_hint_llm
        → parse_hint_output
        → validate_hint_quality
        → persist_hints_to_questions
        → END

Routing
-------
- **Entry** (``_route_from_entry``): fresh runs start at ``load_hint_context``;
  resume runs jump to the node returned by ``resolve_resume_next_node`` (or
  ``__end__`` when the checkpoint is already complete).
- **After invoke** (``_route_after_invoke``): ``terminal_llm_failure`` →
  ``persist_hint_failure_diagnostics``; ``error`` → ``__end__``; else →
  ``parse_hint_output``.
- **After parse** (``_route_after_parse``): ``error`` → ``__end__``; else →
  ``validate_hint_quality``.
- **After validate** (``_route_after_validate``): ``error`` → ``__end__``;
  else → ``persist_hints_to_questions``.

The compiled graph is cached module-wide via ``get_hint_generation_graph``;
``reset_hint_generation_graph`` clears that cache for tests.
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
    """Choose the first executable node after the entry passthrough.

    Fresh invocations always begin at context load. Resume invocations defer
    to ``resolve_resume_next_node`` based on the checkpoint's last completed
    node and partial state already hydrated into ``state``.
    """
    if not is_resume_state(state):
        # Fresh run: start from DB context load.
        return "load_hint_context"
    next_node = resolve_resume_next_node(
        state,
        last_completed_node=last_completed_node_from_state(state),
    )
    if next_node == "__end__":
        # Checkpoint already finished; skip remaining nodes.
        return "__end__"
    return next_node  # type: ignore[return-value]


def _route_after_invoke(
    state: HintGraphState,
) -> Literal["parse_hint_output", "persist_hint_failure_diagnostics", "__end__"]:
    """Branch after the Groq hint-generation call.

    Terminal LLM failures (rate limits, exhausted retries) are persisted as
    diagnostics. Recoverable ``error`` values end the graph immediately so the
    runner can raise; successful calls proceed to JSON parsing.
    """
    if state.get("terminal_llm_failure"):
        # Hard LLM failure — record diagnostics, do not parse empty output.
        return "persist_hint_failure_diagnostics"
    if state.get("error"):
        # Soft error (e.g. missing prompt) — stop; runner raises.
        return "__end__"
    return "parse_hint_output"


def _route_after_parse(
    state: HintGraphState,
) -> Literal["validate_hint_quality", "__end__"]:
    """Branch after JSON parsing of the LLM hint array.

    Malformed or schema-invalid output sets ``error`` and ends the graph;
    otherwise validation (with per-question retries) runs next.
    """
    if state.get("error"):
        # Parse failure — runner will surface HintGenerationFailedException.
        return "__end__"
    return "validate_hint_quality"


def _route_after_validate(
    state: HintGraphState,
) -> Literal["persist_hints_to_questions", "__end__"]:
    """Branch after hint quality validation and staged DB writes.

    Validation may record per-question failures in diagnostics without setting
    ``error``; only fatal validation errors (e.g. duplicate question IDs) end
    the graph early. Successful validation always proceeds to commit.
    """
    if state.get("error"):
        # Fatal validation error — do not commit partial hints.
        return "__end__"
    return "persist_hints_to_questions"


def build_hint_generation_graph() -> Any:
    """Wire nodes, edges, and conditional routers into a compiled StateGraph.

    Registers all hint pipeline nodes, sets ``entry_router`` as the entry
    point, and attaches conditional edges at entry, post-invoke, post-parse,
    and post-validate. Linear edges connect the middle of the happy path;
    both terminal nodes (persist success and persist failure) connect to END.
    """
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
    """Return the singleton compiled hint generation graph.

    Lazily builds and caches the graph on first access so import-time side
    effects are avoided and tests can reset via ``reset_hint_generation_graph``.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_hint_generation_graph()
    return _compiled_graph


def reset_hint_generation_graph() -> None:
    """Clear the compiled graph cache (for tests)."""
    global _compiled_graph
    _compiled_graph = None
