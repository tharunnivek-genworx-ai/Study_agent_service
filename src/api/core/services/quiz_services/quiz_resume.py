"""Resume execution for quiz generation runs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.api.core.services.quiz_services.quiz_service import QuizService
from src.api.core.services.resume_dispatch import execute_pipeline_resume
from src.api.schemas import GenerationRunResumeResult

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
    await execute_pipeline_resume(
        session,
        resume_result,
        mentor_id=mentor_id,
        role=role,
        service_factory=QuizService,
        resume_fn=QuizService.resume_quiz_generation,
    )
