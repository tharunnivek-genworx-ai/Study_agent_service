"""Entry point for running the quiz single-question regeneration LangGraph."""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.control.quiz_agent.graph.quiz_single_regen_graph.quiz_single_regen_graph import (
    get_quiz_single_regen_graph,
)
from src.api.control.quiz_agent.states.quiz_single_regen_graph.quiz_single_regen_state import (
    QuizSingleRegenGraphState,
)
from src.api.core.exceptions import QuizGenerationFailedException
from src.api.utils.generation_progress import (
    GenerationPipeline,
    invoke_graph_with_progress,
)

logger = logging.getLogger(__name__)


async def _run_graph(
    session: AsyncSession,
    initial_state: QuizSingleRegenGraphState,
    *,
    run_id: UUID | None = None,
) -> QuizSingleRegenGraphState:
    graph = get_quiz_single_regen_graph()
    config = {"configurable": {"session": session}}
    result = cast(
        QuizSingleRegenGraphState,
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
            "Quiz single-question regen LLM failed (%s) for quiz '%s'.",
            result.get("llm_error_type"),
            result.get("quiz_id"),
        )
        return result

    if result.get("error"):
        detail = str(result["error"])
        logger.error("Quiz single-question regen failed: %s", detail)
        raise QuizGenerationFailedException(detail)

    return result


async def run_quiz_single_regen(
    session: AsyncSession,
    initial_state: QuizSingleRegenGraphState,
    *,
    run_id: UUID | None = None,
) -> QuizSingleRegenGraphState:
    """Fresh single-question regen from service-shaped initial state."""
    return await _run_graph(
        session,
        initial_state,
        run_id=run_id,
    )


async def run_quiz_single_regen_from_checkpoint(
    session: AsyncSession,
    initial_state: QuizSingleRegenGraphState,
    *,
    run_id: UUID | None = None,
) -> QuizSingleRegenGraphState:
    """Resume a failed single-question regen run from a hydrated checkpoint state."""
    return await _run_graph(
        session,
        initial_state,
        run_id=run_id,
    )
