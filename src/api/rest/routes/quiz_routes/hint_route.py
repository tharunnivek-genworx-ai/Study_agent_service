# src/api/rest/routes/quiz_routes/hint_route.py
"""
Routes for hint generation on existing quiz questions (async).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services import HintService
from src.api.data.clients.postgres import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.generation_run_schema import GenerationJobStartResponse
from src.api.schemas.identity_schemas import TokenPayload
from src.api.schemas.quiz_schemas import (
    HintGenerateRequest,
    HintRegenerateRequest,
    QuizOut,
)
from src.api.utils.generation_progress.generation_job_executor import (
    schedule_generation_job,
)

router = APIRouter(tags=["Quiz Hints"])


@router.post(
    "/nodes/{node_id}/quizzes/{quiz_id}/hints/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationJobStartResponse,
)
async def generate_hints(
    node_id: UUID,
    quiz_id: UUID,
    payload: HintGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationJobStartResponse:
    """Mentor generates hints for all active questions missing hints (async)."""
    service = HintService(db)
    run_id = await service.start_generate_hints(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )
    await db.commit()
    user_id = current_user.sub
    schedule_generation_job(
        lambda session: HintService(session).execute_generate_hints(
            run_id=run_id,
            user_id=user_id,
        )
    )
    return GenerationJobStartResponse(run_id=run_id, pipeline="hint")


@router.post(
    "/nodes/{node_id}/quizzes/{quiz_id}/hints/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationJobStartResponse,
)
async def regenerate_hints(
    node_id: UUID,
    quiz_id: UUID,
    payload: HintRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationJobStartResponse:
    """Mentor regenerates hints for specific questions or the whole quiz (async)."""
    service = HintService(db)
    run_id = await service.start_regenerate_hints(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )
    await db.commit()
    user_id = current_user.sub
    schedule_generation_job(
        lambda session: HintService(session).execute_regenerate_hints(
            run_id=run_id,
            user_id=user_id,
        )
    )
    return GenerationJobStartResponse(run_id=run_id, pipeline="hint")


@router.delete(
    "/nodes/{node_id}/quizzes/{quiz_id}/hints",
    status_code=status.HTTP_200_OK,
    response_model=QuizOut,
)
async def delete_hints_draft(
    node_id: UUID,
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor clears all generated hints on an unpublished quiz draft."""
    service = HintService(db)
    return await service.delete_hints_draft(
        node_id, quiz_id, current_user.sub, current_user.role
    )
