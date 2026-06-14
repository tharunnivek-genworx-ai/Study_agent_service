from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode


class NodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_node_by_id(self, node_id: UUID) -> TopicNode | None:
        result = await self.db.execute(
            select(TopicNode).where(TopicNode.node_id == node_id)
        )
        return cast(TopicNode | None, result.scalars().first())

    async def get_ancestors(self, node: TopicNode) -> list[TopicNode]:
        """Return ancestor nodes ordered root → parent (exclusive of *node*)."""
        ancestors: list[TopicNode] = []
        current_parent_id = node.parent_id

        while current_parent_id is not None:
            parent = await self.get_node_by_id(current_parent_id)
            if parent is None:
                break
            ancestors.append(parent)
            current_parent_id = parent.parent_id

        ancestors.reverse()
        return ancestors
