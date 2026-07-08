"""Entry point for running the hint generation LangGraph."""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.control.hint_agent.graph.hint_generation_graph import (
    get_hint_generation_graph,
)
from src.api.control.hint_agent.states.hint_state import HintGraphState
from src.api.core.exceptions import (
    HintGenerationFailedException,
)
from src.api.utils.generation_progress import (
    GenerationPipeline,
    invoke_graph_with_progress,
)

logger = logging.getLogger(__name__)


async def _run_graph(
    session: AsyncSession,
    initial_state: HintGraphState,
    *,
    run_id: UUID | None = None,
) -> HintGraphState:
    graph = get_hint_generation_graph()
    config = {
        "configurable": {
            "session": session,
            "run_id": str(run_id) if run_id is not None else None,
            "pipeline": GenerationPipeline.HINT.value,
        }
    }
    result = cast(
        HintGraphState,
        await invoke_graph_with_progress(
            graph,
            cast(dict[str, Any], initial_state),
            config,
            pipeline=GenerationPipeline.HINT,
            run_id=run_id,
        ),
    )

    if result.get("terminal_llm_failure"):
        logger.warning(
            "Hint LLM generation failed (%s) for quiz '%s' — persisting diagnostics.",
            result.get("llm_error_type"),
            result.get("quiz_id"),
        )
        return result

    if result.get("error"):
        detail = str(result["error"])
        logger.error("Hint generation failed: %s", detail)
        raise HintGenerationFailedException(detail)

    return result


async def run_hint_generation(
    session: AsyncSession,
    initial_state: HintGraphState,
    *,
    run_id: UUID | None = None,
) -> HintGraphState:
    """Fresh hint generation from service-shaped initial state."""
    return await _run_graph(
        session,
        initial_state,
        run_id=run_id,
    )


async def run_hint_from_checkpoint(
    session: AsyncSession,
    initial_state: HintGraphState,
    *,
    run_id: UUID | None = None,
) -> HintGraphState:
    """Resume a failed hint run from a hydrated checkpoint state."""
    return await _run_graph(
        session,
        initial_state,
        run_id=run_id,
    )
