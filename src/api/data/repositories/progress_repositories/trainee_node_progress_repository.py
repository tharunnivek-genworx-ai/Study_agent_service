from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.progress_models.trainee_node_progress import (
    TraineeNodeProgress,
)
from src.api.utils.time import utc_now


def _derive_completion_status(
    *,
    study_material_completed: bool,
    quiz_passed: bool,
    study_material_viewed: bool,
    read_percent: int,
) -> str:
    if study_material_completed and quiz_passed:
        return "completed"
    if (
        study_material_completed
        or quiz_passed
        or study_material_viewed
        or read_percent > 0
    ):
        return "in_progress"
    return "not_started"


class TraineeNodeProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_by_trainee_and_node(
        self, trainee_id: UUID, node_id: UUID
    ) -> TraineeNodeProgress | None:
        result = await self.db.execute(
            select(TraineeNodeProgress).where(
                TraineeNodeProgress.trainee_id == trainee_id,
                TraineeNodeProgress.node_id == node_id,
            )
        )
        return cast(TraineeNodeProgress | None, result.scalars().first())

    async def get_or_create(
        self,
        trainee_id: UUID,
        node_id: UUID,
        space_id: UUID,
    ) -> TraineeNodeProgress:
        existing = await self.get_by_trainee_and_node(trainee_id, node_id)
        if existing is not None:
            return existing

        row = TraineeNodeProgress(
            progress_id=uuid4(),
            trainee_id=trainee_id,
            node_id=node_id,
            space_id=space_id,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def mark_study_material_viewed(
        self, trainee_id: UUID, node_id: UUID, space_id: UUID
    ) -> TraineeNodeProgress:
        row = await self.get_or_create(trainee_id, node_id, space_id)
        now = utc_now()
        if not row.study_material_viewed:
            row.study_material_viewed = True
            row.first_viewed_at = now
        row.last_viewed_at = now
        row.completion_status = _derive_completion_status(
            study_material_completed=row.study_material_completed,
            quiz_passed=row.quiz_passed,
            study_material_viewed=row.study_material_viewed,
            read_percent=row.study_material_read_percent,
        )
        row.updated_at = now
        await self.db.flush()
        return row

    async def update_read_progress(
        self,
        trainee_id: UUID,
        node_id: UUID,
        space_id: UUID,
        read_percent: int,
    ) -> TraineeNodeProgress:
        row = await self.get_or_create(trainee_id, node_id, space_id)
        now = utc_now()
        clamped = max(0, min(100, read_percent))
        row.study_material_read_percent = max(row.study_material_read_percent, clamped)
        if row.study_material_read_percent >= 100:
            row.study_material_completed = True
        if not row.study_material_viewed:
            row.study_material_viewed = True
            row.first_viewed_at = now
        row.last_viewed_at = now
        row.completion_status = _derive_completion_status(
            study_material_completed=row.study_material_completed,
            quiz_passed=row.quiz_passed,
            study_material_viewed=row.study_material_viewed,
            read_percent=row.study_material_read_percent,
        )
        row.updated_at = now
        await self.db.flush()
        return row
