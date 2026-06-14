from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.space_node_exceptions.node_exceptions import (
    NodeForbiddenException,
)
from src.api.core.exceptions.space_node_exceptions.space_exceptions import (
    SpaceNotFoundException,
)
from src.api.data.models.postgres.e_spaces_trees.espaces import ESpace
from src.api.data.repositories.space_node_repository.space_repository import (
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
