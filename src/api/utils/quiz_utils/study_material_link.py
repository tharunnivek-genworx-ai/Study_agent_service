"""Validate quiz ↔ study material version linkage."""

from __future__ import annotations

from uuid import UUID

from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (
    QuizCannotPublishWithoutPublishedStudyMaterialException,
    QuizHasNoPublishedStudyMaterialException,
    QuizStudyMaterialNotCurrentPublishedException,
    QuizVersionNotPublishedException,
)
from src.api.core.exceptions.study_material_exceptions.study_material_exceptions import (
    StudyMaterialVersionMismatchException,
)
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.utils.study_agent_utils.version_labels import build_version_display_label


class _PublishedVersionLike:
    node_id: UUID
    version_id: UUID
    version_number: int
    generation_type: str


def _version_label(version: _PublishedVersionLike | None) -> str | None:
    if version is None:
        return None
    return build_version_display_label(version.version_number, version.generation_type)


def validate_study_material_is_currently_published_for_node(
    *,
    node_id: UUID,
    version_id: UUID,
    published_version: _PublishedVersionLike | None,
) -> None:
    """
    Ensure version_id is the single currently published study material for the node.
    Used before quiz generation, quiz publish, and trainee quiz delivery.
    """
    if published_version is None:
        raise QuizHasNoPublishedStudyMaterialException()
    if published_version.node_id != node_id:
        raise StudyMaterialVersionMismatchException()
    if published_version.version_id != version_id:
        raise QuizStudyMaterialNotCurrentPublishedException()


async def validate_quiz_linked_version_is_published(
    sm_repo: StudyMaterialRepository,
    *,
    node_id: UUID,
    study_material_version_id: UUID,
) -> None:
    """Block quiz mutations when the linked study material version is unpublished."""
    linked = await sm_repo.get_version_by_id(study_material_version_id)
    if linked is None or linked.node_id != node_id:
        raise StudyMaterialVersionMismatchException()
    if linked.is_published:
        return

    published = await sm_repo.get_published_version(node_id)
    raise QuizVersionNotPublishedException(
        version_label=build_version_display_label(
            linked.version_number, linked.generation_type
        ),
        current_published_version_label=_version_label(published),
    )


def validate_quiz_can_be_published(
    *,
    node_id: UUID,
    quiz_study_material_version_id: UUID,
    published_version: _PublishedVersionLike | None,
) -> None:
    """Block quiz publish when the linked study material is not currently published."""
    try:
        validate_study_material_is_currently_published_for_node(
            node_id=node_id,
            version_id=quiz_study_material_version_id,
            published_version=published_version,
        )
    except QuizStudyMaterialNotCurrentPublishedException as exc:
        raise QuizCannotPublishWithoutPublishedStudyMaterialException() from exc
    except QuizHasNoPublishedStudyMaterialException as exc:
        raise QuizCannotPublishWithoutPublishedStudyMaterialException() from exc
