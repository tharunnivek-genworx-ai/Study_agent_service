"""Insert node_event_notifications rows for trainee-facing event delivery."""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.progress_notification_models.node_event_notifications import (
    NodeEventNotification,
)
from src.api.utils.common_utils.time import utc_now

logger = logging.getLogger(__name__)

EVENT_NODE_COMPLETION_RESET = "node_completion_reset"

_NODE_COMPLETION_RESET_MESSAGE = (
    "A new quiz was published for this topic. Your completion status has been "
    "reset — pass the quiz to complete this topic."
)


async def emit_node_completion_reset(
    session: AsyncSession,
    *,
    space_id: UUID,
    node_id: UUID,
    triggered_by: UUID,
    related_quiz_id: UUID | None = None,
) -> None:
    """EC-20: notify enrolled trainees that node completion was reset on quiz publish."""
    await session.execute(
        insert(NodeEventNotification).values(
            notification_id=uuid4(),
            space_id=space_id,
            node_id=node_id,
            event_type=EVENT_NODE_COMPLETION_RESET,
            triggered_by=triggered_by,
            related_quiz_id=related_quiz_id,
            system_message=_NODE_COMPLETION_RESET_MESSAGE,
            created_at=utc_now(),
        )
    )
    await session.commit()


async def emit_node_completion_reset_safe(
    session: AsyncSession,
    *,
    space_id: UUID,
    node_id: UUID,
    triggered_by: UUID,
    related_quiz_id: UUID | None = None,
) -> None:
    """Best-effort wrapper — notification failure must not roll back publish."""
    try:
        await emit_node_completion_reset(
            session,
            space_id=space_id,
            node_id=node_id,
            triggered_by=triggered_by,
            related_quiz_id=related_quiz_id,
        )
    except Exception:
        logger.warning(
            "emit_node_completion_reset failed space_id=%s node_id=%s quiz_id=%s",
            space_id,
            node_id,
            related_quiz_id,
            exc_info=True,
        )
