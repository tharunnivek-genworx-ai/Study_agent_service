"""Centralized lifecycle transitions for study material versions and quizzes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_DISCARDED,
    LIFECYCLE_DRAFT,
    LIFECYCLE_HIDDEN,
)


def _now() -> datetime:
    return datetime.now(UTC)


def transition_sm_to_archived(version: StudyMaterialVersion) -> None:
    """Supersede path: retain publish metadata, move to trainee archive lifecycle."""
    version.is_published = False
    version.lifecycle_status = LIFECYCLE_ARCHIVED
    version.superseded_at = _now()


def transition_sm_to_hidden(version: StudyMaterialVersion) -> None:
    """Explicit unpublish: retain publish metadata; return to mentor draft workspace."""
    version.is_published = False
    version.lifecycle_status = LIFECYCLE_DRAFT
    version.superseded_at = None


def transition_sm_to_active(version: StudyMaterialVersion, published_by: UUID) -> None:
    """Publish or re-publish a study material version as the active trainee layer."""
    now = _now()
    version.is_published = True
    version.published_at = now
    version.published_by = published_by
    version.lifecycle_status = LIFECYCLE_ACTIVE
    version.superseded_at = None


def transition_quiz_to_archived(quiz: Quiz) -> None:
    """Supersede path: unpublish but preserve published_at and attempt history."""
    now = _now()
    quiz.is_published = False
    quiz.lifecycle_status = LIFECYCLE_ARCHIVED
    quiz.superseded_at = now
    quiz.updated_at = now


def transition_quiz_to_hidden(quiz: Quiz) -> None:
    """Explicit unpublish: retain publish metadata, hide from trainees."""
    now = _now()
    quiz.is_published = False
    quiz.lifecycle_status = LIFECYCLE_HIDDEN
    quiz.updated_at = now


def transition_quiz_to_active(quiz: Quiz) -> None:
    """Publish a quiz as the active trainee layer for its node."""
    now = _now()
    quiz.is_published = True
    quiz.published_at = now
    quiz.lifecycle_status = LIFECYCLE_ACTIVE
    quiz.superseded_at = None
    quiz.updated_at = now


def transition_sm_to_discarded(version: StudyMaterialVersion) -> None:
    """Mentor workspace trash: soft-remove draft from all views; row retained."""
    version.lifecycle_status = LIFECYCLE_DISCARDED
    version.is_published = False
    version.is_active = False


def transition_quiz_to_discarded(quiz: Quiz) -> None:
    """Mentor workspace trash: soft-remove draft quiz; row retained."""
    now = _now()
    quiz.lifecycle_status = LIFECYCLE_DISCARDED
    quiz.is_published = False
    quiz.updated_at = now
