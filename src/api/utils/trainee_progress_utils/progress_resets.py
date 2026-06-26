"""Batch progress resets when active study material or quiz content changes.

M4a — SM supersede: reset read progress for all trainees on the node.
M4b — EC-20 quiz publish: reset quiz_passed while preserving quiz_best_score.

Both paths update stored ``completion_status`` and fan out space-progress
recompute so ``count_completed_nodes`` stays accurate.
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
from src.api.utils.common_utils.time import utc_now
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
