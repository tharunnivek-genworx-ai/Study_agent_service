"""Entry point for running the quiz generation LangGraph.

Pipeline position
-----------------
Called by the quiz service layer (not HTTP handlers directly). Wraps
``get_quiz_generation_graph()`` with ``invoke_graph_with_progress`` for
checkpointing, artifact logging, and run-id tracking.

Public entry points
-------------------
- ``run_quiz_generation`` / ``run_quiz_from_checkpoint`` — full quiz draft flow.
- ``run_quiz_single_regen`` / ``run_quiz_single_regen_from_checkpoint`` —
  mentor single-question rework (forces ``mode="improve"``).

Inputs
------
``AsyncSession`` plus a service-shaped ``QuizGraphState``. Config passes
``session``, optional ``run_id``, and ``GenerationPipeline.QUIZ``.

Outputs
-------
Final ``QuizGraphState`` with ``created_quiz_id`` (generate path) or patched
question IDs (rework path). Raises ``QuizGenerationFailedException`` on
non-terminal errors without a persisted quiz.
"""

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
    """Shared runner for fresh and checkpoint-resumed full quiz generation.

    Terminal LLM failures return state for draft persistence with diagnostics.
    Other errors without ``created_quiz_id`` raise ``QuizGenerationFailedException``.
    """
    graph = get_quiz_generation_graph()
    config = {
        "configurable": {
            "session": session,
            "run_id": str(run_id) if run_id is not None else None,
            "pipeline": GenerationPipeline.QUIZ.value,
        }
    }
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
    """Fresh quiz generation from service-shaped initial state.

    Expects ``mode`` of ``"generate"`` or ``"regenerate"`` with required IDs
    and counts already set by the caller.
    """
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
    """Resume a failed quiz run from a hydrated checkpoint state.

    ``initial_state`` must include ``_is_resume`` and ``_last_completed_node``
    (typically via ``hydrate_checkpoint_state``).
    """
    return await _run_graph(
        session,
        initial_state,
        run_id=run_id,
    )


async def _run_question_rework_graph(
    session: AsyncSession,
    initial_state: QuizGraphState,
    *,
    run_id: UUID | None = None,
) -> QuizGraphState:
    """Shared runner for single-question mentor rework (improve mode).

    Forces ``mode="improve"`` so ``entry_router`` selects the rework subgraph.
    Terminal LLM failures return state; other errors raise.
    """
    graph = get_quiz_generation_graph()
    state_with_mode: dict[str, Any] = {**initial_state, "mode": "improve"}
    config = {
        "configurable": {
            "session": session,
            "run_id": str(run_id) if run_id is not None else None,
            "pipeline": GenerationPipeline.QUIZ.value,
        }
    }
    result = cast(
        QuizGraphState,
        await invoke_graph_with_progress(
            graph,
            state_with_mode,
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
    initial_state: QuizGraphState,
    *,
    run_id: UUID | None = None,
) -> QuizGraphState:
    """Fresh single-question regen from service-shaped initial state.

    Requires ``quiz_id``, ``question_ids``, and ``mentor_feedback`` in state.
    """
    return await _run_question_rework_graph(
        session,
        initial_state,
        run_id=run_id,
    )


async def run_quiz_single_regen_from_checkpoint(
    session: AsyncSession,
    initial_state: QuizGraphState,
    *,
    run_id: UUID | None = None,
) -> QuizGraphState:
    """Resume a failed single-question regen run from a hydrated checkpoint state."""
    return await _run_question_rework_graph(
        session,
        initial_state,
        run_id=run_id,
    )
