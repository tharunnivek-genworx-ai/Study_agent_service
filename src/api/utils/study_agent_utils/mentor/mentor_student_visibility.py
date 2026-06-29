# src/api/utils/study_agent_utils/mentor_student_visibility.py
"""What students currently see on a topic — mentor visibility summary."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.repositories import (
    StudyMaterialRepository,
    TraineeQuizRepository,
)
from src.api.schemas.study_material_schemas import (
    MentorStudentVisibilityOut,
)
from src.api.utils.content_lifecycle.queries import list_trainee_archive_sm
from src.api.utils.study_agent_utils.version.version_labels import (
    build_version_display_label,
)


async def build_mentor_student_visibility(
    session: AsyncSession,
    node_id: UUID,
) -> MentorStudentVisibilityOut:
    """Resolve live material, previous versions, and optional live quiz for mentors."""
    sm_repo = StudyMaterialRepository(session)
    published = await sm_repo.get_published_version(node_id)

    live_material_label: str | None = None
    live_material_version_id: UUID | None = None
    if published is not None:
        live_material_version_id = published.version_id
        live_material_label = build_version_display_label(
            published.version_number,
            published.generation_type,
        )

    archived_versions = await list_trainee_archive_sm(session, node_id)
    previous_version_labels = [
        build_version_display_label(v.version_number, v.generation_type)
        for v in archived_versions[:3]
    ]

    quiz_repo = TraineeQuizRepository(session)
    live_quiz = await quiz_repo.get_published_quiz_by_node(node_id)
    live_quiz_title = live_quiz.title if live_quiz is not None else None

    return MentorStudentVisibilityOut(
        live_material_label=live_material_label,
        live_material_version_id=live_material_version_id,
        previous_version_count=len(archived_versions),
        previous_version_labels=previous_version_labels,
        live_quiz_title=live_quiz_title,
    )
