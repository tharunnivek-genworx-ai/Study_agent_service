"""Load quiz and question context for single-question mentor rework.

Graph node (rework subgraph — first step)
-----------------------------------------
Extends ``load_generation_context`` then loads the target draft quiz, validates
``question_ids`` against active questions, and sets ``all_questions`` for the
rework prompt.

Inputs: ``quiz_id``, ``question_ids``, ``mentor_id``, ``node_id``.
Outputs: ``all_questions``, ``difficulty_profile``, plus context fields from
``load_generation_context``.

Raises if quiz is missing, published, or question IDs are not found.
"""

from __future__ import annotations

from typing import Any, cast

from langchain_core.runnables import RunnableConfig

from src.api.control.quiz_agent.nodes.quiz_graph.load_generation_context_node import (
    load_generation_context,
)
from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.core.exceptions import (
    QuizAlreadyPublishedException,
    QuizNotFoundException,
    QuizQuestionNotFoundException,
)
from src.api.data.repositories import QuizRepository
from src.api.utils.quiz_utils.graph.node_helpers import graph_session


def _question_to_dict(question: Any) -> dict[str, Any]:
    """Serialize a QuizQuestion ORM row to the dict shape used in graph state."""
    return {
        "question_id": str(question.question_id),
        "question_text": question.question_text,
        "option_a": question.option_a,
        "option_b": question.option_b,
        "option_c": question.option_c,
        "option_d": question.option_d,
        "correct_option": question.correct_option,
        "explanation": question.explanation,
        "order_index": question.order_index,
    }


async def load_quiz_single_regen_context(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    """Load study material plus full quiz context for mentor single-question rework."""
    context_update = await load_generation_context(
        cast(Any, state),
        config,
    )
    merged_state: QuizGraphState = cast(QuizGraphState, {**state, **context_update})

    quiz_id = merged_state.get("quiz_id")
    if not quiz_id:
        raise QuizNotFoundException()

    session = graph_session(config)
    repo = QuizRepository(session)
    quiz = await repo.get_quiz_by_id(quiz_id)
    if quiz is None or quiz.node_id != merged_state["node_id"]:
        raise QuizNotFoundException()
    if quiz.is_published:
        raise QuizAlreadyPublishedException()

    active_questions = await repo.get_active_questions_by_quiz(quiz_id)
    active_by_id = {
        str(question.question_id): question for question in active_questions
    }
    target_ids = [str(question_id) for question_id in merged_state["question_ids"]]
    missing = [
        question_id for question_id in target_ids if question_id not in active_by_id
    ]
    if missing:
        raise QuizQuestionNotFoundException()

    all_questions = [_question_to_dict(question) for question in active_questions]
    return {
        **merged_state,
        "all_questions": all_questions,
        "difficulty_profile": cast(str, quiz.difficulty) or "medium",
    }
