"""Server-side mentor quiz UI resolution helpers."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class _QuizLike(Protocol):
    quiz_id: UUID
    is_published: bool


def resolve_mentor_quiz_id(
    quizzes: list[_QuizLike],
    preferred_quiz_id: UUID | None = None,
) -> UUID | None:
    """
    Pick the quiz a mentor should continue working on.

    Priority:
      1. preferred_quiz_id when it still exists for the node
      2. the newest unpublished draft (caller should pass quizzes ordered created_at DESC)
      3. the published quiz (if any)
      4. the newest quiz overall
    """
    if not quizzes:
        return None
    if preferred_quiz_id is not None:
        for quiz in quizzes:
            if quiz.quiz_id == preferred_quiz_id:
                return preferred_quiz_id
    for quiz in quizzes:
        if not quiz.is_published:
            return quiz.quiz_id
    for quiz in quizzes:
        if quiz.is_published:
            return quiz.quiz_id
    return quizzes[0].quiz_id


def mentor_quiz_draft_exists(quizzes: list[_QuizLike]) -> bool:
    """True when at least one unpublished quiz draft exists for the node."""
    return any(not quiz.is_published for quiz in quizzes)
