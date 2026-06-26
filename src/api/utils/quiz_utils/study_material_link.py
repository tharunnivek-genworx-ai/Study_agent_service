"""Validate quiz ↔ study material linkage.

Mentor paths only require that *some* published SM exists on the node.
Version-match checks are intentionally absent so quiz lifecycle is
decoupled from SM version identity.

`validate_study_material_is_currently_published_for_node` retains the
strict version-match check because it guards **trainee** attempt start,
where content identity matters.
"""

from __future__ import annotations

from uuid import UUID

from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (
    QuizCannotPublishWithoutPublishedStudyMaterialException,
    QuizHasNoPublishedStudyMaterialException,
    QuizStudyMaterialNotCurrentPublishedException,
)
from src.api.core.exceptions.study_material_exceptions.study_material_exceptions import (
    StudyMaterialVersionMismatchException,
)
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)


class _PublishedVersionLike:
    node_id: UUID
    version_id: UUID
    version_number: int
    generation_type: str


def validate_study_material_is_currently_published_for_node(
    *,
    node_id: UUID,
    version_id: UUID | None,
    published_version: _PublishedVersionLike | None,
) -> None:
    """
    Ensure the node has a published study material before a trainee starts a quiz.

    When ``version_id`` metadata is present on the quiz, it must match the
    currently published SM version.  When metadata is ``None`` (orphaned after
    SM supersede), any live SM on the node is sufficient.
    """
    if published_version is None:
        raise QuizHasNoPublishedStudyMaterialException()
    if published_version.node_id != node_id:
        raise StudyMaterialVersionMismatchException()
    if version_id is not None and published_version.version_id != version_id:
        raise QuizStudyMaterialNotCurrentPublishedException()


async def get_mentor_quiz_study_material_source(
    sm_repo: StudyMaterialRepository,
    *,
    node_id: UUID,
) -> StudyMaterialVersion:
    """Resolve study material for mentor quiz generation and draft editing.

    Prefer the live published edition; otherwise fall back to the mentor's
    active working draft when nothing is live for students.
    """
    published = await sm_repo.get_published_version(node_id)
    if published is not None and (published.content or "").strip():
        return published

    active = await sm_repo.get_active_version(node_id)
    if active is not None and (active.content or "").strip():
        return active

    raise QuizHasNoPublishedStudyMaterialException()


async def require_mentor_quiz_study_material_source(
    sm_repo: StudyMaterialRepository,
    *,
    node_id: UUID,
) -> StudyMaterialVersion:
    """Require usable study material before mentor quiz draft work."""
    return await get_mentor_quiz_study_material_source(sm_repo, node_id=node_id)


async def require_published_study_material_for_node(
    sm_repo: StudyMaterialRepository,
    *,
    node_id: UUID,
) -> None:
    """Require a live study material on the node before mentor quiz mutations.

    Option B: any published SM on the node is sufficient — no version-match
    with the quiz's ``study_material_version_id`` metadata.
    """
    published = await sm_repo.get_published_version(node_id)
    if published is None:
        raise QuizHasNoPublishedStudyMaterialException()


def validate_quiz_can_be_published(
    *,
    published_version: _PublishedVersionLike | None,
) -> None:
    """Block quiz publish when no study material is published on the node.

    Relaxed from the previous version-match check: any live SM on the node
    satisfies the publish precondition.
    """
    if published_version is None:
        raise QuizCannotPublishWithoutPublishedStudyMaterialException()
