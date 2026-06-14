from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.space_node_exceptions.node_exceptions import (
    NodeNotFoundException,
)
from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.repositories.space_node_repository.node_repository import (
    NodeRepository,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _get_space_and_assert_owner,
)


async def _get_node_and_assert_space_access(
    session: AsyncSession,
    node_id: UUID,
    user_id: UUID,
    *,
    owner_only: bool = False,
) -> TopicNode:
    """Load an active node and optionally assert mentor ownership of its space."""
    repo = NodeRepository(session)
    node = await repo.get_node_by_id(node_id)
    if node is None or not node.is_active:
        raise NodeNotFoundException()

    if owner_only:
        await _get_space_and_assert_owner(session, node.space_id, user_id)

    return node
