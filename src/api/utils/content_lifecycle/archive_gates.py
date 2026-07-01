"""Gate checks for trainee archive (superseded) content access."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import (
    NodeNotActiveException,
    QuizNotFoundException,
    SpaceNotPublishedException,
    StudyMaterialArchiveNotAvailableException,
    StudyMaterialVersionNotInStudentArchiveException,
    TraineeNotEnrolledInSpaceException,
)
from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.data.models.postgres.e_spaces_trees.espaces import ESpace
from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.repositories import (
    MentorProgressRepository,
    StudyMaterialRepository,
)
from src.api.utils.content_lifecycle.constants import LIFECYCLE_ARCHIVED
from src.api.utils.space_node_utils.node_role_assert import _assert_trainee


async def assert_trainee_archive_context(
    session: AsyncSession,
    *,
    node_id: UUID,
    user_id: UUID,
    role: str,
) -> tuple[TopicNode, ESpace]:
    """Validate trainee, enrollment, published space, and active node.

    Does not require an active published SM — callers use
    ``assert_archive_list_gate`` for archive list/read gates.
    """
    _assert_trainee(role)
    guard_repo = MentorProgressRepository(session)
    node = await guard_repo.get_node_by_id(node_id)
    if node is None or not node.is_active:
        raise NodeNotActiveException()

    space = await guard_repo.get_space_by_id(node.space_id)
    if space is None or not space.is_published or not space.is_active:
        raise SpaceNotPublishedException()

    is_member = await guard_repo.is_active_member(node.space_id, user_id)
    if not is_member:
        raise TraineeNotEnrolledInSpaceException()

    return node, space


async def node_has_active_published_sm(session: AsyncSession, node_id: UUID) -> bool:
    """True when the node has a currently active published study material version."""
    sm_repo = StudyMaterialRepository(session)
    version = await sm_repo.get_published_version(node_id)
    return version is not None and version.lifecycle_status == "active"


async def assert_archive_list_gate(session: AsyncSession, *, node_id: UUID) -> bool:
    """Return True when archive listings are allowed (archived SM exists on node)."""
    from src.api.utils.content_lifecycle.queries import (
        list_trainee_archive_sm,  # noqa: PLC0415
    )

    archived = await list_trainee_archive_sm(session, node_id)
    return len(archived) > 0


async def assert_archived_sm_version(
    session: AsyncSession,
    *,
    node_id: UUID,
    version_id: UUID,
) -> StudyMaterialVersion:
    """Load an archived SM version or raise if gate / lifecycle checks fail."""
    if not await assert_archive_list_gate(session, node_id=node_id):
        raise StudyMaterialArchiveNotAvailableException()

    sm_repo = StudyMaterialRepository(session)
    version = await sm_repo.get_version_by_id(version_id)
    if (
        version is None
        or version.node_id != node_id
        or version.lifecycle_status != LIFECYCLE_ARCHIVED
    ):
        raise StudyMaterialVersionNotInStudentArchiveException()
    return version


async def assert_archived_quiz_access(
    session: AsyncSession,
    *,
    node_id: UUID,
    quiz_id: UUID,
) -> Quiz:
    """Load an archived quiz or raise when it is missing or not reviewable."""
    from sqlalchemy import select  # noqa: PLC0415

    result = await session.execute(select(Quiz).where(Quiz.quiz_id == quiz_id))
    quiz: Quiz | None = result.scalars().first()
    if quiz is None or quiz.node_id != node_id:
        raise QuizNotFoundException()
    if quiz.lifecycle_status != LIFECYCLE_ARCHIVED:
        raise StudyMaterialArchiveNotAvailableException()
    return quiz
