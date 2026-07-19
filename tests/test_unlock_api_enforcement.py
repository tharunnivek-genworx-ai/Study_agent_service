"""Focused service-level enforcement tests for current versus archived quiz access."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.core.services.trainee_quiz_services.trainee_quiz_service import (
    TraineeQuizService,
)
from src.api.schemas.quiz_schemas import QuizAttemptStartRequest


def test_attempt_start_checks_prerequisite_before_quiz_discovery() -> None:
    node_id = uuid4()
    trainee_id = uuid4()
    service = TraineeQuizService(MagicMock())
    service.repo = MagicMock()
    locked = RuntimeError("prerequisite locked")

    with (
        patch(
            "src.api.core.services.trainee_quiz_services.trainee_quiz_service."
            "_get_node_and_assert_space_access",
            new=AsyncMock(return_value=SimpleNamespace(space_id=uuid4())),
        ),
        patch(
            "src.api.core.services.trainee_quiz_services.trainee_quiz_service."
            "_assert_space_access",
            new=AsyncMock(),
        ),
        patch(
            "src.api.core.services.trainee_quiz_services.trainee_quiz_service."
            "assert_trainee_node_unlocked",
            new=AsyncMock(side_effect=locked),
        ),
    ):
        with pytest.raises(RuntimeError, match="prerequisite locked"):
            asyncio.run(
                service.start_attempt(
                    node_id=node_id,
                    quiz_id=uuid4(),
                    request=QuizAttemptStartRequest(),
                    user_id=trainee_id,
                    role="trainee",
                )
            )

    service.repo.get_published_quiz_by_node.assert_not_called()


def test_archived_attempt_lookup_does_not_apply_current_prerequisite_gate() -> None:
    quiz_id = uuid4()
    quiz = MagicMock(
        quiz_id=quiz_id,
        is_published=False,
        lifecycle_status="archived",
    )
    attempt = MagicMock(quiz_id=quiz_id, trainee_id=uuid4())
    service = TraineeQuizService(MagicMock())
    service.repo = MagicMock()
    service.repo.get_quiz_by_id = AsyncMock(return_value=quiz)
    service.repo.list_attempts_by_quiz_and_trainee = AsyncMock(return_value=[attempt])

    with patch(
        "src.api.core.services.trainee_quiz_services.trainee_quiz_service."
        "assert_trainee_node_unlocked",
        new=AsyncMock(side_effect=AssertionError("archive path must stay exempt")),
    ):
        assert asyncio.run(service._get_quiz_for_attempt(attempt)) is quiz
