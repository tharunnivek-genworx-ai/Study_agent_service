from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.progress_models.trainee_node_progress import (
    TraineeNodeProgress,
)
from src.api.schemas.progress_schemas import CompletionStatus
from src.api.utils.common_utils import utc_now
from src.api.utils.trainee_progress_utils.completion import (
    score_meets_pass_threshold,
)


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
        self,
        trainee_id: UUID,
        node_id: UUID,
        space_id: UUID,
        *,
        completion_status: CompletionStatus,
    ) -> TraineeNodeProgress:
        row = await self.get_or_create(trainee_id, node_id, space_id)
        now = utc_now()
        if not row.study_material_viewed:
            row.study_material_viewed = True
            row.first_viewed_at = now
        row.last_viewed_at = now
        row.completion_status = completion_status
        row.updated_at = now
        await self.db.flush()
        return row

    async def record_quiz_attempt_submission(
        self,
        trainee_id: UUID,
        node_id: UUID,
        space_id: UUID,
        score: float,
        *,
        pass_threshold_percent: int | None,
        completion_status: CompletionStatus,
    ) -> TraineeNodeProgress:
        """Persist quiz contribution to node progress after attempt submission."""
        row = await self.get_or_create(trainee_id, node_id, space_id)
        now = utc_now()

        best_score = (
            score if row.quiz_best_score is None else max(row.quiz_best_score, score)
        )
        row.quiz_best_score = best_score
        row.quiz_attempt_count = max(row.quiz_attempt_count + 1, 1)
        if score_meets_pass_threshold(best_score, pass_threshold_percent):
            row.quiz_passed = True

        row.completion_status = completion_status
        row.updated_at = now
        await self.db.flush()
        return row
