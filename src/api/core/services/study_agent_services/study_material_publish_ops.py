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
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.data.repositories.trainee_quiz_repositories.trainee_quiz_repository import (
    TraineeQuizRepository,
)
from src.api.schemas.study_material_schemas.study_material_schema import RetentionMode
from src.api.utils.content_lifecycle.transitions import (
    transition_sm_to_archived,
    transition_sm_to_hidden,
)
from src.api.utils.mentor_progress_utils.space_recompute import (
    recompute_all_trainees_space_progress,
)
from src.api.utils.trainee_progress_utils.progress_resets import (
    reset_node_read_progress_for_all_trainees,
)

logger = logging.getLogger(__name__)


async def execute_publish_version_cascade(
    session: AsyncSession,
    *,
    node_id: UUID,
    target_version: StudyMaterialVersion,
    previous_published_version: StudyMaterialVersion | None,
    published_by: UUID,
    superseded_retention_mode: RetentionMode = RetentionMode.keep_for_review,
) -> StudyMaterialVersion:
    """Publish target version in one transaction; quiz lifecycle is unchanged.

    After the publish commit succeeds, fans out a space-progress recompute
    to all enrolled trainees so trainee_space_progress.total_nodes reflects
    the newly published node immediately (EC-23).
    """
    try:
        sm_repo = StudyMaterialRepository(session)
        # Capture space_id before commit — ORM attributes expire after commit
        # in async sessions, so accessing target_version.space_id after commit
        # would require an extra SELECT.
        space_id = target_version.space_id
        target_version_id = target_version.version_id
        previous_version_id = (
            previous_published_version.version_id
            if previous_published_version is not None
            else None
        )
        is_supersede = (
            previous_version_id is not None and previous_version_id != target_version_id
        )

        await sm_repo.publish_version(
            target_version,
            published_by,
            superseded_retention_mode=superseded_retention_mode,
            commit=False,
        )
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

        # M4a: reset read progress when superseding a prior published version.
        if is_supersede:
            quiz_repo = TraineeQuizRepository(session)
            has_published_quiz_on_node = (
                await quiz_repo.get_published_quiz_by_node(node_id) is not None
            )
            try:
                await reset_node_read_progress_for_all_trainees(
                    session,
                    node_id=node_id,
                    space_id=space_id,
                    has_published_quiz=has_published_quiz_on_node,
                )
            except Exception:
                logger.warning(
                    "execute_publish_version_cascade: read-progress reset failed "
                    "for space_id=%s node_id=%s",
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
    retention_mode: RetentionMode,
) -> StudyMaterialVersion:
    """Unpublish SM version only; quiz lifecycle is unchanged.

    retention_mode controls the SM transition:
      remove_completely → transition_sm_to_hidden  (draft; not in Previous versions)
      keep_for_review   → transition_sm_to_archived (archived; visible in Previous versions)

    After the unpublish commit succeeds, fans out a space-progress recompute
    so total_nodes no longer counts this node for any trainee (EC-23).
    """
    try:
        # Capture space_id before commit — ORM attributes expire after commit.
        space_id = version.space_id

        if retention_mode == RetentionMode.keep_for_review:
            transition_sm_to_archived(version)
        else:
            transition_sm_to_hidden(version)

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
