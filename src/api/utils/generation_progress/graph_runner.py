"""LangGraph runner that emits step progress for the frontend loading screen."""

from __future__ import annotations

from typing import Any

from src.api.schemas.generation_progress_schema import GenerationPipeline
from src.api.utils.generation_progress.store import get_generation_progress_store


async def invoke_graph_with_progress(
    graph: Any,
    initial_state: dict[str, Any],
    config: dict[str, Any],
    *,
    progress_session_id: str | None,
    pipeline: GenerationPipeline,
) -> dict[str, Any]:
    """Run a compiled LangGraph, updating the progress store after each node."""
    if not progress_session_id:
        result: dict[str, Any] = await graph.ainvoke(initial_state, config)
        return result

    store = get_generation_progress_store()
    final_state: dict[str, Any] | None = None

    async for chunk in graph.astream(initial_state, config, stream_mode="updates"):
        for node_name, node_update in chunk.items():
            store.on_node(progress_session_id, pipeline, node_name)
            if final_state is None:
                final_state = {**initial_state, **node_update}
            else:
                final_state = {**final_state, **node_update}

    if final_state is None:
        final_state = await graph.ainvoke(initial_state, config)

    return final_state
