"""Live space-level rollup for a single trainee.

Single source of truth for total_nodes / completed_nodes / overall % on reads
and cache recompute. Derives completion from current published content state
rather than stale stored ``completion_status`` values.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.repositories import (
    MentorProgressRepository,
    TraineeNodeProgressRepository,
    TraineeQuizRepository,
)
from src.api.utils.trainee_progress_utils.completion import compute_completion_status


async def compute_trainee_space_rollup(
    session: AsyncSession,
    *,
    trainee_id: UUID,
    space_id: UUID,
) -> tuple[int, int, int]:
    """Return ``(total_nodes, completed_nodes, overall_progress_percentage)``.

    Eligible nodes are active topic nodes with at least one published study
    material version. A node counts as completed when
    ``compute_completion_status`` returns ``"completed"`` under today's
    published-quiz rules.
    """
    guard_repo = MentorProgressRepository(session)
    node_repo = TraineeNodeProgressRepository(session)
    quiz_repo = TraineeQuizRepository(session)

    eligible_node_ids = list(
        await guard_repo.get_published_study_material_node_ids(space_id)
    )
    total_nodes = len(eligible_node_ids)
    if total_nodes == 0:
        return 0, 0, 0

    quiz_node_ids = await quiz_repo.get_published_quiz_node_ids(eligible_node_ids)
    progress_by_node = await node_repo.get_batch_by_trainee_and_nodes(
        trainee_id, eligible_node_ids
    )

    completed_nodes = 0
    for node_id in eligible_node_ids:
        row = progress_by_node.get(node_id)
        status = compute_completion_status(
            study_material_completed=row.study_material_completed if row else False,
            quiz_passed=row.quiz_passed if row else False,
            study_material_read_percent=row.study_material_read_percent if row else 0,
            quiz_attempt_count=row.quiz_attempt_count if row else 0,
            has_published_quiz=node_id in quiz_node_ids,
        )
        if status == "completed":
            completed_nodes += 1

    overall_pct = round((completed_nodes / total_nodes) * 100)
    return total_nodes, completed_nodes, overall_pct
