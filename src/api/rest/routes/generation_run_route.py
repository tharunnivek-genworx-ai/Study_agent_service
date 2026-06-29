"""Shared generation run status and resume endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.generation_run_service import GenerationRunService
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.generation_run_schema import (
    GenerationRunOut,
    GenerationRunResumeResponse,
)
from src.api.schemas.identity_schemas.auth_schema import TokenPayload

router = APIRouter(tags=["Generation Runs"])


@router.get(
    "/generation-runs/{run_id}",
    response_model=GenerationRunOut,
)
async def get_generation_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationRunOut:
    """Return generation run status, last completed step, and resumable flag."""
    service = GenerationRunService(db)
    return await service.get_run(run_id, mentor_id=current_user.sub)


@router.post(
    "/generation-runs/{run_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationRunResumeResponse,
)
async def resume_generation_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationRunResumeResponse:
    """Resume a failed generation run from its last checkpoint."""
    service = GenerationRunService(db)
    return await service.execute_resume(
        run_id,
        mentor_id=current_user.sub,
        role=current_user.role,
    )


@router.post(
    "/generation-runs/{run_id}/cancel",
    response_model=GenerationRunOut,
)
async def cancel_generation_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationRunOut:
    """Cancel an in-flight generation run."""
    service = GenerationRunService(db)
    return await service.cancel_run(run_id, mentor_id=current_user.sub)
