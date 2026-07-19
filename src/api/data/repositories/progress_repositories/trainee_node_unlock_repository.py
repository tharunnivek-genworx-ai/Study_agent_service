"""Persistence for durable trainee node unlock grants."""

from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.progress_models.trainee_node_unlocks import (
    TraineeNodeUnlock,
)
from src.api.utils.common_utils import utc_now

UnlockSource = str  # parent_completed | backfill


class TraineeNodeUnlockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_by_trainee_and_node(
        self, trainee_id: UUID, node_id: UUID
    ) -> TraineeNodeUnlock | None:
        result = await self.db.execute(
            select(TraineeNodeUnlock).where(
                TraineeNodeUnlock.trainee_id == trainee_id,
                TraineeNodeUnlock.node_id == node_id,
            )
        )
        return cast(TraineeNodeUnlock | None, result.scalars().first())

    async def get_unlocked_node_ids(
        self, trainee_id: UUID, node_ids: list[UUID]
    ) -> set[UUID]:
        """Return the subset of *node_ids* that already have a durable grant."""
        if not node_ids:
            return set()
        result = await self.db.execute(
            select(TraineeNodeUnlock.node_id).where(
                TraineeNodeUnlock.trainee_id == trainee_id,
                TraineeNodeUnlock.node_id.in_(node_ids),
            )
        )
        return {row[0] for row in result.all()}

    async def grant_unlock(
        self,
        *,
        trainee_id: UUID,
        node_id: UUID,
        space_id: UUID,
        gate_node_id: UUID | None,
        source: UnlockSource,
    ) -> bool:
        """Idempotently insert a durable unlock. Returns True if newly written."""
        stmt = (
            insert(TraineeNodeUnlock)
            .values(
                unlock_id=uuid4(),
                trainee_id=trainee_id,
                node_id=node_id,
                space_id=space_id,
                unlocked_at=utc_now(),
                source=source,
                gate_node_id=gate_node_id,
            )
            .on_conflict_do_nothing(constraint="uq_traineenodeunlocks_trainee_node")
            .returning(TraineeNodeUnlock.unlock_id)
        )
        result = await self.db.execute(stmt)
        newly_written = result.scalar_one_or_none() is not None
        await self.db.flush()
        return newly_written

    async def delete_unlocks_for_node(self, node_id: UUID) -> int:
        """Clear all trainees' grants for *node_id* (reparent / structure change)."""
        result = await self.db.execute(
            delete(TraineeNodeUnlock).where(TraineeNodeUnlock.node_id == node_id)
        )
        deleted = int(getattr(result, "rowcount", 0) or 0)
        await self.db.flush()
        return deleted
