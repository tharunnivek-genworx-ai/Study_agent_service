"""Unit tests for mid-attempt access to archived quizzes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.api.core.exceptions import QuizNotFoundException
from src.api.core.services.trainee_quiz_services.trainee_quiz_service import (
    TraineeQuizService,
)
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_HIDDEN,
)


def _make_service(*, quiz: MagicMock, attempts: list) -> TraineeQuizService:
    service = TraineeQuizService(MagicMock())
    service.repo = MagicMock()
    service.repo.get_quiz_by_id = AsyncMock(return_value=quiz)
    service.repo.list_attempts_by_quiz_and_trainee = AsyncMock(return_value=attempts)
    return service


class TestArchivedQuizMidAttemptAccess:
    def test_get_quiz_for_attempt_allows_archived_with_existing_attempt(self):
        quiz = MagicMock()
        quiz.is_published = False
        quiz.lifecycle_status = LIFECYCLE_ARCHIVED
        quiz.quiz_id = uuid4()
        attempt = MagicMock()
        attempt.quiz_id = quiz.quiz_id
        attempt.trainee_id = uuid4()

        service = _make_service(quiz=quiz, attempts=[attempt])
        loaded = asyncio.run(service._get_quiz_for_attempt(attempt))
        assert loaded is quiz

    def test_get_quiz_for_attempt_allows_hidden_with_existing_attempt(self):
        quiz = MagicMock()
        quiz.is_published = False
        quiz.lifecycle_status = LIFECYCLE_HIDDEN
        quiz.quiz_id = uuid4()
        attempt = MagicMock()
        attempt.quiz_id = quiz.quiz_id

        service = _make_service(quiz=quiz, attempts=[attempt])
        loaded = asyncio.run(service._get_quiz_for_attempt(attempt))
        assert loaded is quiz

    def test_get_quiz_for_attempt_rejects_archived_without_attempt(self):
        quiz = MagicMock()
        quiz.is_published = False
        quiz.lifecycle_status = LIFECYCLE_ARCHIVED
        quiz.quiz_id = uuid4()
        attempt = MagicMock()
        attempt.quiz_id = quiz.quiz_id

        service = _make_service(quiz=quiz, attempts=[])
        with pytest.raises(QuizNotFoundException):
            asyncio.run(service._get_quiz_for_attempt(attempt))

    def test_get_quiz_for_attempt_allows_active_published_quiz(self):
        quiz = MagicMock()
        quiz.is_published = True
        quiz.lifecycle_status = LIFECYCLE_ACTIVE
        attempt = MagicMock()

        service = _make_service(quiz=quiz, attempts=[])
        loaded = asyncio.run(service._get_quiz_for_attempt(attempt))
        assert loaded is quiz

    def test_resolve_quiz_for_trainee_access_allows_archived_with_attempt(self):
        node_id = uuid4()
        quiz_id = uuid4()
        trainee_id = uuid4()
        quiz = MagicMock()
        quiz.node_id = node_id
        quiz.is_published = False
        quiz.lifecycle_status = LIFECYCLE_ARCHIVED

        service = _make_service(quiz=quiz, attempts=[MagicMock()])
        loaded = asyncio.run(
            service._resolve_quiz_for_trainee_access(
                node_id=node_id,
                quiz_id=quiz_id,
                trainee_id=trainee_id,
            )
        )
        assert loaded is quiz
        service.repo.list_attempts_by_quiz_and_trainee.assert_awaited_once_with(
            quiz_id, trainee_id
        )

    def test_resolve_quiz_for_trainee_access_rejects_archived_without_attempt(self):
        node_id = uuid4()
        quiz_id = uuid4()
        quiz = MagicMock()
        quiz.node_id = node_id
        quiz.is_published = False
        quiz.lifecycle_status = LIFECYCLE_ARCHIVED

        service = _make_service(quiz=quiz, attempts=[])
        with pytest.raises(QuizNotFoundException):
            asyncio.run(
                service._resolve_quiz_for_trainee_access(
                    node_id=node_id,
                    quiz_id=quiz_id,
                    trainee_id=uuid4(),
                )
            )

    def test_resolve_quiz_for_trainee_access_rejects_wrong_node(self):
        quiz = MagicMock()
        quiz.node_id = uuid4()
        quiz.is_published = True
        quiz.lifecycle_status = LIFECYCLE_ACTIVE

        service = _make_service(quiz=quiz, attempts=[])
        with pytest.raises(QuizNotFoundException):
            asyncio.run(
                service._resolve_quiz_for_trainee_access(
                    node_id=uuid4(),
                    quiz_id=uuid4(),
                    trainee_id=uuid4(),
                )
            )
