# src/api/core/services/progress_services/trainee_space_progress_service.py
"""Progress service: trainee_space_progress reads and recompute.

Owns business logic for the space-level rollup. Two public entry points:

  get_own_space_progress      — trainee self-view read
                                 (GET /trainee/spaces/:id/progress)
  recompute_after_node_update — called by TraineeProgressService after a
                                 node progress write (scroll update or quiz
                                 submit) so the rollup never goes stale
                                 between reads.

Reuses MentorProgressRepository for node/space lookups, the live
count_total_nodes query, and node_progress listing — it already owns those
queries; this service does not duplicate them. TraineeQuizRepository is
reused for published-quiz lookups, matching how TraineeProgressService
already sources that information.

EC-23: total_nodes/completed_nodes are recomputed from source tables rather
than incremented, so archived nodes (EC-3) and quiz resets (EC-20) are always
reflected correctly without separate patch logic.

Transaction note: recompute_after_node_update commits independently of the
node-progress write that triggers it (MentorProgressRepository.upsert_node_progress
and TraineeNodeProgressRepository.record_quiz_attempt_submission each own
their own commit/flush already). This is two small separate transactions
rather than one atomic transaction — acceptable here since the rollup is a
derived read-model that EC-23 already treats as eventually-consistent
("stale reads are bounded by polling frequency").
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.progress_exceptions.progress_exceptions import (
    SpaceProgressNotFoundException,
    SpaceProgressRecomputeFailedException,
    TraineeNotEnrolledInSpaceException,
)
from src.api.data.repositories.progress_repositories.mentor_progress_repository import (
    MentorProgressRepository,
)
from src.api.data.repositories.progress_repositories.trainee_node_progress_repository import (
    TraineeNodeProgressRepository,
)
from src.api.data.repositories.progress_repositories.trainee_space_progress_repository import (
    TraineeSpaceProgressRepository,
)
from src.api.data.repositories.trainee_quiz_repositories.trainee_quiz_repository import (
    TraineeQuizRepository,
)
from src.api.schemas.progress_schemas.trainee_progress_schema import (
    TraineeNodeProgressSummaryOut,
    TraineeOwnSpaceProgressOut,
)
from src.api.utils.space_node_utils.node_role_assert import _assert_trainee
from src.api.utils.trainee_progress_utils.completion import (
    compute_completion_status,
    compute_progress_percentage,
)
from src.api.utils.trainee_progress_utils.space_progress_presenter import (
    to_score_percentage,
)


class TraineeSpaceProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.guard_repo = MentorProgressRepository(session)
        self.space_repo = TraineeSpaceProgressRepository(session)
        self.node_repo = TraineeNodeProgressRepository(session)
        self.quiz_repo = TraineeQuizRepository(session)

    async def get_own_space_progress(
        self,
        *,
        space_id: UUID,
        user_id: UUID,
        role: str,
    ) -> TraineeOwnSpaceProgressOut:
        """Trainee self-view rollup. Read-only — does not trigger recompute.

        Relies on the rollup row kept fresh by recompute_after_node_update.
        If no row exists yet (trainee enrolled but never opened any
        material), a zeroed default is returned rather than raising,
        since "no activity" is a valid state, not an error.
        """
        _assert_trainee(role)

        space = await self.guard_repo.get_space_by_id(space_id)
        if space is None or not space.is_active:
            raise SpaceProgressNotFoundException()

        is_member = await self.guard_repo.is_active_member(space_id, user_id)
        if not is_member:
            raise TraineeNotEnrolledInSpaceException()

        # Active nodes with >= 1 published study material version, scoped
        # to this space.
        all_nodes = await self.guard_repo.list_nodes_for_space(space_id)
        published_node_ids = (
            await self.guard_repo.get_published_study_material_node_ids(space_id)
        )
        eligible_nodes = [
            node
            for node in all_nodes
            if node.is_active and node.node_id in published_node_ids
        ]
        eligible_node_ids = [node.node_id for node in eligible_nodes]

        quiz_node_ids = await self.quiz_repo.get_published_quiz_node_ids(
            eligible_node_ids
        )

        # Mirrors get_batch_by_trainee_and_nodes pattern: query only this trainee
        # and index by node_id to avoid scanning other trainees' rows.
        progress_by_node = await self.node_repo.get_batch_by_trainee_and_nodes(
            user_id, eligible_node_ids
        )

        node_progress: list[TraineeNodeProgressSummaryOut] = []
        for node in eligible_nodes:
            row = progress_by_node.get(node.node_id)
            has_published_quiz = node.node_id in quiz_node_ids

            study_material_completed = row.study_material_completed if row else False
            study_material_read_percent = row.study_material_read_percent if row else 0
            quiz_passed = row.quiz_passed if row else False
            quiz_best_score = row.quiz_best_score if row else None
            quiz_attempt_count = row.quiz_attempt_count if row else 0

            completion_status = compute_completion_status(
                study_material_completed=study_material_completed,
                quiz_passed=quiz_passed,
                study_material_read_percent=study_material_read_percent,
                quiz_attempt_count=quiz_attempt_count,
                has_published_quiz=has_published_quiz,
            )
            progress_percentage = compute_progress_percentage(
                study_material_completed=study_material_completed,
                quiz_passed=quiz_passed,
                has_published_quiz=has_published_quiz,
            )

            node_progress.append(
                TraineeNodeProgressSummaryOut(
                    node_id=node.node_id,
                    node_title=node.title,
                    node_level=node.level,
                    is_active=node.is_active,
                    study_material_completed=study_material_completed,
                    study_material_read_percent=study_material_read_percent,
                    quiz_passed=quiz_passed,
                    quiz_best_score=quiz_best_score,
                    quiz_attempt_count=quiz_attempt_count,
                    completion_status=completion_status,
                    progress_percentage=progress_percentage,
                    last_viewed_at=row.last_viewed_at if row else None,
                    updated_at=row.updated_at if row else space.updated_at,
                )
            )

        total_nodes = len(eligible_nodes)
        completed_nodes = sum(
            1 for item in node_progress if item.completion_status == "completed"
        )
        overall_score_avg = await self.space_repo.compute_score_average(
            trainee_id=user_id, space_id=space_id
        )
        last_activity_at = await self.space_repo.get_last_activity_at(
            trainee_id=user_id, space_id=space_id
        )
        overall_progress_percentage = (
            round((completed_nodes / total_nodes) * 100) if total_nodes > 0 else 0
        )

        return TraineeOwnSpaceProgressOut(
            space_id=space.space_id,
            space_name=space.space_name,
            trainee_id=user_id,
            total_nodes=total_nodes,
            completed_nodes=completed_nodes,
            overall_progress_percentage=overall_progress_percentage,
            overall_score_avg=overall_score_avg,
            overall_score_percentage=to_score_percentage(overall_score_avg),
            last_activity_at=last_activity_at,
            node_progress=node_progress,
        )

    async def recompute_after_node_update(
        self,
        *,
        trainee_id: UUID,
        space_id: UUID,
    ) -> None:
        """Recompute and upsert the trainee_space_progress row.

        Called by TraineeProgressService after a node progress write
        (scroll update or quiz submission). Commits independently — see
        module docstring transaction note.
        """
        try:
            total_nodes = await self.guard_repo.count_total_nodes(space_id)
            completed_nodes = await self.space_repo.count_completed_nodes(
                trainee_id=trainee_id, space_id=space_id
            )
            overall_score_avg = await self.space_repo.compute_score_average(
                trainee_id=trainee_id, space_id=space_id
            )
            last_activity_at = await self.space_repo.get_last_activity_at(
                trainee_id=trainee_id, space_id=space_id
            )

            await self.space_repo.upsert_space_progress(
                trainee_id=trainee_id,
                space_id=space_id,
                total_nodes=total_nodes,
                completed_nodes=completed_nodes,
                overall_score_avg=overall_score_avg,
                last_activity_at=last_activity_at,
            )
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            raise SpaceProgressRecomputeFailedException() from exc
