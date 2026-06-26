# C:\CapStone\study_agent_service\src\api\data\repositories\progress_repositories\mentor_progress_repository.py
"""Repository for trainee_node_progress and trainee_space_progress.

Handles:
  - Node and space lookups needed by the service layer for guards
  - Membership check (delegated to space_trainees table)
  - Published study material existence check
  - trainee_node_progress: get, upsert
  - trainee_space_progress: get (read-only here; space-level rollup is
    written by quiz_service on attempt submission and by this service on
    study material completion)
  - Bulk reads for the mentor dashboard (all node progress for a space,
    all enrolled trainees with their space-level rollup, node metadata)

All methods are pure DB operations. No business logic lives here.
"""

from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.quiz_attempts import QuizAttempt
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.data.models.postgres.e_spaces_trees.espaces import ESpace
from src.api.data.models.postgres.e_spaces_trees.space_trainees import SpaceTrainee
from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.models.postgres.identity_refs.trainees import Trainee
from src.api.data.models.postgres.progress_models.trainee_node_progress import (
    TraineeNodeProgress,
)
from src.api.data.models.postgres.progress_models.trainee_space_progress import (
    TraineeSpaceProgress,
)
from src.api.utils.common_utils.time import utc_now as get_current_utc_time
from src.api.utils.trainee_progress_utils.completion import compute_completion_status


class MentorProgressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── Space / node lookups (guard support) ──────────────────────────────────

    async def get_space_by_id(self, space_id: UUID) -> ESpace | None:
        result = await self.db.execute(
            select(ESpace).where(ESpace.space_id == space_id)
        )
        return cast(ESpace | None, result.scalars().first())

    async def get_node_by_id(self, node_id: UUID) -> TopicNode | None:
        result = await self.db.execute(
            select(TopicNode).where(TopicNode.node_id == node_id)
        )
        return cast(TopicNode | None, result.scalars().first())

    async def is_active_member(self, space_id: UUID, trainee_id: UUID) -> bool:
        """Return True if the trainee has an active membership in the space."""
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

    async def node_has_published_study_material(self, node_id: UUID) -> bool:
        """Return True if the node has at least one published study material version."""
        result = await self.db.execute(
            select(func.count())
            .select_from(StudyMaterialVersion)
            .where(
                and_(
                    StudyMaterialVersion.node_id == node_id,
                    StudyMaterialVersion.is_published.is_(True),
                )
            )
        )
        return (result.scalar() or 0) > 0

    async def get_published_study_material_node_ids(self, space_id: UUID) -> set[UUID]:
        """Return active node ids in a space with published study material."""
        result = await self.db.execute(
            select(TopicNode.node_id)
            .select_from(TopicNode)
            .join(
                StudyMaterialVersion,
                and_(
                    StudyMaterialVersion.node_id == TopicNode.node_id,
                    StudyMaterialVersion.is_published.is_(True),
                ),
            )
            .where(
                and_(
                    TopicNode.space_id == space_id,
                    TopicNode.is_active.is_(True),
                )
            )
        )
        return {cast(UUID, node_id) for node_id in result.scalars().all()}

    # ── trainee_node_progress ─────────────────────────────────────────────────

    async def get_node_progress(
        self, trainee_id: UUID, node_id: UUID
    ) -> TraineeNodeProgress | None:
        """Fetch an existing progress row for (trainee_id, node_id), or None."""
        result = await self.db.execute(
            select(TraineeNodeProgress).where(
                and_(
                    TraineeNodeProgress.trainee_id == trainee_id,
                    TraineeNodeProgress.node_id == node_id,
                )
            )
        )
        return cast(TraineeNodeProgress | None, result.scalars().first())

    async def upsert_node_progress(
        self,
        *,
        trainee_id: UUID,
        node_id: UUID,
        space_id: UUID,
        read_percent: int,
        study_material_completed: bool,
        has_published_quiz: bool = True,
    ) -> TraineeNodeProgress:
        """Insert or update the trainee_node_progress row for a scroll event.

        On first interaction:
          - Creates the row with study_material_viewed=True,
            first_viewed_at=now, last_viewed_at=now.
        On subsequent calls:
          - Updates study_material_read_percent and last_viewed_at.
          - Sets study_material_completed=True when read_percent==100
            (monotonic — never sets it back to False here).

        quiz_passed and quiz_best_score are NOT touched here; they are
        owned by quiz_service on attempt submission.

        Space-level rollup (trainee_space_progress) is updated by a
        separate call to _update_space_progress_after_node_change when
        study_material_completed transitions to True for the first time.
        """
        now = get_current_utc_time()
        existing = await self.get_node_progress(trainee_id, node_id)

        if existing is None:
            row = TraineeNodeProgress(
                progress_id=uuid4(),
                trainee_id=trainee_id,
                node_id=node_id,
                space_id=space_id,
                study_material_viewed=True,
                first_viewed_at=now,
                last_viewed_at=now,
                study_material_read_percent=read_percent,
                study_material_completed=study_material_completed,
                quiz_best_score=None,
                quiz_attempt_count=0,
                quiz_passed=False,
                chat_session_count=0,
                completion_status=compute_completion_status(
                    study_material_completed=study_material_completed,
                    quiz_passed=False,
                    study_material_read_percent=read_percent,
                    quiz_attempt_count=0,
                    has_published_quiz=has_published_quiz,
                ),
                updated_at=now,
            )
            self.db.add(row)
            await self.db.commit()
            await self.db.refresh(row)
            return row

        # Monotonic guard: never lower a completed flag
        if not existing.study_material_completed and study_material_completed:
            existing.study_material_completed = True

        existing.study_material_read_percent = read_percent
        existing.study_material_viewed = True
        existing.last_viewed_at = now
        existing.updated_at = now
        existing.completion_status = compute_completion_status(
            study_material_completed=existing.study_material_completed,
            quiz_passed=existing.quiz_passed,
            study_material_read_percent=existing.study_material_read_percent,
            quiz_attempt_count=existing.quiz_attempt_count,
            has_published_quiz=has_published_quiz,
        )

        await self.db.commit()
        await self.db.refresh(existing)
        return existing

    # ── trainee_space_progress ────────────────────────────────────────────────

    async def get_space_progress(
        self, trainee_id: UUID, space_id: UUID
    ) -> TraineeSpaceProgress | None:
        """Fetch the space-level rollup row for a trainee, or None."""
        result = await self.db.execute(
            select(TraineeSpaceProgress).where(
                and_(
                    TraineeSpaceProgress.trainee_id == trainee_id,
                    TraineeSpaceProgress.space_id == space_id,
                )
            )
        )
        return cast(TraineeSpaceProgress | None, result.scalars().first())

    # ── Mentor dashboard bulk reads ───────────────────────────────────────────

    async def count_total_nodes(self, space_id: UUID) -> int:
        """Recompute the live count of active nodes with >= 1 published study
        material version for the space (EC-23 — always fresh, not from cache).

        Mirrors the recompute query in TDD §3.2.4:
          SELECT COUNT(DISTINCT tn.node_id) FROM topic_nodes tn
          INNER JOIN study_material_versions smv
            ON smv.node_id = tn.node_id AND smv.is_published = TRUE
          WHERE tn.space_id = :space_id AND tn.is_active = TRUE
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
            .where(
                and_(
                    TopicNode.space_id == space_id,
                    TopicNode.is_active.is_(True),
                )
            )
        )
        return int(result.scalar() or 0)

    async def count_active_enrolled_trainees(self, space_id: UUID) -> int:
        """Count active enrolled trainees in the space."""
        result = await self.db.execute(
            select(func.count(SpaceTrainee.trainee_id)).where(
                and_(
                    SpaceTrainee.space_id == space_id,
                    SpaceTrainee.is_active.is_(True),
                )
            )
        )
        return int(result.scalar() or 0)

    async def list_enrolled_trainees_with_space_progress(
        self, space_id: UUID
    ) -> list[tuple[Trainee, TraineeSpaceProgress | None]]:
        """Return all active enrolled trainees joined with their space-level
        progress row (outer join — trainees with no activity have None).

        Used to build the mentor dashboard trainee list.
        """
        result = await self.db.execute(
            select(Trainee, TraineeSpaceProgress)
            .join(
                SpaceTrainee,
                and_(
                    SpaceTrainee.trainee_id == Trainee.trainee_id,
                    SpaceTrainee.space_id == space_id,
                    SpaceTrainee.is_active.is_(True),
                ),
            )
            .outerjoin(
                TraineeSpaceProgress,
                and_(
                    TraineeSpaceProgress.trainee_id == Trainee.trainee_id,
                    TraineeSpaceProgress.space_id == space_id,
                ),
            )
            .order_by(Trainee.full_name)
        )
        return [
            (cast(Trainee, row[0]), cast(TraineeSpaceProgress | None, row[1]))
            for row in result.all()
        ]

    async def list_all_node_progress_for_space(
        self, space_id: UUID
    ) -> list[TraineeNodeProgress]:
        """Fetch all trainee_node_progress rows for the space in a single query.

        Used by the mentor dashboard to avoid N+1 queries when assembling
        per-node summaries for every enrolled trainee.
        """
        result = await self.db.execute(
            select(TraineeNodeProgress).where(TraineeNodeProgress.space_id == space_id)
        )
        return list(result.scalars().all())

    async def list_nodes_for_space(self, space_id: UUID) -> list[TopicNode]:
        """Fetch all topic_nodes for the space (active and inactive) so the
        mentor dashboard can render archived nodes with an '(Archived)' label.

        is_active is included in TraineeNodeProgressSummaryOut so the frontend
        can distinguish live nodes from archived ones (EC-3).
        """
        result = await self.db.execute(
            select(TopicNode)
            .where(TopicNode.space_id == space_id)
            .order_by(TopicNode.level, TopicNode.order_index)
        )
        return list(result.scalars().all())

    # ── Unpublish engagement counts ───────────────────────────────────────────

    async def count_trainees_with_read_progress(
        self, node_id: UUID, space_id: UUID
    ) -> int:
        """Count distinct enrolled trainees who have read at least 1 % of the node's
        study material (study_material_read_percent > 0).

        Used to populate the engagement impact block in the SM unpublish preview.
        """
        result = await self.db.execute(
            select(func.count(TraineeNodeProgress.trainee_id.distinct())).where(
                and_(
                    TraineeNodeProgress.node_id == node_id,
                    TraineeNodeProgress.space_id == space_id,
                    TraineeNodeProgress.study_material_read_percent > 0,
                )
            )
        )
        return int(result.scalar() or 0)

    async def count_trainees_with_quiz_attempts(self, node_id: UUID) -> int:
        """Count distinct trainees with any quiz attempt on the node (live or historical).

        Used to populate the engagement impact block in SM and quiz unpublish previews.
        """
        result = await self.db.execute(
            select(func.count(QuizAttempt.trainee_id.distinct())).where(
                QuizAttempt.node_id == node_id
            )
        )
        return int(result.scalar() or 0)
