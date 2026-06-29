from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import (
    NodeForbiddenException,
    NodeNotFoundException,
    SpaceNotFoundException,
)
from src.api.data.models.postgres.e_spaces_trees.espaces import ESpace
from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.repositories import (
    NodeRepository,
    SpaceRepository,
)
from src.api.utils.space_node_utils.space_role_assert import (
    _resolve_effective_mentor,
)


def _assert_mentor(role: str) -> None:
    if role != "mentor":
        raise NodeForbiddenException()


def _assert_trainee(role: str) -> None:
    if role != "trainee":
        raise NodeForbiddenException()


async def _get_space_and_assert_owner(
    session: AsyncSession, space_id: UUID, mentor_id: UUID
) -> ESpace:
    space_repo = SpaceRepository(session)
    space = await space_repo.get_space_by_id(space_id)
    if space is None or not space.is_active:
        raise SpaceNotFoundException()
    if _resolve_effective_mentor(space) != mentor_id:
        raise NodeForbiddenException()
    return space


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


async def _assert_space_access(
    session: AsyncSession, space_id: UUID, user_id: UUID, role: str
) -> None:
    space_repo = SpaceRepository(session)
    space = await space_repo.get_space_by_id(space_id)
    if space is None or not space.is_active:
        raise SpaceNotFoundException()

    if role == "mentor":
        if _resolve_effective_mentor(space) != user_id:
            raise NodeForbiddenException()
    elif role == "trainee":
        is_member = await space_repo.is_active_member(space_id, user_id)
        if not is_member:
            raise NodeForbiddenException()
    else:
        raise NodeForbiddenException()
