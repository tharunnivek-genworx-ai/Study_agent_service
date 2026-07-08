"""Shared generation run status and resume endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services import GenerationRunService
from src.api.data.clients.postgres import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas import (
    GenerationRunActiveOut,
    GenerationRunOut,
    GenerationRunResultOut,
    GenerationRunResumeResponse,
)
from src.api.schemas.identity_schemas import TokenPayload
from src.api.utils.generation_progress.generation_job_executor import (
    schedule_generation_job,
)

router = APIRouter(tags=["Generation Runs"])


@router.get(
    "/generation-runs/active",
    response_model=GenerationRunActiveOut | None,
)
async def get_active_generation_run(
    resource_id: UUID = Query(...),
    pipeline: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationRunActiveOut | None:
    """Return the in-flight generation run for a resource, if any."""
    service = GenerationRunService(db)
    return await service.get_active_run_for_resource(
        resource_id=resource_id,
        pipeline=pipeline,
        mentor_id=current_user.sub,
    )


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


@router.get(
    "/generation-runs/{run_id}/result",
    response_model=GenerationRunResultOut,
)
async def get_generation_run_result(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationRunResultOut:
    """Return the materialized result payload for a completed generation run."""
    service = GenerationRunService(db)
    return await service.get_run_result(run_id, mentor_id=current_user.sub)


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
    """Resume a failed generation run from its last checkpoint (async)."""
    service = GenerationRunService(db)
    resume_result = await service.begin_resume(run_id, mentor_id=current_user.sub)
    await db.commit()
    mentor_id = current_user.sub
    role = current_user.role
    schedule_generation_job(
        lambda session: GenerationRunService(session).run_resume_pipeline(
            resume_result,
            mentor_id=mentor_id,
            role=role,
        )
    )
    return GenerationRunResumeResponse(
        run_id=run_id,
        progress_session_id=run_id,
        pipeline=resume_result.pipeline,
        status="running",
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
