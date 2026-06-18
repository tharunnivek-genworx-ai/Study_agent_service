"""
Database queries for the trainee topic detail panel (tree + content only).

Progress rows are **not** read here — ``TraineeNodePanelService`` calls
``TraineeProgressService.get_batch_node_progress`` instead (Option 1).
"""

from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.repositories.space_node_repository.node_repository import (
    NodeRepository,
)
from src.api.data.repositories.trainee_study_repositories.trainee_study_repository import (
    TraineeStudyRepository,
)


class TraineeNodePanelRepository:
    """Tree structure and published-material lookups for panel assembly."""

    def __init__(self, session: AsyncSession) -> None:
        self.db = session
        self.node_repo = NodeRepository(session)
        self.study_repo = TraineeStudyRepository(session)

    async def get_active_nodes_in_space(self, space_id: UUID) -> list[TopicNode]:
        """All active topic nodes — used to build the in-memory child map."""
        result = await self.db.execute(
            select(TopicNode).where(
                and_(
                    TopicNode.space_id == space_id,
                    TopicNode.is_active.is_(True),
                )
            )
        )
        return list(result.scalars().all())

    async def get_published_node_ids(self, space_id: UUID) -> set[UUID]:
        return await self.study_repo.get_published_node_ids(space_id)

    async def get_published_study_material(
        self, node_id: UUID
    ) -> StudyMaterialVersion | None:
        """Latest published version — used for content preview snippets."""
        return await self.study_repo.get_published_study_material(node_id)

    async def get_ancestors(self, node: TopicNode) -> list[TopicNode]:
        return await self.node_repo.get_ancestors(node)

    async def get_siblings(self, node: TopicNode) -> list[TopicNode]:
        result = await self.db.execute(
            select(TopicNode).where(
                and_(
                    TopicNode.space_id == node.space_id,
                    TopicNode.parent_id == node.parent_id,
                    TopicNode.is_active.is_(True),
                )
            )
        )
        siblings = list(result.scalars().all())
        siblings.sort(key=lambda item: item.order_index)
        return siblings
