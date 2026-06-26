# C:\CapStone\study_agent_service\src\api\utils\mentor_progress_utils\space_recompute.py
"""
Bulk space-progress recomputation utilities for mentor-triggered events.

When a mentor publishes or unpublishes study material, or publishes/unpublishes
a quiz, the ``total_nodes`` denominator used in every trainee's space-level
progress percentage changes. This module provides the function that fans the
recompute out across all actively enrolled trainees in the affected space.

Trigger points (EC-23):
  - study_material publish / unpublish
    → changes which nodes count as "learning units" (total_nodes)
    → fan-out: all enrolled trainees
  - quiz publish / unpublish (EC-20)
    → changes completion requirements per node
    → fan-out: all enrolled trainees who have touched the affected node
  - topic node archive (is_active → False)
    → removes node from total_nodes
    → fan-out: all enrolled trainees

Design notes:
  - Uses ``MentorProgressRepository`` to enumerate enrolled trainees cheaply
    (single query), then calls ``TraineeSpaceProgressService.recompute_after_node_update``
    for each trainee. The service already owns the per-trainee recompute logic
    (count_total_nodes, count_completed_nodes, score average, last_activity_at)
    and the final upsert into trainee_space_progress.
  - Recompute failures for individual trainees are logged and swallowed so that
    one bad row never blocks the rest of the fan-out or the caller's own commit.
  - The function is intentionally fire-and-forget safe: the caller (publish_ops /
    quiz_service / mentor_progress_service) commits its own change first, then
    calls this. The recompute itself commits per-trainee via
    TraineeSpaceProgressService.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.progress_services.trainee_space_progress_service import (
    TraineeSpaceProgressService,
)
from src.api.data.repositories.progress_repositories.mentor_progress_repository import (
    MentorProgressRepository,
)

logger = logging.getLogger(__name__)


async def recompute_all_trainees_space_progress(
    session: AsyncSession,
    *,
    space_id: UUID,
) -> None:
    """Fan out a space-progress recompute to every actively enrolled trainee.

    Called after any mentor action that changes the effective total_nodes count
    or the completion requirements for nodes in the space:
      - Study material published / unpublished     (changes total_nodes)
      - Quiz published / unpublished (EC-20)       (changes completion requirements)
      - Topic node archived / restored             (changes total_nodes)

    Each trainee's ``trainee_space_progress`` row is recomputed using fresh
    DB queries (count_total_nodes, count_completed_nodes, score average,
    last_activity_at) so the mentor dashboard always reflects the latest state.

    Failures for individual trainees are logged and skipped — a single bad
    trainee row never aborts the entire fan-out.

    Args:
        session:  The async SQLAlchemy session scoped to the current request.
        space_id: The space whose enrolled trainees should be recomputed.
    """
    mentor_repo = MentorProgressRepository(session)
    enrolled = await mentor_repo.list_enrolled_trainees_with_space_progress(space_id)

    if not enrolled:
        logger.debug(
            "recompute_all_trainees_space_progress: no enrolled trainees for space=%s",
            space_id,
        )
        return

    space_svc = TraineeSpaceProgressService(session)
    recomputed = 0
    failed = 0

    trainee_ids = [trainee.trainee_id for trainee, _space_progress in enrolled]

    for trainee_id in trainee_ids:
        try:
            await space_svc.recompute_after_node_update(
                trainee_id=trainee_id,
                space_id=space_id,
            )
            recomputed += 1
        except Exception:
            failed += 1
            logger.warning(
                "recompute_all_trainees_space_progress: failed for "
                "trainee_id=%s space_id=%s",
                trainee_id,
                space_id,
                exc_info=True,
            )

    logger.info(
        "recompute_all_trainees_space_progress: space=%s recomputed=%d failed=%d",
        space_id,
        recomputed,
        failed,
    )
