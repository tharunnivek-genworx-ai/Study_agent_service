"""Resume execution for study material generation runs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.api.core.services.study_agent_services.study_material_service import (
    StudyMaterialService,
)
from src.api.schemas.generation_run_schema import GenerationRunResumeResult
from src.api.utils.space_node_utils.node_role_assert import _assert_mentor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def execute_resume(
    session: AsyncSession,
    resume_result: GenerationRunResumeResult,
    *,
    mentor_id: UUID,
    role: str,
) -> None:
    """Dispatch a validated study material resume to the service layer."""
    _assert_mentor(role)
    service = StudyMaterialService(session)
    await service.resume_study_material_generation(
        resume_result,
        user_id=mentor_id,
        role=role,
    )
