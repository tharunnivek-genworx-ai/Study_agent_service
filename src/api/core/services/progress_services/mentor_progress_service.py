# C:\CapStone\study_agent_service\src\api\core\services\progress_services\mentor_progress_service.py
"""Progress service: all business logic for trainee_node_progress and
trainee_space_progress.

Responsibilities:
  get_space_progress — build MentorSpaceProgressOut by joining
    trainee_space_progress + trainee_node_progress + topic_nodes + trainees
    for every active enrolled trainee in the space.
  recompute_space_progress_for_space — fan-out space-level progress recompute
    for all enrolled trainees after mentor publish/unpublish/archive actions
    (EC-23). This is the authoritative entry point for mentor-triggered
    recomputes; it validates ownership, then delegates to the
    recompute_all_trainees_space_progress utility.

Progress model (TDD §3.2.4):
  Node-level:
    study_material portion = 50%  (study_material_completed=True)
    quiz portion           = 50%  (quiz_passed=True)
    completion_status:
      'not_started'  — no interaction yet
      'in_progress'  — at least one component partially satisfied
      'completed'    — both components done

  Space-level:
    total_nodes    = active nodes with >= 1 published study material version
    completed_nodes = nodes where this trainee's completion_status='completed'
    overall_progress_percentage = round((completed_nodes / total_nodes) * 100)

Edge cases enforced here:
  EC-3   — Archived node: excluded from total_nodes on next recompute; existing
             node-progress rows are preserved read-only.
  EC-13  — Removed trainee: rejects writes with TraineeNotEnrolledInSpaceException.
  EC-20  — Quiz publish/unpublish: all trainees' completion requirements change;
             recompute_space_progress_for_space is called from quiz_service after
             each quiz publish/unpublish so the cached rollup reflects the new
             completion rules immediately.
  EC-21  — No published quiz: reading complete counts as fully done (100%).
           When a quiz is later published, completion drops to in-progress at
           50% until the quiz is passed.
  EC-22  — quiz_best_score stays MAX(); quiz_passed stays True once achieved.
             Enforced in quiz_service; this service reads the result.
  EC-23  — total_nodes recomputed at query time via JOIN on study_material_versions;
             cached trainee_space_progress.total_nodes is refreshed for all
             enrolled trainees whenever the mentor publishes or unpublishes
             study material.
  EC-27  — Space ownership resolved via COALESCE(transferred_to_mentor_id,
             mentor_id) for all guarded methods.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.space_node_exceptions.space_exceptions import (
    SpaceForbiddenException,
    SpaceNotFoundException,
)
from src.api.data.repositories.progress_repositories.mentor_progress_repository import (
    MentorProgressRepository,
)
from src.api.data.repositories.trainee_quiz_repositories.trainee_quiz_repository import (
    TraineeQuizRepository,
)
from src.api.schemas.progress_schemas.mentor_progress_schema import (
    MentorSpaceProgressOut,
    MentorSpaceProgressSummaryOut,
)
from src.api.schemas.progress_schemas.trainee_progress_schema import (
    TraineeNodeProgressSummaryOut,
    TraineeSpaceSummaryOut,
)
from src.api.utils.mentor_progress_utils.space_recompute import (
    recompute_all_trainees_space_progress,
)
from src.api.utils.trainee_progress_utils.completion import (
    compute_completion_status,
    compute_progress_percentage,
)


def _assert_mentor(role: str) -> None:
    if role != "mentor":
        raise SpaceForbiddenException()


class MentorProgressService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_space_progress(
        self,
        *,
        space_id: UUID,
        user_id: UUID,
        role: str,
    ) -> MentorSpaceProgressOut:
        """Build the full per-trainee progress dashboard for a space.

        Guards:
          1. Role must be 'mentor'.
          2. Space must exist and be active.
          3. Caller must be the effective owner of the space
             (COALESCE(transferred_to_mentor_id, mentor_id), EC-27).

        EC-23: total_nodes is recomputed at query time from the repo rather
        than read from the cached trainee_space_progress.total_nodes, so
        tree/publish changes are reflected immediately.
        """
        _assert_mentor(role)

        repo = MentorProgressRepository(self.session)

        space = await repo.get_space_by_id(space_id)
        if space is None or not space.is_active:
            raise SpaceNotFoundException()

        # Effective owner check (EC-27)
        effective_owner_id = (
            space.transferred_to_mentor_id
            if space.transferred_to_mentor_id is not None
            else space.mentor_id
        )
        if effective_owner_id != user_id:
            raise SpaceForbiddenException()

        # Recompute live total_nodes from DB (EC-23)
        total_nodes = await repo.count_total_nodes(space_id)

        # Fetch all active enrolled trainees with their space-level rollup
        enrolled_trainees = await repo.list_enrolled_trainees_with_space_progress(
            space_id
        )

        # Fetch all node-level progress rows for the space in one query,
        # keyed by trainee_id for efficient per-trainee assembly below
        all_node_progress = await repo.list_all_node_progress_for_space(space_id)
        node_progress_by_trainee: dict[UUID, list] = {}
        for row in all_node_progress:
            node_progress_by_trainee.setdefault(row.trainee_id, []).append(row)

        # Fetch active node metadata (id, title, level, is_active) for the space
        active_nodes = await repo.list_nodes_for_space(space_id)
        node_meta: dict[UUID, tuple[str, int, bool]] = {
            n.node_id: (n.title, n.level, n.is_active) for n in active_nodes
        }
        quiz_repo = TraineeQuizRepository(self.session)
        quiz_node_ids = await quiz_repo.get_published_quiz_node_ids(
            list(node_meta.keys())
        )

        trainees_with_no_activity = 0
        trainee_summaries: list[TraineeSpaceSummaryOut] = []

        for trainee, space_progress in enrolled_trainees:
            trainee_node_rows = node_progress_by_trainee.get(trainee.trainee_id, [])

            # Build per-node summaries
            node_summaries: list[TraineeNodeProgressSummaryOut] = []
            for np_row in trainee_node_rows:
                title, level, is_active = node_meta.get(
                    np_row.node_id, ("(Unknown)", 1, False)
                )
                has_published_quiz = np_row.node_id in quiz_node_ids
                progress_pct = compute_progress_percentage(
                    study_material_completed=np_row.study_material_completed,
                    quiz_passed=np_row.quiz_passed,
                    has_published_quiz=has_published_quiz,
                )
                c_status = compute_completion_status(
                    study_material_completed=np_row.study_material_completed,
                    quiz_passed=np_row.quiz_passed,
                    study_material_read_percent=np_row.study_material_read_percent,
                    quiz_attempt_count=np_row.quiz_attempt_count,
                    has_published_quiz=has_published_quiz,
                )
                node_summaries.append(
                    TraineeNodeProgressSummaryOut(
                        node_id=np_row.node_id,
                        node_title=title,
                        node_level=level,
                        is_active=is_active,
                        study_material_completed=np_row.study_material_completed,
                        study_material_read_percent=np_row.study_material_read_percent,
                        quiz_passed=np_row.quiz_passed,
                        quiz_best_score=np_row.quiz_best_score,
                        quiz_attempt_count=np_row.quiz_attempt_count,
                        completion_status=c_status,
                        progress_percentage=progress_pct,
                        last_viewed_at=np_row.last_viewed_at,
                        updated_at=np_row.updated_at,
                    )
                )

            completed_nodes = (
                space_progress.completed_nodes if space_progress is not None else 0
            )
            overall_score_avg = (
                space_progress.overall_score_avg if space_progress is not None else None
            )
            last_activity_at = (
                space_progress.last_activity_at if space_progress is not None else None
            )

            overall_progress_pct = (
                round((completed_nodes / total_nodes) * 100) if total_nodes > 0 else 0
            )

            # Track trainees with zero activity for the dashboard header count
            if not node_summaries:
                trainees_with_no_activity += 1

            trainee_summaries.append(
                TraineeSpaceSummaryOut(
                    trainee_id=trainee.trainee_id,
                    trainee_full_name=trainee.full_name,
                    trainee_email=trainee.email,
                    total_nodes=total_nodes,
                    completed_nodes=completed_nodes,
                    overall_score_avg=overall_score_avg,
                    overall_progress_percentage=overall_progress_pct,
                    last_activity_at=last_activity_at,
                    node_progress=node_summaries,
                )
            )

        # Order by overall_progress_percentage DESC (most advanced first)
        trainee_summaries.sort(
            key=lambda t: t.overall_progress_percentage, reverse=True
        )

        return MentorSpaceProgressOut(
            space_id=space_id,
            space_name=space.space_name,
            total_nodes=total_nodes,
            total_enrolled_trainees=len(trainee_summaries),
            trainees_with_no_activity=trainees_with_no_activity,
            trainees=trainee_summaries,
        )

    async def recompute_space_progress_for_space(
        self,
        *,
        space_id: UUID,
        user_id: UUID,
        role: str,
    ) -> None:
        """Fan-out space-progress recompute for all enrolled trainees (EC-23).

        Called by mentor-triggered actions that change what counts as a
        learning unit or how completion is determined:
          - Study material published / unpublished  (changes total_nodes)
          - Quiz published / unpublished (EC-20)    (changes completion rules)
          - Topic node archived / unarchived         (changes total_nodes)

        Guards:
          1. Role must be 'mentor'.
          2. Space must exist and be active.
          3. Caller must be the effective owner of the space (EC-27).

        The actual per-trainee recompute is delegated to
        ``recompute_all_trainees_space_progress`` in mentor_progress_utils.
        Individual trainee failures are logged and skipped — the caller's own
        commit is not affected.
        """
        _assert_mentor(role)

        repo = MentorProgressRepository(self.session)
        space = await repo.get_space_by_id(space_id)
        if space is None or not space.is_active:
            raise SpaceNotFoundException()

        # Effective owner check (EC-27)
        effective_owner_id = (
            space.transferred_to_mentor_id
            if space.transferred_to_mentor_id is not None
            else space.mentor_id
        )
        if effective_owner_id != user_id:
            raise SpaceForbiddenException()

        await recompute_all_trainees_space_progress(self.session, space_id=space_id)

    async def get_space_progress_summary(
        self,
        *,
        space_id: UUID,
        user_id: UUID,
        role: str,
    ) -> MentorSpaceProgressSummaryOut:
        """Get lightweight space progress summary (total nodes and enrolled trainees).

        Guards:
          1. Role must be 'mentor'.
          2. Space must exist and be active.
          3. Caller must be the effective owner of the space (EC-27).
        """
        _assert_mentor(role)

        repo = MentorProgressRepository(self.session)
        space = await repo.get_space_by_id(space_id)
        if space is None or not space.is_active:
            raise SpaceNotFoundException()

        # Effective owner check (EC-27)
        effective_owner_id = (
            space.transferred_to_mentor_id
            if space.transferred_to_mentor_id is not None
            else space.mentor_id
        )
        if effective_owner_id != user_id:
            raise SpaceForbiddenException()

        # Recompute live total_nodes from DB (EC-23)
        total_nodes = await repo.count_total_nodes(space_id)

        # Count active enrolled trainees
        total_enrolled = await repo.count_active_enrolled_trainees(space_id)

        return MentorSpaceProgressSummaryOut(
            space_id=space_id,
            space_name=space.space_name,
            total_nodes=total_nodes,
            total_enrolled_trainees=total_enrolled,
        )
