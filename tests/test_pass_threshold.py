import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.api.core.services.quiz_services.quiz_service import QuizService
from src.api.schemas.quiz_schemas.quiz_schema import (
    QuizPassThresholdUpdateRequest,
    QuizPublishRequest,
)
from src.api.utils.trainee_progress_utils.completion import (
    score_meets_pass_threshold,
)


@pytest.mark.parametrize("threshold", [1, 70, 85, 100])
def test_pass_threshold_request_accepts_boundaries(threshold: int) -> None:
    request = QuizPassThresholdUpdateRequest(pass_threshold_percent=threshold)
    assert request.pass_threshold_percent == threshold


@pytest.mark.parametrize("threshold", [0, 101, 70.5, "70"])
def test_pass_threshold_request_rejects_invalid_values(threshold: object) -> None:
    with pytest.raises(ValidationError):
        QuizPassThresholdUpdateRequest(pass_threshold_percent=threshold)


def test_publish_threshold_omitted_preserves_existing() -> None:
    """Omitted publish body must not clobber a mentor-configured threshold."""
    assert QuizPublishRequest().pass_threshold_percent is None


def test_publish_threshold_accepts_explicit_value() -> None:
    assert QuizPublishRequest(pass_threshold_percent=85).pass_threshold_percent == 85


def test_score_at_threshold_passes_and_below_fails() -> None:
    assert score_meets_pass_threshold(0.85, 85)
    assert not score_meets_pass_threshold(0.8499, 85)
    assert not score_meets_pass_threshold(1.0, None)


@pytest.mark.parametrize("is_live, expected_recompute_count", [(True, 1), (False, 0)])
def test_threshold_patch_recomputes_only_live_quiz(
    is_live: bool, expected_recompute_count: int
) -> None:
    node_id = uuid4()
    quiz_id = uuid4()
    space_id = uuid4()
    session = MagicMock()
    session.commit = AsyncMock()
    service = QuizService(session)
    service._build_quiz_out = AsyncMock(return_value=MagicMock())
    quiz = SimpleNamespace(
        quiz_id=quiz_id,
        node_id=node_id,
        space_id=space_id,
        is_published=is_live,
        lifecycle_status="active" if is_live else "draft",
    )
    repo = MagicMock()
    repo.get_quiz_by_id_for_update = AsyncMock(return_value=quiz)
    repo.update_pass_threshold = AsyncMock()

    with (
        patch(
            "src.api.core.services.quiz_services.quiz_service."
            "_get_node_and_assert_space_access",
            new=AsyncMock(),
        ),
        patch(
            "src.api.core.services.quiz_services.quiz_service.QuizRepository",
            return_value=repo,
        ),
        patch(
            "src.api.core.services.quiz_services.quiz_service."
            "recompute_node_quiz_passed_for_threshold",
            new=AsyncMock(),
        ) as recompute,
    ):
        asyncio.run(
            service.update_pass_threshold(
                node_id=node_id,
                quiz_id=quiz_id,
                request=QuizPassThresholdUpdateRequest(pass_threshold_percent=85),
                user_id=uuid4(),
                role="mentor",
            )
        )

    repo.update_pass_threshold.assert_awaited_once_with(quiz, 85)
    assert recompute.await_count == expected_recompute_count
    if is_live:
        recompute.assert_awaited_once_with(
            session,
            node_id=node_id,
            space_id=space_id,
            pass_threshold_percent=85,
        )
        session.commit.assert_not_awaited()
    else:
        session.commit.assert_awaited_once()


def test_threshold_patch_rejects_archived_quiz() -> None:
    from fastapi import HTTPException

    node_id = uuid4()
    quiz_id = uuid4()
    session = MagicMock()
    service = QuizService(session)
    quiz = SimpleNamespace(
        quiz_id=quiz_id,
        node_id=node_id,
        space_id=uuid4(),
        is_published=False,
        lifecycle_status="archived",
    )
    repo = MagicMock()
    repo.get_quiz_by_id_for_update = AsyncMock(return_value=quiz)

    with (
        patch(
            "src.api.core.services.quiz_services.quiz_service."
            "_get_node_and_assert_space_access",
            new=AsyncMock(),
        ),
        patch(
            "src.api.core.services.quiz_services.quiz_service.QuizRepository",
            return_value=repo,
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                service.update_pass_threshold(
                    node_id=node_id,
                    quiz_id=quiz_id,
                    request=QuizPassThresholdUpdateRequest(pass_threshold_percent=85),
                    user_id=uuid4(),
                    role="mentor",
                )
            )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_code"] == "QUIZ_THRESHOLD_NOT_EDITABLE"


def test_publish_preserves_threshold_when_omitted() -> None:
    node_id = uuid4()
    quiz_id = uuid4()
    space_id = uuid4()
    session = MagicMock()
    service = QuizService(session)
    quiz = SimpleNamespace(
        quiz_id=quiz_id,
        node_id=node_id,
        space_id=space_id,
        pass_threshold_percent=85,
        is_published=False,
        lifecycle_status="draft",
    )
    repo = MagicMock()
    repo.lock_quizzes_for_node = AsyncMock()
    repo.get_quiz_by_id_for_update = AsyncMock(return_value=quiz)
    repo.update_pass_threshold = AsyncMock()
    repo.publish_quiz = AsyncMock(return_value=quiz)
    repo.get_active_questions_missing_hints = AsyncMock(return_value=[])
    repo.get_questions_by_quiz = AsyncMock(return_value=[])
    repo.get_active_questions_by_quiz = AsyncMock(return_value=[])
    sm_repo = MagicMock()
    sm_repo.get_published_version = AsyncMock(return_value=MagicMock())

    with (
        patch("src.api.core.services.quiz_services.quiz_service._assert_mentor"),
        patch(
            "src.api.core.services.quiz_services.quiz_service."
            "_get_node_and_assert_space_access",
            new=AsyncMock(return_value=SimpleNamespace(space_id=space_id)),
        ),
        patch(
            "src.api.core.services.quiz_services.quiz_service."
            "_get_space_and_assert_owner",
            new=AsyncMock(return_value=SimpleNamespace(is_published=True)),
        ),
        patch(
            "src.api.core.services.quiz_services.quiz_service.QuizRepository",
            return_value=repo,
        ),
        patch(
            "src.api.core.services.quiz_services.quiz_service.StudyMaterialRepository",
            return_value=sm_repo,
        ),
        patch(
            "src.api.core.services.quiz_services.quiz_service.validate_quiz_can_be_published"
        ),
        patch(
            "src.api.core.services.quiz_services.quiz_service.QuizOut"
        ) as quiz_out_cls,
        patch(
            "src.api.core.services.quiz_services.quiz_service."
            "reset_node_quiz_passed_for_all_trainees",
            new=AsyncMock(),
        ),
    ):
        quiz_out_cls.model_validate.return_value = MagicMock(
            questions=[], hints_status="none"
        )
        asyncio.run(
            service.publish_quiz(
                node_id=node_id,
                quiz_id=quiz_id,
                request=QuizPublishRequest(),
                user_id=uuid4(),
                role="mentor",
            )
        )

    repo.update_pass_threshold.assert_not_awaited()
    repo.publish_quiz.assert_awaited_once()
