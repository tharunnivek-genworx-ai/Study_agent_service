"""LangGraph runner that emits step progress for the frontend loading screen."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from src.api.schemas.generation_progress_schema import GenerationPipeline
from src.api.utils.generation_progress.db_store import DbGenerationProgressStore
from src.api.utils.generation_progress.store import get_generation_progress_store


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
    progress_session_id: str | None,
    pipeline: GenerationPipeline,
    run_id: UUID | None = None,
) -> dict[str, Any]:
    """Run a compiled LangGraph, updating progress and optional run checkpoints."""
    use_run_checkpoints = run_id is not None
    use_progress_stream = progress_session_id is not None or use_run_checkpoints

    if not use_progress_stream:
        result: dict[str, Any] = await graph.ainvoke(initial_state, config)
        return result

    session = config.get("configurable", {}).get("session")
    run_service: Any | None = None
    db_progress: DbGenerationProgressStore | None = None
    if use_run_checkpoints:
        if session is None:
            raise ValueError(
                "config.configurable.session is required when run_id is provided."
            )
        from src.api.core.services.generation_run_service import GenerationRunService

        run_service = GenerationRunService(session)
        db_progress = DbGenerationProgressStore(session)

    memory_store = get_generation_progress_store()
    use_legacy_memory = progress_session_id is not None and (
        run_id is None or progress_session_id != str(run_id)
    )

    running_state: dict[str, Any] = dict(initial_state)
    final_state: dict[str, Any] | None = None

    try:
        async for chunk in graph.astream(initial_state, config, stream_mode="updates"):
            for node_name, node_update in chunk.items():
                # LangGraph emits None for nodes that return {} (no state
                # changes).  Guard the merge so we never unpack a NoneType.
                if isinstance(node_update, dict):
                    running_state = {**running_state, **node_update}
                final_state = running_state

                if use_legacy_memory:
                    memory_store.on_node(progress_session_id, pipeline, node_name)

                if (
                    use_run_checkpoints
                    and run_service is not None
                    and run_id is not None
                ):
                    if node_succeeded(node_update):
                        await run_service.checkpoint_after_node(
                            run_id,
                            node_name=node_name,
                            state=_json_safe_state(running_state),
                        )
                    elif node_update is not None and db_progress is not None:
                        await db_progress.on_node(run_id, pipeline, node_name)

    except Exception as exc:
        if use_run_checkpoints and run_service is not None and run_id is not None:
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
