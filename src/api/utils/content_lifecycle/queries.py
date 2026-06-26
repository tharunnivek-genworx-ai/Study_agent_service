"""Read helpers for trainee archive and clear-drafts eligibility."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_DRAFT,
)
from src.api.utils.content_lifecycle.visibility import exclude_discarded


async def list_trainee_archive_sm(
    session: AsyncSession, node_id: UUID
) -> list[StudyMaterialVersion]:
    """Return superseded study material versions retained for trainee reference."""
    result = await session.execute(
        select(StudyMaterialVersion)
        .where(
            and_(
                StudyMaterialVersion.node_id == node_id,
                StudyMaterialVersion.lifecycle_status == LIFECYCLE_ARCHIVED,
            )
        )
        .order_by(StudyMaterialVersion.version_number.desc())
    )
    return list(result.scalars().all())


async def list_trainee_archive_quizzes(
    session: AsyncSession,
    node_id: UUID,
    *,
    study_material_version_id: UUID | None = None,
) -> list[Quiz]:
    """Return archived quizzes for trainee reference, optionally scoped to one SM version."""
    conditions = [
        Quiz.node_id == node_id,
        Quiz.lifecycle_status == LIFECYCLE_ARCHIVED,
    ]
    if study_material_version_id is not None:
        conditions.append(Quiz.study_material_version_id == study_material_version_id)

    result = await session.execute(
        select(Quiz).where(and_(*conditions)).order_by(Quiz.created_at.desc())
    )
    return list(result.scalars().all())


async def count_blocking_quizzes_for_clear_drafts(
    session: AsyncSession,
    node_id: UUID,
) -> int:
    """Count quizzes that should block clear-all-drafts.

    Blocks on any live quiz on the node, or any non-discarded draft.
    Does not block on archived, hidden, or discarded quizzes.
    """
    block_conditions = [
        and_(
            Quiz.node_id == node_id,
            Quiz.lifecycle_status == LIFECYCLE_ACTIVE,
            Quiz.is_published.is_(True),
            exclude_discarded(Quiz.lifecycle_status),
        ),
        and_(
            Quiz.node_id == node_id,
            Quiz.lifecycle_status == LIFECYCLE_DRAFT,
            Quiz.is_published.is_(False),
            exclude_discarded(Quiz.lifecycle_status),
        ),
    ]

    result = await session.execute(
        select(func.count()).select_from(Quiz).where(or_(*block_conditions))
    )
    return int(result.scalar() or 0)
