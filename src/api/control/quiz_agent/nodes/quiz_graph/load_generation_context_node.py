"""Load study material and node context for quiz generation."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.core.exceptions import QuizNotFoundException
from src.api.data.repositories import (  # noqa: E501
    QuizRepository,
    StudyMaterialRepository,
)
from src.api.utils.artifacts import new_artifact_run_id
from src.api.utils.quiz_utils.graph.node_helpers import graph_session
from src.api.utils.quiz_utils.study_material_link import (
    get_mentor_quiz_study_material_source,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _get_node_and_assert_space_access,
)


async def load_generation_context(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    session = graph_session(config)

    node = await _get_node_and_assert_space_access(
        session, state["node_id"], state["mentor_id"], owner_only=True
    )

    study_repo = StudyMaterialRepository(session)
    version = await get_mentor_quiz_study_material_source(
        study_repo,
        node_id=state["node_id"],
    )

    update: QuizGraphState = {
        **state,
        "space_id": cast(UUID, node.space_id),
        "node_title": cast(str, node.title),
        "study_material_version_id": cast(UUID, version.version_id),
        "study_material_content": cast(str, version.content),
        "artifact_run_id": state.get("artifact_run_id") or new_artifact_run_id(),
    }

    concept_plan = version.concept_plan
    if isinstance(concept_plan, dict):
        if concept_plan.get("domain"):
            update["domain"] = str(concept_plan["domain"])
        if concept_plan.get("topic_split"):
            update["topic_split"] = concept_plan["topic_split"]

    return update


async def load_existing_quiz_if_regenerate(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    if state.get("mode") != "regenerate":
        return state

    session = graph_session(config)
    repo = QuizRepository(session)

    quiz_id = state.get("quiz_id")
    quiz = await repo.get_quiz_by_id(quiz_id) if quiz_id is not None else None
    if quiz is None or quiz.node_id != state["node_id"]:
        raise QuizNotFoundException()

    questions = await repo.get_active_questions_by_quiz(quiz_id)  # type: ignore[arg-type]
    existing = [
        {
            "question_id": str(q.question_id),
            "question_text": q.question_text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_option": q.correct_option,
            "explanation": q.explanation,
            "order_index": q.order_index,
        }
        for q in questions
    ]

    return {**state, "existing_quiz_questions": existing}
