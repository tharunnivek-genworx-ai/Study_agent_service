"""Resume execution for quiz generation runs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.api.core.services.quiz_services.quiz_service import QuizService
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
    """Dispatch a validated quiz resume to the service layer."""
    _assert_mentor(role)
    service = QuizService(session)
    await service.resume_quiz_generation(
        resume_result,
        user_id=mentor_id,
        role=role,
    )
