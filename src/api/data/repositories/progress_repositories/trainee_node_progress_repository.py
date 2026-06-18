from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.progress_models.trainee_node_progress import (
    TraineeNodeProgress,
)
from src.api.utils.common_utils.time import utc_now


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

    async def get_batch_by_trainee_and_nodes(
        self, trainee_id: UUID, node_ids: list[UUID]
    ) -> dict[UUID, TraineeNodeProgress]:
        """Batch-fetch progress rows for panel rollups and batch GET endpoint."""
        if not node_ids:
            return {}
        result = await self.db.execute(
            select(TraineeNodeProgress).where(
                TraineeNodeProgress.trainee_id == trainee_id,
                TraineeNodeProgress.node_id.in_(node_ids),
            )
        )
        rows = list(result.scalars().all())
        return {row.node_id: row for row in rows}

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

    async def record_quiz_attempt_submission(
        self,
        trainee_id: UUID,
        node_id: UUID,
        space_id: UUID,
        score: float,
    ) -> TraineeNodeProgress:
        """Persist quiz contribution to node progress after attempt submission."""
        row = await self.get_or_create(trainee_id, node_id, space_id)
        now = utc_now()

        best_score = (
            score if row.quiz_best_score is None else max(row.quiz_best_score, score)
        )
        row.quiz_best_score = best_score
        row.quiz_attempt_count = max(row.quiz_attempt_count + 1, 1)
        if best_score >= 0.70:
            row.quiz_passed = True

        row.completion_status = _derive_completion_status(
            study_material_completed=row.study_material_completed,
            quiz_passed=row.quiz_passed,
            study_material_viewed=row.study_material_viewed,
            read_percent=row.study_material_read_percent,
        )
        row.updated_at = now
        await self.db.flush()
        return row
