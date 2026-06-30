"""Entry point for running the quiz generation LangGraph."""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.control.quiz_agent.graph.quiz_graph.quiz_generation_graph import (
    get_quiz_generation_graph,
)
from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.core.exceptions import (
    QuizGenerationFailedException,
)
from src.api.utils.generation_progress import (
    GenerationPipeline,
    invoke_graph_with_progress,
)

logger = logging.getLogger(__name__)


async def _run_graph(
    session: AsyncSession,
    initial_state: QuizGraphState,
    *,
    run_id: UUID | None = None,
) -> QuizGraphState:
    graph = get_quiz_generation_graph()
    config = {"configurable": {"session": session}}
    result = cast(
        QuizGraphState,
        await invoke_graph_with_progress(
            graph,
            cast(dict[str, Any], initial_state),
            config,
            pipeline=GenerationPipeline.QUIZ,
            run_id=run_id,
        ),
    )

    if result.get("terminal_llm_failure"):
        logger.warning(
            "Quiz LLM generation failed (%s) for node '%s' — persisting draft with diagnostics.",
            result.get("llm_error_type"),
            result.get("node_title"),
        )
        return result

    if result.get("error") and not result.get("created_quiz_id"):
        detail = str(result["error"])
        logger.error("Quiz generation failed: %s", detail)
        raise QuizGenerationFailedException(detail)

    return result


async def run_quiz_generation(
    session: AsyncSession,
    initial_state: QuizGraphState,
    *,
    run_id: UUID | None = None,
) -> QuizGraphState:
    """Fresh quiz generation from service-shaped initial state."""
    return await _run_graph(
        session,
        initial_state,
        run_id=run_id,
    )


async def run_quiz_from_checkpoint(
    session: AsyncSession,
    initial_state: QuizGraphState,
    *,
    run_id: UUID | None = None,
) -> QuizGraphState:
    """Resume a failed quiz run from a hydrated checkpoint state."""
    return await _run_graph(
        session,
        initial_state,
        run_id=run_id,
    )
