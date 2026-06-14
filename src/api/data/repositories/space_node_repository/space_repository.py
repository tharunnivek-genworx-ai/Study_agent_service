from typing import cast
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_spaces_trees.espaces import ESpace
from src.api.data.models.postgres.e_spaces_trees.space_trainees import SpaceTrainee


class SpaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_space_by_id(self, space_id: UUID) -> ESpace | None:
        result = await self.db.execute(
            select(ESpace).where(ESpace.space_id == space_id)
        )
        return cast(ESpace | None, result.scalars().first())

    async def is_active_member(self, space_id: UUID, trainee_id: UUID) -> bool:
        result = await self.db.execute(
            select(SpaceTrainee).where(
                and_(
                    SpaceTrainee.space_id == space_id,
                    SpaceTrainee.trainee_id == trainee_id,
                    SpaceTrainee.is_active,
                )
            )
        )
        return result.scalars().first() is not None
