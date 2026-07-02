"""Persist validated question patches from single-question mentor rework."""

from __future__ import annotations

from typing import Any, cast

from langchain_core.runnables import RunnableConfig

from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.data.repositories import QuizRepository
from src.api.utils.quiz_utils.graph.node_helpers import (
    graph_session,
    log_quiz_artifact,
)


async def persist_question_patches(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    session = graph_session(config)
    repo = QuizRepository(session)
    patches = state.get("validated_patches") or []
    if not patches:
        return {**state, "error": "No validated question patches to persist."}

    quiz_id = state.get("quiz_id")
    if not quiz_id:
        return {**state, "error": "Missing quiz_id for persisting patches."}

    patched_ids = await repo.patch_questions_from_ai(
        quiz_id,
        patches,
        commit=False,
    )
    if not patched_ids:
        return {**state, "error": "Failed to persist any question patches."}

    log_quiz_artifact(
        cast(Any, state),
        "quiz_single_regen_result",
        {
            "quiz_id": str(state["quiz_id"]),
            "patched_question_ids": patched_ids,
            "hints_stale_question_ids": state.get("hints_stale_question_ids"),
        },
    )
    return {
        **state,
        "hints_stale_question_ids": patched_ids,
    }
