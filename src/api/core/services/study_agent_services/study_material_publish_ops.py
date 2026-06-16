"""Atomic publish/unpublish cascades for study material versions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.study_material_exceptions.study_material_exceptions import (
    StudyMaterialPublishTransactionFailedException,
    StudyMaterialUnpublishTransactionFailedException,
)
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.utils.study_agent_utils.publish_cascade import (
    get_quizzes_linked_to_study_material_version,
    partition_quizzes_by_publish_state,
)


async def execute_publish_version_cascade(
    session: AsyncSession,
    *,
    node_id: UUID,
    target_version: StudyMaterialVersion,
    previous_published_version: StudyMaterialVersion | None,
    published_by: UUID,
) -> StudyMaterialVersion:
    """Publish target version and cascade quiz effects in one transaction."""
    try:
        quiz_repo = QuizRepository(session)
        sm_repo = StudyMaterialRepository(session)

        if (
            previous_published_version is not None
            and previous_published_version.version_id != target_version.version_id
        ):
            linked = await get_quizzes_linked_to_study_material_version(
                session,
                node_id=node_id,
                study_material_version_id=previous_published_version.version_id,
            )
            draft_quizzes, published_quizzes = partition_quizzes_by_publish_state(
                linked
            )
            for draft in draft_quizzes:
                await quiz_repo.delete_quiz(draft, commit=False)
            for published_quiz in published_quizzes:
                await quiz_repo.unpublish_quiz(published_quiz, commit=False)

        await sm_repo.publish_version(target_version, published_by, commit=False)
        await session.commit()
        await session.refresh(target_version)
        return target_version
    except Exception as exc:
        await session.rollback()
        raise StudyMaterialPublishTransactionFailedException() from exc


async def execute_unpublish_version_cascade(
    session: AsyncSession,
    *,
    node_id: UUID,
    version: StudyMaterialVersion,
) -> StudyMaterialVersion:
    """Unpublish version and linked published quizzes; retain drafts."""
    try:
        quiz_repo = QuizRepository(session)
        sm_repo = StudyMaterialRepository(session)

        linked = await get_quizzes_linked_to_study_material_version(
            session,
            node_id=node_id,
            study_material_version_id=version.version_id,
        )
        _, published_quizzes = partition_quizzes_by_publish_state(linked)
        for published_quiz in published_quizzes:
            await quiz_repo.unpublish_quiz(published_quiz, commit=False)

        await sm_repo.unpublish_version(version, commit=False)
        await session.commit()
        await session.refresh(version)
        return version
    except Exception as exc:
        await session.rollback()
        raise StudyMaterialUnpublishTransactionFailedException() from exc
