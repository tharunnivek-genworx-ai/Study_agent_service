"""
Shared database access for trainee-facing study material.

This repository is the single source of truth for reading published study
material versions and discovering which nodes in a space have published
content. Both ``TraineeStudyService`` (full material delivery) and
``TraineeNodePanelService`` (overview/preview panel) depend on it so the
same publish rules are applied everywhere.
"""

from typing import cast
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)


class TraineeStudyRepository:
    """Read-only study material queries for the trainee learning flow."""

    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_published_study_material(
        self, node_id: UUID
    ) -> StudyMaterialVersion | None:
        """Return the latest published version for *node_id*, or ``None``.

        Trainees never see draft or archived versions — only rows where
        ``is_published=True``. When multiple published versions exist (rare),
        the highest ``version_number`` wins.
        """
        result = await self.db.execute(
            select(StudyMaterialVersion)
            .where(
                and_(
                    StudyMaterialVersion.node_id == node_id,
                    StudyMaterialVersion.is_published.is_(True),
                )
            )
            .order_by(StudyMaterialVersion.version_number.desc())
            .limit(1)
        )
        return cast(StudyMaterialVersion | None, result.scalars().first())

    async def get_published_node_ids(self, space_id: UUID) -> set[UUID]:
        """Return every node in *space_id* that has at least one published version.

        Used by the topic detail panel to distinguish available vs locked
        subtopics without N+1 queries per child node.
        """
        result = await self.db.execute(
            select(StudyMaterialVersion.node_id)
            .where(
                and_(
                    StudyMaterialVersion.space_id == space_id,
                    StudyMaterialVersion.is_published.is_(True),
                )
            )
            .distinct()
        )
        return {row[0] for row in result.all()}
