"""HTTP routes for durable generate-all batch jobs (poll-only; no client advance)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.batch.dispatcher import dispatch_batch_job
from src.api.core.services.batch_orchestration_service import (
    BatchOrchestrationService,
)
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.batch_schemas import (
    BatchCancelResponse,
    BatchCreateRequest,
    BatchCreateResponse,
    BatchDetailOut,
    BatchPreviewRequest,
    BatchPreviewResponse,
)
from src.api.schemas.identity_schemas.auth_schema import TokenPayload

router = APIRouter(tags=["Study Material Batch"])
logger = logging.getLogger(__name__)


@router.post(
    "/spaces/{space_id}/batches/preview",
    response_model=BatchPreviewResponse,
)
async def preview_generate_all(
    space_id: UUID,
    payload: BatchPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> BatchPreviewResponse:
    service = BatchOrchestrationService(db)
    return await service.preview_generate_all(
        space_id=space_id,
        root_node_ids=payload.root_node_ids,
        node_ids=payload.node_ids,
        mentor_id=current_user.sub,
        role=current_user.role,
    )


@router.post(
    "/spaces/{space_id}/batches",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BatchCreateResponse,
)
async def create_batch(
    space_id: UUID,
    payload: BatchCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> BatchCreateResponse:
    service = BatchOrchestrationService(db)
    try:
        response = await service.create_batch(
            space_id=space_id,
            payload=payload,
            mentor_id=current_user.sub,
            role=current_user.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    await dispatch_batch_job(response.batch_id)
    logger.info(
        "Batch job created",
        extra={
            "space_id": str(space_id),
            "batch_id": str(response.batch_id),
            "mentor_id": str(current_user.sub),
        },
    )
    return response


@router.get(
    "/batches/{batch_id}",
    response_model=BatchDetailOut,
)
async def get_batch_detail(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> BatchDetailOut:
    service = BatchOrchestrationService(db)
    try:
        detail = await service.get_batch_detail(
            batch_id=batch_id,
            mentor_id=current_user.sub,
            role=current_user.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return detail


@router.post(
    "/batches/{batch_id}/cancel",
    response_model=BatchCancelResponse,
)
async def cancel_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> BatchCancelResponse:
    service = BatchOrchestrationService(db)
    try:
        response = await service.cancel_batch(
            batch_id=batch_id,
            mentor_id=current_user.sub,
            role=current_user.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return response


@router.get(
    "/spaces/{space_id}/batches/active",
    response_model=BatchDetailOut | None,
)
async def get_active_batch(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> BatchDetailOut | None:
    service = BatchOrchestrationService(db)
    detail = await service.get_active_batch_for_space(
        space_id=space_id,
        mentor_id=current_user.sub,
        role=current_user.role,
    )
    await db.commit()
    return detail
