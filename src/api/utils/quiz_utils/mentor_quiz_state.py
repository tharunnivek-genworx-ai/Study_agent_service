"""Server-side mentor quiz UI resolution helpers."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_DRAFT,
)


class _QuizLike(Protocol):
    quiz_id: UUID
    is_published: bool
    lifecycle_status: str
    title: str


def is_mentor_workspace_quiz(quiz: _QuizLike) -> bool:
    """Quizzes in the mentor working layer (draft or live), not history."""
    return quiz.lifecycle_status in (LIFECYCLE_DRAFT, LIFECYCLE_ACTIVE)


def resolve_mentor_quiz_id(
    quizzes: list[_QuizLike],
    preferred_quiz_id: UUID | None = None,
) -> UUID | None:
    """
    Pick the quiz a mentor should continue working on.

    Only workspace quizzes (draft or live) are eligible. Retired history rows
    in Previous versions or Removed state are never auto-promoted to the
    working draft.

    Priority:
      1. preferred_quiz_id when it is still a workspace quiz for the node
      2. the newest workspace draft newer than the live quiz (if any)
      3. the live published quiz (if any)
      4. the newest workspace draft
      5. None — show the generate-quiz form
    """
    workspace_quizzes = [quiz for quiz in quizzes if is_mentor_workspace_quiz(quiz)]
    if not workspace_quizzes:
        return None

    if preferred_quiz_id is not None:
        for quiz in workspace_quizzes:
            if quiz.quiz_id == preferred_quiz_id:
                return preferred_quiz_id

    # Note: quizzes is assumed to be ordered by created_at DESC (newest first).
    published_idx = None
    for idx, quiz in enumerate(quizzes):
        if quiz.is_published and quiz.lifecycle_status == LIFECYCLE_ACTIVE:
            published_idx = idx
            break

    if published_idx is not None:
        for quiz in quizzes[:published_idx]:
            if quiz.lifecycle_status == LIFECYCLE_DRAFT:
                return quiz.quiz_id
        return quizzes[published_idx].quiz_id

    for quiz in quizzes:
        if quiz.lifecycle_status == LIFECYCLE_DRAFT:
            return quiz.quiz_id

    return None


def mentor_quiz_draft_exists(quizzes: list[_QuizLike]) -> bool:
    """True when a workspace draft quiz exists for the node."""
    return any(quiz.lifecycle_status == LIFECYCLE_DRAFT for quiz in quizzes)


def find_other_live_quiz(
    quizzes: list[_QuizLike],
    *,
    current_quiz_id: UUID | None,
) -> _QuizLike | None:
    """Return the published quiz on this node that is not the mentor's current quiz."""
    for quiz in quizzes:
        if (
            quiz.is_published
            and quiz.lifecycle_status == LIFECYCLE_ACTIVE
            and (current_quiz_id is None or quiz.quiz_id != current_quiz_id)
        ):
            return quiz
    return None
