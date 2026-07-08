"""LangGraph runner that emits step progress for the frontend loading screen."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from src.api.core.exceptions import GenerationRunAborted
from src.api.schemas import GenerationPipeline
from src.api.utils.generation_progress.db_store import DbGenerationProgressStore


def node_succeeded(node_output: dict[str, Any] | None) -> bool:
    """Return True when a node completed without a hard pipeline error.

    Returns False for None updates — LangGraph emits None for nodes that
    return an empty dict (no state changes), so None is treated as a
    no-op that should not be checkpointed as a successful completion.
    """
    if not isinstance(node_output, dict):
        return False
    if node_output.get("error"):
        return False
    if node_output.get("terminal_llm_failure"):
        return False
    return True


def _json_safe_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-serializable copy of graph state for checkpoint storage."""

    def _default(obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    return cast(dict[str, Any], json.loads(json.dumps(state, default=_default)))


async def invoke_graph_with_progress(
    graph: Any,
    initial_state: dict[str, Any],
    config: dict[str, Any],
    *,
    pipeline: GenerationPipeline,
    run_id: UUID | None = None,
) -> dict[str, Any]:
    """Run a compiled LangGraph, updating progress and optional run checkpoints."""
    if run_id is None:
        result: dict[str, Any] = await graph.ainvoke(initial_state, config)
        return result

    session = config.get("configurable", {}).get("session")
    if session is None:
        raise ValueError(
            "config.configurable.session is required when run_id is provided."
        )
    from src.api.core.services.generation_run_service import GenerationRunService

    run_service = GenerationRunService(session)
    db_progress = DbGenerationProgressStore(session)

    running_state: dict[str, Any] = dict(initial_state)
    final_state: dict[str, Any] | None = None

    try:
        async for chunk in graph.astream(initial_state, config, stream_mode="updates"):
            if not await run_service.is_run_active(run_id):
                raise GenerationRunAborted()

            for node_name, node_update in chunk.items():
                # LangGraph emits None for nodes that return {} (no state
                # changes).  Guard the merge so we never unpack a NoneType.
                if isinstance(node_update, dict):
                    running_state = {**running_state, **node_update}
                final_state = running_state

                if node_succeeded(node_update):
                    await run_service.checkpoint_after_node(
                        run_id,
                        node_name=node_name,
                        state=_json_safe_state(running_state),
                    )
                elif node_update is not None:
                    await db_progress.on_node(run_id, pipeline, node_name)

    except GenerationRunAborted:
        raise
    except Exception as exc:
        next_retry = running_state.get("next_llm_retry_at")
        retry_at = next_retry if isinstance(next_retry, datetime) else None
        await run_service.fail_run(
            run_id,
            error_message=str(exc),
            error_type=type(exc).__name__,
            next_llm_retry_at=retry_at,
        )
        raise

    if final_state is None:
        final_state = await graph.ainvoke(initial_state, config)

    return final_state
