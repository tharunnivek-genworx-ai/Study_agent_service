# src/api/core/services/progress_services/trainee_progress_service.py
"""Progress service: trainee_node_progress reads and writes.

Owns all business logic for progress state. Other modules (study panel,
study material first-view tracking) call this service rather than touching
progress repositories directly.

Public operations:
  update_study_material_progress — PATCH scroll progress
  get_batch_node_progress        — batch read for panel / BFF orchestration
  mark_study_material_viewed     — first-open side effect when reading material
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.progress_exceptions.progress_exceptions import (
    NodeNotActiveException,
    ReadPercentOutOfRangeException,
    ReadPercentRegressionException,
    SpaceNotPublishedException,
    StudyMaterialNotPublishedException,
    TraineeNotEnrolledInSpaceException,
)
from src.api.core.services.progress_services.trainee_space_progress_service import (
    TraineeSpaceProgressService,
)
from src.api.data.models.postgres.progress_models.trainee_node_progress import (
    TraineeNodeProgress,
)
from src.api.data.repositories.progress_repositories.mentor_progress_repository import (
    MentorProgressRepository,
)
from src.api.data.repositories.progress_repositories.trainee_node_progress_repository import (
    TraineeNodeProgressRepository,
)
from src.api.data.repositories.trainee_quiz_repositories.trainee_quiz_repository import (
    TraineeQuizRepository,
)
from src.api.schemas.progress_schemas.trainee_progress_schema import (
    TraineeNodeProgressBatchItemOut,
    TraineeNodeProgressBatchOut,
    TraineeNodeProgressOut,
    TraineeProgressUpdateRequest,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_space_access,
    _assert_trainee,
    _get_node_and_assert_space_access,
)
from src.api.utils.trainee_progress_utils.completion import (
    compute_completion_status,
    compute_progress_percentage,
)


def _snapshot_from_row(
    row: TraineeNodeProgress,
    *,
    has_published_quiz: bool,
) -> TraineeNodeProgressBatchItemOut:
    """Map a DB row to the lightweight batch/panel snapshot DTO."""
    completion_status = compute_completion_status(
        study_material_completed=row.study_material_completed,
        quiz_passed=row.quiz_passed,
        study_material_read_percent=row.study_material_read_percent,
        quiz_attempt_count=row.quiz_attempt_count,
        has_published_quiz=has_published_quiz,
    )
    progress_percentage = compute_progress_percentage(
        study_material_completed=row.study_material_completed,
        quiz_passed=row.quiz_passed,
        has_published_quiz=has_published_quiz,
    )
    return TraineeNodeProgressBatchItemOut(
        node_id=row.node_id,
        study_material_read_percent=row.study_material_read_percent,
        study_material_completed=row.study_material_completed,
        quiz_passed=row.quiz_passed,
        quiz_attempt_count=row.quiz_attempt_count,
        completion_status=completion_status,
        progress_percentage=progress_percentage,
    )


def _empty_snapshot(node_id: UUID) -> TraineeNodeProgressBatchItemOut:
    """Default progress state when the trainee has never interacted with a node."""
    return TraineeNodeProgressBatchItemOut(node_id=node_id)


class TraineeProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TraineeNodeProgressRepository(session)
        self.guard_repo = MentorProgressRepository(session)
        self.quiz_repo = TraineeQuizRepository(session)

    async def get_batch_node_progress(
        self,
        *,
        node_ids: list[UUID],
        user_id: UUID,
        role: str,
    ) -> dict[UUID, TraineeNodeProgressBatchItemOut]:
        """Batch-read progress snapshots for panel assembly (Option 1 orchestrator).

        Returns a dict keyed by ``node_id``. Missing rows are filled with
        ``not_started`` defaults so callers never need null checks.
        """
        _assert_trainee(role)
        unique_ids = list(dict.fromkeys(node_ids))
        if not unique_ids:
            return {}

        rows = await self.repo.get_batch_by_trainee_and_nodes(user_id, unique_ids)
        quiz_node_ids = await self.quiz_repo.get_published_quiz_node_ids(unique_ids)
        return {
            node_id: _snapshot_from_row(
                rows[node_id],
                has_published_quiz=node_id in quiz_node_ids,
            )
            if node_id in rows
            else _empty_snapshot(node_id)
            for node_id in unique_ids
        }

    async def get_batch_node_progress_out(
        self,
        *,
        node_ids: list[UUID],
        user_id: UUID,
        role: str,
    ) -> TraineeNodeProgressBatchOut:
        """HTTP-facing wrapper around ``get_batch_node_progress``."""
        progress_map = await self.get_batch_node_progress(
            node_ids=node_ids, user_id=user_id, role=role
        )
        return TraineeNodeProgressBatchOut(node_progress=list(progress_map.values()))

    async def mark_study_material_viewed(
        self,
        *,
        node_id: UUID,
        user_id: UUID,
        role: str,
    ) -> None:
        """Record first material open — called when trainee loads full content."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        await self.repo.mark_study_material_viewed(user_id, node_id, node.space_id)
        await self.session.commit()

    async def update_study_material_progress(
        self,
        *,
        node_id: UUID,
        payload: TraineeProgressUpdateRequest,
        user_id: UUID,
        role: str,
    ) -> TraineeNodeProgressOut:
        """Upsert trainee_node_progress on a scroll event."""
        _assert_trainee(role)

        node = await self.guard_repo.get_node_by_id(node_id)
        if node is None or not node.is_active:
            raise NodeNotActiveException()

        space = await self.guard_repo.get_space_by_id(node.space_id)
        if space is None or not space.is_published or not space.is_active:
            raise SpaceNotPublishedException()

        is_member = await self.guard_repo.is_active_member(node.space_id, user_id)
        if not is_member:
            raise TraineeNotEnrolledInSpaceException()

        has_published_material = (
            await self.guard_repo.node_has_published_study_material(node_id)
        )
        if not has_published_material:
            raise StudyMaterialNotPublishedException()

        if payload.read_percent < 0 or payload.read_percent > 100:
            raise ReadPercentOutOfRangeException()

        progress_row = await self.guard_repo.get_node_progress(user_id, node_id)

        if (
            progress_row is not None
            and payload.read_percent < progress_row.study_material_read_percent
        ):
            raise ReadPercentRegressionException()

        study_material_completed = payload.read_percent == 100
        has_published_quiz = (
            await self.quiz_repo.get_published_quiz_by_node(node_id) is not None
        )
        progress_row = await self.guard_repo.upsert_node_progress(
            trainee_id=user_id,
            node_id=node_id,
            space_id=node.space_id,
            read_percent=payload.read_percent,
            study_material_completed=study_material_completed,
            has_published_quiz=has_published_quiz,
        )
        space_progress_service = TraineeSpaceProgressService(self.session)
        await space_progress_service.recompute_after_node_update(
            trainee_id=user_id,
            space_id=node.space_id,
        )
        # Refresh progress_row since the downstream recompute committed and expired it
        await self.session.refresh(progress_row)

        progress_percentage = compute_progress_percentage(
            study_material_completed=progress_row.study_material_completed,
            quiz_passed=progress_row.quiz_passed,
            has_published_quiz=has_published_quiz,
        )
        completion_status = compute_completion_status(
            study_material_completed=progress_row.study_material_completed,
            quiz_passed=progress_row.quiz_passed,
            study_material_read_percent=progress_row.study_material_read_percent,
            quiz_attempt_count=progress_row.quiz_attempt_count,
            has_published_quiz=has_published_quiz,
        )

        return TraineeNodeProgressOut(
            progress_id=progress_row.progress_id,
            trainee_id=progress_row.trainee_id,
            node_id=progress_row.node_id,
            space_id=progress_row.space_id,
            study_material_viewed=progress_row.study_material_viewed,
            first_viewed_at=progress_row.first_viewed_at,
            last_viewed_at=progress_row.last_viewed_at,
            study_material_read_percent=progress_row.study_material_read_percent,
            study_material_completed=progress_row.study_material_completed,
            quiz_best_score=progress_row.quiz_best_score,
            quiz_attempt_count=progress_row.quiz_attempt_count,
            quiz_passed=progress_row.quiz_passed,
            completion_status=completion_status,
            progress_percentage=progress_percentage,
            updated_at=progress_row.updated_at,
        )

    async def record_quiz_attempt_submission(
        self,
        *,
        trainee_id: UUID,
        node_id: UUID,
        space_id: UUID,
        score: float,
    ) -> None:
        """Update node progress after quiz submit (called by ``TraineeQuizService``).

        Also refreshes the space-level rollup to keep trainee-space progress in sync.
        """
        await self.repo.record_quiz_attempt_submission(
            trainee_id=trainee_id,
            node_id=node_id,
            space_id=space_id,
            score=score,
        )
        space_progress_service = TraineeSpaceProgressService(self.session)
        await space_progress_service.recompute_after_node_update(
            trainee_id=trainee_id,
            space_id=space_id,
        )
