"""Abandon in-progress quiz attempts when a quiz is archived or superseded."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.quiz_attempts import QuizAttempt


async def abandon_in_progress_attempts_for_quizzes(
    session: AsyncSession,
    quiz_ids: list[UUID],
) -> int:
    """Mark in-progress attempts as abandoned for the given quiz ids.

    Uses a bulk UPDATE to avoid expired-attribute lazy loads on ORM rows after
    subsequent commits in the same async session.
    """
    if not quiz_ids:
        return 0
    now = datetime.now(UTC)
    result = await session.execute(
        update(QuizAttempt)
        .where(
            and_(
                QuizAttempt.quiz_id.in_(quiz_ids),
                QuizAttempt.status == "in_progress",
            )
        )
        .values(status="abandoned", submitted_at=now)
    )
    await session.flush()
    return int(getattr(result, "rowcount", 0) or 0)
