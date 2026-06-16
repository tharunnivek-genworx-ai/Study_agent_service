"""Quiz lookup helpers for study material publish/unpublish cascades."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.quizzes import Quiz


async def get_quizzes_linked_to_study_material_version(
    session: AsyncSession,
    *,
    node_id: UUID,
    study_material_version_id: UUID,
) -> list[Quiz]:
    """Return all quizzes linked to a study material version for this node."""
    result = await session.execute(
        select(Quiz).where(
            and_(
                Quiz.node_id == node_id,
                Quiz.study_material_version_id == study_material_version_id,
            )
        )
    )
    return list(result.scalars().all())


def partition_quizzes_by_publish_state(
    quizzes: list[Quiz],
) -> tuple[list[Quiz], list[Quiz]]:
    """Split quizzes into (draft_quizzes, published_quizzes)."""
    draft = [q for q in quizzes if not q.is_published]
    published = [q for q in quizzes if q.is_published]
    return draft, published
