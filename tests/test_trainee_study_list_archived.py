"""Unit tests for trainee archived study material list fields."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.api.core.services.trainee_study_services.trainee_study_service import (
    TraineeStudyService,
)


def _dt() -> datetime:
    return datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)


class TestListArchivedStudyMaterialFields:
    def test_archived_sm_row_sets_removed_at_and_can_read_material(self):
        node_id = uuid4()
        user_id = uuid4()
        version_id = uuid4()
        superseded = _dt()

        archived_version = MagicMock()
        archived_version.version_id = version_id
        archived_version.version_number = 2
        archived_version.generation_type = "regenerated"
        archived_version.published_at = _dt()
        archived_version.superseded_at = superseded

        service = TraineeStudyService(MagicMock())

        with (
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.assert_trainee_archive_context",
                AsyncMock(),
            ),
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.list_trainee_archive_sm",
                AsyncMock(return_value=[archived_version]),
            ),
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.list_trainee_archive_quizzes",
                AsyncMock(return_value=[]),
            ),
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.MentorProgressRepository"
            ) as progress_repo_cls,
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.build_version_display_label",
                return_value="v2 (Regenerated)",
            ),
        ):
            progress_repo_cls.return_value.get_node_progress = AsyncMock(
                return_value=None
            )
            service.repo.get_published_study_material = AsyncMock(return_value=None)

            result = asyncio.run(
                service.list_archived_study_material(node_id, user_id, "trainee")
            )

        assert len(result.versions) == 1
        item = result.versions[0]
        assert item.version_id == version_id
        assert item.removed_at == superseded
        assert item.can_read_material is True
        assert item.is_current_version is False

    def test_quiz_only_current_version_row_uses_quiz_superseded_at(self):
        node_id = uuid4()
        user_id = uuid4()
        sm_version_id = uuid4()
        quiz_id = uuid4()
        quiz_removed = _dt()

        published_sm = MagicMock()
        published_sm.version_id = sm_version_id
        published_sm.version_number = 3
        published_sm.generation_type = "improved"
        published_sm.published_at = _dt()
        published_sm.superseded_at = None

        archived_quiz = MagicMock()
        archived_quiz.quiz_id = quiz_id
        archived_quiz.superseded_at = quiz_removed

        service = TraineeStudyService(MagicMock())

        with (
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.assert_trainee_archive_context",
                AsyncMock(),
            ),
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.list_trainee_archive_sm",
                AsyncMock(return_value=[]),
            ),
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.list_trainee_archive_quizzes",
                AsyncMock(return_value=[archived_quiz]),
            ),
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.MentorProgressRepository"
            ) as progress_repo_cls,
            patch(
                "src.api.core.services.trainee_study_services.trainee_study_service.build_version_display_label",
                return_value="v3 (Improved)",
            ),
        ):
            progress_repo_cls.return_value.get_node_progress = AsyncMock(
                return_value=None
            )
            service.repo.get_published_study_material = AsyncMock(
                return_value=published_sm
            )

            result = asyncio.run(
                service.list_archived_study_material(node_id, user_id, "trainee")
            )

        assert len(result.versions) == 1
        item = result.versions[0]
        assert item.is_current_version is True
        assert item.version_id == sm_version_id
        assert item.removed_at == quiz_removed
        assert item.can_read_material is True
        assert item.archived_quiz_id == quiz_id
        assert item.has_archived_quiz is True
