"""Atomic publish/unpublish cascades for study material versions.

After a version is published or unpublished, every enrolled trainee's
trainee_space_progress.total_nodes value changes (because total_nodes counts
active nodes with at least one published study material version).
To keep the cached rollup fresh, each cascade commits its own content
change first, then fans out a space-progress recompute to all enrolled
trainees via recompute_all_trainees_space_progress (EC-23).

Recompute failure for individual trainees is logged and swallowed inside the
utility — it never rolls back the content change.
"""

from __future__ import annotations

import logging
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
from src.api.utils.mentor_progress_utils.space_recompute import (
    recompute_all_trainees_space_progress,
)
from src.api.utils.study_agent_utils.publish_cascade import (
    get_quizzes_linked_to_study_material_version,
    partition_quizzes_by_publish_state,
)

logger = logging.getLogger(__name__)


async def execute_publish_version_cascade(
    session: AsyncSession,
    *,
    node_id: UUID,
    target_version: StudyMaterialVersion,
    previous_published_version: StudyMaterialVersion | None,
    published_by: UUID,
) -> StudyMaterialVersion:
    """Publish target version and cascade quiz effects in one transaction.

    After the publish commit succeeds, fans out a space-progress recompute
    to all enrolled trainees so trainee_space_progress.total_nodes reflects
    the newly published node immediately (EC-23).
    """
    try:
        quiz_repo = QuizRepository(session)
        sm_repo = StudyMaterialRepository(session)
        # Capture space_id before commit — ORM attributes expire after commit
        # in async sessions, so accessing target_version.space_id after commit
        # would require an extra SELECT.
        space_id = target_version.space_id

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

        # EC-23: fan-out space-progress recompute for all enrolled trainees.
        # The publish is already committed above; recompute runs independently.
        try:
            await recompute_all_trainees_space_progress(session, space_id=space_id)
        except Exception:
            logger.warning(
                "execute_publish_version_cascade: space-progress recompute failed "
                "for space_id=%s node_id=%s — progress data may be stale until next "
                "mentor dashboard refresh",
                space_id,
                node_id,
                exc_info=True,
            )

        # Recompute commits per trainee and expires ORM state; reload before
        # the caller validates into StudyMaterialVersionOut.
        await session.refresh(target_version)
        return target_version
    except StudyMaterialPublishTransactionFailedException:
        raise
    except Exception as exc:
        await session.rollback()
        raise StudyMaterialPublishTransactionFailedException() from exc


async def execute_unpublish_version_cascade(
    session: AsyncSession,
    *,
    node_id: UUID,
    version: StudyMaterialVersion,
) -> StudyMaterialVersion:
    """Unpublish version and linked published quizzes; retain drafts.

    After the unpublish commit succeeds, fans out a space-progress recompute
    so total_nodes no longer counts this node for any trainee (EC-23).
    """
    try:
        quiz_repo = QuizRepository(session)
        sm_repo = StudyMaterialRepository(session)
        # Capture space_id before commit — ORM attributes expire after commit.
        space_id = version.space_id

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

        # EC-23: fan-out space-progress recompute for all enrolled trainees.
        try:
            await recompute_all_trainees_space_progress(session, space_id=space_id)
        except Exception:
            logger.warning(
                "execute_unpublish_version_cascade: space-progress recompute failed "
                "for space_id=%s node_id=%s — progress data may be stale until next "
                "mentor dashboard refresh",
                space_id,
                node_id,
                exc_info=True,
            )

        await session.refresh(version)
        return version
    except StudyMaterialUnpublishTransactionFailedException:
        raise
    except Exception as exc:
        await session.rollback()
        raise StudyMaterialUnpublishTransactionFailedException() from exc
