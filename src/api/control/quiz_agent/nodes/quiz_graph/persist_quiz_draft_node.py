"""Persist validated quiz questions as a draft in the database."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.data.repositories import QuizRepository
from src.api.utils.quiz_utils.artifacts.quiz_artifacts import log_quiz_draft_snapshot
from src.api.utils.quiz_utils.graph.node_helpers import (
    graph_session,
    resolve_qc_result_for_persist,
)


async def persist_quiz_draft(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    session = graph_session(config)
    repo = QuizRepository(session)
    validated = state.get("validated_questions") or []

    qc_failed_permanently, qc_result = resolve_qc_result_for_persist(state)
    next_llm_retry_at = state.get("next_llm_retry_at")
    title = state.get("quiz_title") or "Quiz"
    difficulty = state["difficulty"]

    replace_quiz_id = state.get("quiz_id")
    if replace_quiz_id is not None:
        quiz_id = await repo.replace_quiz_draft_with_questions(
            quiz_id=replace_quiz_id,
            node_id=state["node_id"],
            title=title,
            difficulty=difficulty,
            questions=validated,
            qc_failed_permanently=qc_failed_permanently,
            qc_result=qc_result,
            study_material_version_id=state.get("study_material_version_id"),
            next_llm_retry_at=next_llm_retry_at,
        )
    else:
        quiz_id = await repo.create_quiz_draft_with_questions(
            node_id=state["node_id"],
            space_id=state["space_id"],  # type: ignore[arg-type]
            study_material_version_id=state.get("study_material_version_id"),  # type: ignore[arg-type]
            title=title,
            difficulty=difficulty,
            created_by=state["mentor_id"],
            questions=validated,
            qc_failed_permanently=qc_failed_permanently,
            qc_result=qc_result,
            next_llm_retry_at=next_llm_retry_at,
        )

    log_quiz_draft_snapshot(
        topic_title=state.get("node_title") or str(state.get("node_id")),
        quiz_id=str(quiz_id),
        payload={
            "created_quiz_id": str(quiz_id),
            "questions": validated,
            "qc_result": qc_result,
            "artifact_run_id": state.get("artifact_run_id"),
            "qc_failed_permanently": qc_failed_permanently,
        },
    )

    return {**state, "created_quiz_id": quiz_id}
