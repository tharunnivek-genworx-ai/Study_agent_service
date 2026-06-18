# src/api/data/repositories/progress_repositories/trainee_space_progress_repository.py
"""Repository for trainee_space_progress recompute writes and supporting reads.

count_total_nodes already lives on MentorProgressRepository — this file does
not duplicate it. This repository owns only the trainee-scoped pieces:
completed-node count, score average, last activity, and the upsert write.

All methods flush only; the caller (TraineeSpaceProgressService) controls
the commit boundary for the recompute operation.
"""

from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.models.postgres.progress_models.trainee_node_progress import (
    TraineeNodeProgress,
)
from src.api.data.models.postgres.progress_models.trainee_space_progress import (
    TraineeSpaceProgress,
)
from src.api.utils.common_utils.time import utc_now


class TraineeSpaceProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_by_trainee_and_space(
        self, trainee_id: UUID, space_id: UUID
    ) -> TraineeSpaceProgress | None:
        result = await self.db.execute(
            select(TraineeSpaceProgress).where(
                and_(
                    TraineeSpaceProgress.trainee_id == trainee_id,
                    TraineeSpaceProgress.space_id == space_id,
                )
            )
        )
        return cast(TraineeSpaceProgress | None, result.scalars().first())

    async def count_completed_nodes(self, *, trainee_id: UUID, space_id: UUID) -> int:
        """Active, published-material nodes where this trainee's
        completion_status = 'completed'. Mirrors the filter in
        MentorProgressRepository.count_total_nodes, narrowed to this
        trainee via an inner join on trainee_node_progress.
        """
        result = await self.db.execute(
            select(func.count(TopicNode.node_id.distinct()))
            .select_from(TopicNode)
            .join(
                StudyMaterialVersion,
                and_(
                    StudyMaterialVersion.node_id == TopicNode.node_id,
                    StudyMaterialVersion.is_published.is_(True),
                ),
            )
            .join(
                TraineeNodeProgress,
                and_(
                    TraineeNodeProgress.node_id == TopicNode.node_id,
                    TraineeNodeProgress.trainee_id == trainee_id,
                ),
            )
            .where(
                and_(
                    TopicNode.space_id == space_id,
                    TopicNode.is_active.is_(True),
                    TraineeNodeProgress.completion_status == "completed",
                )
            )
        )
        return int(result.scalar() or 0)

    async def compute_score_average(
        self, *, trainee_id: UUID, space_id: UUID
    ) -> float | None:
        """Average quiz_best_score across all nodes the trainee has
        attempted in this space. None if no quiz attempts exist yet.
        """
        result = await self.db.execute(
            select(func.avg(TraineeNodeProgress.quiz_best_score)).where(
                and_(
                    TraineeNodeProgress.trainee_id == trainee_id,
                    TraineeNodeProgress.space_id == space_id,
                    TraineeNodeProgress.quiz_best_score.is_not(None),
                )
            )
        )
        avg_score = result.scalar()
        return float(avg_score) if avg_score is not None else None

    async def get_last_activity_at(
        self, *, trainee_id: UUID, space_id: UUID
    ) -> datetime | None:
        result = await self.db.execute(
            select(func.max(TraineeNodeProgress.updated_at)).where(
                and_(
                    TraineeNodeProgress.trainee_id == trainee_id,
                    TraineeNodeProgress.space_id == space_id,
                )
            )
        )
        return cast(datetime | None, result.scalar())

    async def upsert_space_progress(
        self,
        *,
        trainee_id: UUID,
        space_id: UUID,
        total_nodes: int,
        completed_nodes: int,
        overall_score_avg: float | None,
        last_activity_at: datetime | None,
    ) -> TraineeSpaceProgress:
        row = await self.get_by_trainee_and_space(trainee_id, space_id)
        now = utc_now()

        if row is None:
            row = TraineeSpaceProgress(
                space_progress_id=uuid4(),
                trainee_id=trainee_id,
                space_id=space_id,
            )
            self.db.add(row)

        row.total_nodes = total_nodes
        row.completed_nodes = completed_nodes
        row.overall_score_avg = overall_score_avg
        row.last_activity_at = last_activity_at
        row.updated_at = now

        await self.db.flush()
        return row
