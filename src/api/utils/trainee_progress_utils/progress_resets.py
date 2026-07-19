"""Batch progress resets when active study material or quiz content changes.

M4a — SM supersede: reset read progress for all trainees on the node.
M4b — EC-20 quiz publish: reset quiz_passed while preserving quiz_best_score.

Both paths update stored ``completion_status`` and fan out space-progress
recompute so ``count_completed_nodes`` stays accurate.

Durable unlock policy (progressive subtopic unlocking):
  C1/C2 — These resets MUST NOT delete ``trainee_node_unlocks``. Children stay
          usable after a parent reading or quiz_passed reset.
  C6    — Parent SM unpublish is handled by resolve rules (gate drops); do not
          revoke child grants or reset child progress here.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.progress_models.trainee_node_progress import (
    TraineeNodeProgress,
)
from src.api.utils.common_utils import utc_now
from src.api.utils.mentor_progress_utils.space_recompute import (
    recompute_all_trainees_space_progress,
)

logger = logging.getLogger(__name__)


def _completion_after_read_reset() -> Any:
    """Derive status after read fields are zeroed (quiz fields unchanged)."""
    return case(
        (TraineeNodeProgress.quiz_attempt_count > 0, "in_progress"),
        else_="not_started",
    )


def _completion_after_quiz_passed_reset(*, has_published_quiz: bool) -> Any:
    """Derive status after quiz_passed is cleared (read fields unchanged)."""
    if has_published_quiz:
        return case(
            (
                (TraineeNodeProgress.study_material_read_percent > 0)
                | (TraineeNodeProgress.quiz_attempt_count > 0)
                | (TraineeNodeProgress.study_material_completed.is_(True)),
                "in_progress",
            ),
            else_="not_started",
        )
    return case(
        (TraineeNodeProgress.study_material_completed.is_(True), "completed"),
        (TraineeNodeProgress.study_material_read_percent > 0, "in_progress"),
        else_="not_started",
    )


async def reset_node_read_progress_for_all_trainees(
    session: AsyncSession,
    *,
    node_id: UUID,
    space_id: UUID,
    has_published_quiz: bool,  # noqa: ARG001 — reserved for future nuanced rules
) -> int:
    """Reset SM read fields for every trainee progress row on *node_id*.

    Preserves ``first_viewed_at`` / ``last_viewed_at`` for audit. Does not
    touch quiz fields. Recomputes ``completion_status`` in bulk.
    """
    now = utc_now()
    result = await session.execute(
        update(TraineeNodeProgress)
        .where(
            and_(
                TraineeNodeProgress.node_id == node_id,
                TraineeNodeProgress.space_id == space_id,
            )
        )
        .values(
            study_material_read_percent=0,
            study_material_completed=False,
            completion_status=_completion_after_read_reset(),
            updated_at=now,
        )
    )
    updated = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()

    try:
        await recompute_all_trainees_space_progress(session, space_id=space_id)
    except Exception:
        logger.warning(
            "reset_node_read_progress: space recompute failed node_id=%s space_id=%s",
            node_id,
            space_id,
            exc_info=True,
        )

    return updated


async def reset_node_quiz_passed_for_all_trainees(
    session: AsyncSession,
    *,
    node_id: UUID,
    space_id: UUID,
    has_published_quiz: bool = True,
) -> int:
    """EC-20: clear quiz_passed for every trainee on *node_id*.

    Preserves ``quiz_best_score`` and ``quiz_attempt_count``. Recomputes
    ``completion_status`` so completed trainees move back to in_progress
    when a new quiz is published.
    """
    now = utc_now()
    result = await session.execute(
        update(TraineeNodeProgress)
        .where(
            and_(
                TraineeNodeProgress.node_id == node_id,
                TraineeNodeProgress.space_id == space_id,
            )
        )
        .values(
            quiz_passed=False,
            completion_status=_completion_after_quiz_passed_reset(
                has_published_quiz=has_published_quiz
            ),
            updated_at=now,
        )
    )
    updated = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()

    try:
        await recompute_all_trainees_space_progress(session, space_id=space_id)
    except Exception:
        logger.warning(
            "reset_node_quiz_passed: space recompute failed node_id=%s space_id=%s",
            node_id,
            space_id,
            exc_info=True,
        )

    return updated


async def recompute_node_quiz_passed_for_threshold(
    session: AsyncSession,
    *,
    node_id: UUID,
    space_id: UUID,
    pass_threshold_percent: int,
) -> int:
    """Re-evaluate cached pass/completion state after a live threshold change.

    Lowering the threshold may auto-pass trainees and batch-grant child unlocks.
    Raising it may clear ``quiz_passed`` but never revokes durable child grants.
    """
    from src.api.utils.trainee_progress_utils.unlocking import (  # noqa: PLC0415
        grant_unlocks_for_completed_trainees_on_node,
    )

    threshold = pass_threshold_percent / 100.0
    passed = TraineeNodeProgress.quiz_best_score.is_not(None) & (
        TraineeNodeProgress.quiz_best_score >= threshold
    )
    completion_status = case(
        (
            TraineeNodeProgress.study_material_completed.is_(True) & passed,
            "completed",
        ),
        (
            (TraineeNodeProgress.study_material_read_percent > 0)
            | (TraineeNodeProgress.quiz_attempt_count > 0)
            | TraineeNodeProgress.study_material_completed.is_(True),
            "in_progress",
        ),
        else_="not_started",
    )
    result = await session.execute(
        update(TraineeNodeProgress)
        .where(
            and_(
                TraineeNodeProgress.node_id == node_id,
                TraineeNodeProgress.space_id == space_id,
            )
        )
        .values(
            quiz_passed=passed,
            completion_status=completion_status,
            updated_at=utc_now(),
        )
    )
    updated = int(getattr(result, "rowcount", 0) or 0)
    await grant_unlocks_for_completed_trainees_on_node(
        session, node_id=node_id, space_id=space_id
    )
    await session.commit()
    await recompute_all_trainees_space_progress(session, space_id=space_id)
    return updated


async def recompute_node_completion_after_quiz_unpublish(
    session: AsyncSession,
    *,
    node_id: UUID,
    space_id: UUID,
) -> int:
    """C3: after quiz unpublish, reading-complete trainees become completed.

    Syncs stored ``completion_status`` (quiz no longer required) and durable-
    grants eligible children. Does not clear ``quiz_passed`` / best score —
    those remain historical. Never revokes existing child unlocks.
    """
    from src.api.utils.trainee_progress_utils.unlocking import (  # noqa: PLC0415
        grant_unlocks_for_completed_trainees_on_node,
    )

    now = utc_now()
    result = await session.execute(
        update(TraineeNodeProgress)
        .where(
            and_(
                TraineeNodeProgress.node_id == node_id,
                TraineeNodeProgress.space_id == space_id,
            )
        )
        .values(
            completion_status=_completion_after_quiz_passed_reset(
                has_published_quiz=False
            ),
            updated_at=now,
        )
    )
    updated = int(getattr(result, "rowcount", 0) or 0)
    await grant_unlocks_for_completed_trainees_on_node(
        session, node_id=node_id, space_id=space_id
    )
    await session.commit()
    return updated
