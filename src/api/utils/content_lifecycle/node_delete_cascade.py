"""Retire study material and quiz content when topic nodes are soft-deleted.

Mentor-facing node removal sets ``topicnodes.isactive = false`` in Identity.
This module unpublishes live layers and discards workspace drafts so content
does not remain ``lifecycle_status = active`` on invisible nodes.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.utils.content_lifecycle.attempt_freeze import (
    abandon_in_progress_attempts_for_quizzes,
)
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_DRAFT,
    LIFECYCLE_HIDDEN,
)
from src.api.utils.content_lifecycle.transitions import (
    transition_quiz_to_archived,
    transition_quiz_to_discarded,
    transition_sm_to_archived,
    transition_sm_to_discarded,
)
from src.api.utils.content_lifecycle.visibility import (
    is_trainee_live_quiz,
    is_trainee_live_sm,
)
from src.api.utils.mentor_progress_utils.space_recompute import (
    recompute_all_trainees_space_progress,
)

logger = logging.getLogger(__name__)


async def preview_node_delete_content(
    session: AsyncSession,
    *,
    node_ids: list[UUID],
) -> tuple[int, int]:
    """Count live study material versions and quizzes that would be retired."""
    if not node_ids:
        return 0, 0

    sm_repo = StudyMaterialRepository(session)
    quiz_repo = QuizRepository(session)
    live_sm_count = 0
    live_quiz_count = 0

    for node_id in node_ids:
        versions = await sm_repo.get_all_versions(node_id, archived=None)
        live_sm_count += sum(1 for version in versions if is_trainee_live_sm(version))

        quizzes = await quiz_repo.get_quizzes_by_node(node_id)
        live_quiz_count += sum(1 for quiz in quizzes if is_trainee_live_quiz(quiz))

    return live_sm_count, live_quiz_count


async def cascade_node_delete_content(
    session: AsyncSession,
    *,
    space_id: UUID,
    node_ids: list[UUID],
) -> None:
    """Unpublish live SM/quiz layers and discard drafts for deleted topic nodes."""
    if not node_ids:
        return

    sm_repo = StudyMaterialRepository(session)
    quiz_repo = QuizRepository(session)
    quiz_ids_to_abandon: list[UUID] = []

    for node_id in node_ids:
        versions = await sm_repo.get_all_versions(node_id, archived=None)
        for version in versions:
            if version.lifecycle_status == LIFECYCLE_ACTIVE and version.is_published:
                transition_sm_to_archived(version)
            elif version.lifecycle_status == LIFECYCLE_HIDDEN and version.published_at:
                transition_sm_to_archived(version)
            elif version.lifecycle_status in (LIFECYCLE_DRAFT, LIFECYCLE_HIDDEN):
                transition_sm_to_discarded(version)

        quizzes = await quiz_repo.get_quizzes_by_node(node_id)
        for quiz in quizzes:
            if quiz.lifecycle_status == LIFECYCLE_ARCHIVED:
                continue
            if quiz.lifecycle_status == LIFECYCLE_ACTIVE and quiz.is_published:
                transition_quiz_to_archived(quiz)
                quiz_ids_to_abandon.append(quiz.quiz_id)
            elif quiz.lifecycle_status == LIFECYCLE_HIDDEN and quiz.published_at:
                transition_quiz_to_archived(quiz)
                quiz_ids_to_abandon.append(quiz.quiz_id)
            elif quiz.lifecycle_status in (LIFECYCLE_DRAFT, LIFECYCLE_HIDDEN):
                transition_quiz_to_discarded(quiz)

    await abandon_in_progress_attempts_for_quizzes(session, quiz_ids_to_abandon)
    await session.commit()

    try:
        await recompute_all_trainees_space_progress(session, space_id=space_id)
    except Exception:
        logger.warning(
            "cascade_node_delete_content: space-progress recompute failed "
            "for space_id=%s node_ids=%s",
            space_id,
            node_ids,
            exc_info=True,
        )
