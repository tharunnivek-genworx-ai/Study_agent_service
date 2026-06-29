"""Helpers for mentor-facing quiz history panel."""

from __future__ import annotations

from uuid import UUID

from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
from src.api.data.repositories import (
    StudyMaterialRepository,
)
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_HIDDEN,
)
from src.api.utils.content_lifecycle.visibility import is_discarded
from src.api.utils.study_agent_utils.version.version_labels import (
    build_version_display_label,
)

UNKNOWN_SM_VERSION_LABEL = "Unknown version"


async def resolve_history_version_label(
    sm_repo: StudyMaterialRepository,
    sm_version_id: UUID | None,
    cache: dict[UUID, str],
) -> str:
    """Label for history rows; tolerates NULL metadata after SM draft discard."""
    if sm_version_id is None:
        return UNKNOWN_SM_VERSION_LABEL
    if sm_version_id not in cache:
        sm_version = await sm_repo.get_version_by_id(sm_version_id)
        cache[sm_version_id] = (
            build_version_display_label(
                sm_version.version_number, sm_version.generation_type
            )
            if sm_version is not None
            else UNKNOWN_SM_VERSION_LABEL
        )
    return cache[sm_version_id]


def is_orphan_failed_generation_draft(quiz: Quiz) -> bool:
    """QC-failed drafts that were never published — not history."""
    return bool(quiz.qc_failed_permanently) and quiz.published_at is None


def is_mentor_history_quiz(quiz: Quiz, *, exclude_quiz_id: UUID | None) -> bool:
    """True when a quiz belongs in the mentor history panel.

    History = quizzes that were live (published_at set) and are now ARCHIVED
    or HIDDEN, plus any non-discarded, non-draft quiz that was ever published.
    """
    if exclude_quiz_id is not None and quiz.quiz_id == exclude_quiz_id:
        return False
    if is_discarded(lifecycle_status=quiz.lifecycle_status):
        return False
    if is_orphan_failed_generation_draft(quiz):
        return False
    if quiz.lifecycle_status in (LIFECYCLE_ARCHIVED, LIFECYCLE_HIDDEN):
        return True
    if quiz.published_at is not None:
        return True
    return False


def history_status_badge(quiz: Quiz) -> str:
    if quiz.lifecycle_status == LIFECYCLE_ARCHIVED:
        return "In Previous versions"
    if quiz.lifecycle_status == LIFECYCLE_HIDDEN:
        return "Removed"
    if quiz.published_at is not None:
        return "Was live"
    return "Was live"


def can_delete_history_quiz(quiz: Quiz) -> bool:
    """HIDDEN quizzes (remove_completely path) may be discarded from history."""
    if is_discarded(lifecycle_status=quiz.lifecycle_status):
        return False
    return bool(quiz.lifecycle_status == LIFECYCLE_HIDDEN)
