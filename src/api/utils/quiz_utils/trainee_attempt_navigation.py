"""Resume and per-question navigation rules for trainee quiz attempts."""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from src.api.data.models.postgres.e_learning_content.quiz_question_responses import (
    QuizQuestionResponse,
)
from src.api.data.models.postgres.e_learning_content.quiz_questions import QuizQuestion

QuestionNavStatus = Literal["notVisited", "visited", "answered", "skipped"]


def is_question_skipped_at_submit(
    question: QuizQuestion,
    response: QuizQuestionResponse | None,
) -> bool:
    """True when the trainee submitted without ever answering this active question."""
    if not question.is_active:
        return False
    if response is None:
        return True
    return not response.was_locked and response.selected_option is None


def count_skipped_at_submit(
    questions: list[QuizQuestion],
    responses_map: dict[UUID, QuizQuestionResponse],
) -> int:
    active = _active_questions(questions)
    return sum(
        1
        for question in active
        if is_question_skipped_at_submit(
            question, responses_map.get(question.question_id)
        )
    )


def _active_questions(questions: list[QuizQuestion]) -> list[QuizQuestion]:
    return [q for q in questions if q.is_active]


def compute_resume_question_id(
    questions: list[QuizQuestion],
    responses_map: dict[UUID, QuizQuestionResponse],
) -> UUID | None:
    """
    Resume position for an in-progress attempt:
      - Correctly answered (locked) questions are passed over.
      - Wrong or unanswered questions resume on the first such question in order.
      - Unanswered questions resume at the first gap in order.
    """
    active = _active_questions(questions)
    if not active:
        return None

    for question in active:
        response = responses_map.get(question.question_id)
        if response is None:
            return cast(UUID, question.question_id)
        if response.was_locked:
            continue
        return cast(UUID, question.question_id)

    return cast(UUID, active[-1].question_id)


def compute_nav_status(
    response: QuizQuestionResponse | None,
    *,
    attempt_submitted: bool = False,
    skipped_at_submit: bool = False,
) -> QuestionNavStatus:
    if response is None:
        return "skipped" if attempt_submitted and skipped_at_submit else "notVisited"
    if response.was_locked:
        return "answered"
    if response.was_skipped:
        return "skipped"
    if attempt_submitted and skipped_at_submit:
        return "skipped"
    if (
        response.is_visited
        or response.selected_option is not None
        or response.hint_level_reached > 0
        or response.is_correct is False
    ):
        return "visited"
    return "notVisited"


def can_answer_question(
    *,
    is_active: bool,
    attempt_submitted: bool,
    was_locked: bool,
) -> bool:
    return is_active and not attempt_submitted and not was_locked


def can_skip_question(
    *,
    is_active: bool,
    attempt_submitted: bool,
    was_locked: bool,
) -> bool:
    return is_active and not attempt_submitted and not was_locked
