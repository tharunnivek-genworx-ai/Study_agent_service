"""HTTP routes for generate-all (sequential per-node generate).

Critical Cloud Run constraint: background ``asyncio.create_task`` after the
response returns often never runs (CPU throttled). So enqueue/get-batch
``await`` the kick while the request is still alive.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import GenerationAdvisoryLockUnavailableException
from src.api.core.services.study_agent_services.study_material_batch_service import (
    StudyMaterialBatchService,
)
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.schemas.study_material_schemas.batch_schema import (
    StudyMaterialBatchCancelResponse,
    StudyMaterialBatchDetailOut,
    StudyMaterialBatchEnqueueRequest,
    StudyMaterialBatchPreviewRequest,
    StudyMaterialBatchPreviewResponse,
    StudyMaterialSpaceQueueOut,
)
from src.api.utils.generation_progress.batch_queue_kick import kick_space_queue

router = APIRouter(tags=["Study Material Batch"])
logger = logging.getLogger(__name__)


@router.post(
    "/spaces/{space_id}/study-material/generate-all/preview",
    response_model=StudyMaterialBatchPreviewResponse,
)
async def preview_generate_all(
    space_id: UUID,
    payload: StudyMaterialBatchPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialBatchPreviewResponse:
    service = StudyMaterialBatchService(db)
    return await service.preview_generate_all(
        space_id=space_id,
        root_node_ids=payload.root_node_ids,
        mentor_id=current_user.sub,
        role=current_user.role,
    )


@router.post(
    "/spaces/{space_id}/study-material/generate-all/enqueue",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StudyMaterialSpaceQueueOut,
)
async def enqueue_generate_all(
    space_id: UUID,
    payload: StudyMaterialBatchEnqueueRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialSpaceQueueOut:
    """Persist the plan only — keep this fast on Cloud Run.

    Starting the first node is done by POST .../generation-queue/advance (or the
    GET batch safety-net). Awaiting kick inside enqueue caused 45s browser
    timeouts when locks/contention stalled claim.
    """
    service = StudyMaterialBatchService(db)
    try:
        snapshot = await service.enqueue_batch(
            space_id=space_id,
            payload=payload,
            mentor_id=current_user.sub,
            role=current_user.role,
        )
    except GenerationAdvisoryLockUnavailableException:
        # Return existing queue snapshot so the client can call advance to recover.
        logger.warning(
            "Generate-all enqueue lock busy — returning existing queue",
            extra={"space_id": str(space_id)},
        )
        await db.rollback()
        snapshot = await StudyMaterialBatchService(db).get_space_queue(
            space_id=space_id,
            mentor_id=current_user.sub,
            role=current_user.role,
        )
        await db.commit()
        return snapshot

    await db.commit()
    logger.info(
        "Generate-all enqueued (persist only)",
        extra={
            "space_id": str(space_id),
            "mentor_id": str(current_user.sub),
            "needs_advance": snapshot.needs_advance,
            "running_batch": (
                str(snapshot.running_batch.batch_id) if snapshot.running_batch else None
            ),
        },
    )
    return snapshot


@router.get(
    "/spaces/{space_id}/study-material/generation-queue",
    response_model=StudyMaterialSpaceQueueOut,
)
async def get_generation_queue(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialSpaceQueueOut:
    service = StudyMaterialBatchService(db)
    snapshot = await service.get_space_queue(
        space_id=space_id,
        mentor_id=current_user.sub,
        role=current_user.role,
    )
    await db.commit()

    if snapshot.needs_advance and snapshot.current_item is None:
        kick_status = await kick_space_queue(
            space_id=space_id,
            mentor_id=current_user.sub,
            role=current_user.role,
            force=True,
        )
        logger.info(
            "Generate-all queue GET re-armed kick",
            extra={"space_id": str(space_id), "kick": kick_status},
        )
        snapshot = await StudyMaterialBatchService(db).get_space_queue(
            space_id=space_id,
            mentor_id=current_user.sub,
            role=current_user.role,
        )
        await db.commit()

    return snapshot


@router.post(
    "/spaces/{space_id}/study-material/generation-queue/advance",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StudyMaterialSpaceQueueOut,
)
async def advance_generation_queue(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialSpaceQueueOut:
    """Recovery kick — starts one next item if the queue is idle."""
    kick_status = await kick_space_queue(
        space_id=space_id,
        mentor_id=current_user.sub,
        role=current_user.role,
        force=True,
    )
    logger.info(
        "Generate-all advance endpoint kicked",
        extra={"space_id": str(space_id), "kick": kick_status},
    )
    service = StudyMaterialBatchService(db)
    snapshot = await service.get_space_queue(
        space_id=space_id,
        mentor_id=current_user.sub,
        role=current_user.role,
    )
    await db.commit()
    return snapshot


@router.post(
    "/study-material-batches/{batch_id}/cancel",
    response_model=StudyMaterialBatchCancelResponse,
)
async def cancel_batch(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialBatchCancelResponse:
    service = StudyMaterialBatchService(db)
    try:
        response, space_id = await service.cancel_batch(
            batch_id=batch_id,
            mentor_id=current_user.sub,
            role=current_user.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    await kick_space_queue(
        space_id=space_id,
        mentor_id=current_user.sub,
        role=current_user.role,
        force=True,
    )
    return response


@router.get(
    "/study-material-batches/{batch_id}",
    response_model=StudyMaterialBatchDetailOut,
)
async def get_batch_detail(
    batch_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialBatchDetailOut:
    """Return batch detail and re-arm the sequential kick if stalled."""
    service = StudyMaterialBatchService(db)
    try:
        detail = await service.get_batch_detail(
            batch_id=batch_id,
            mentor_id=current_user.sub,
            role=current_user.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()

    # Safety net for Cloud Run: if items are still queued and nothing is running,
    # start the next generate while this poll request has CPU.
    has_running = any(item.status == "running" for item in detail.items)
    has_queued = any(item.status == "queued" for item in detail.items)
    if detail.batch.status in {"running", "queued"} and has_queued and not has_running:
        kick_status = await kick_space_queue(
            space_id=detail.batch.space_id,
            mentor_id=current_user.sub,
            role=current_user.role,
            force=True,
        )
        logger.info(
            "Generate-all batch GET re-armed kick",
            extra={
                "batch_id": str(batch_id),
                "space_id": str(detail.batch.space_id),
                "kick": kick_status,
            },
        )
        detail = await StudyMaterialBatchService(db).get_batch_detail(
            batch_id=batch_id,
            mentor_id=current_user.sub,
            role=current_user.role,
        )
        await db.commit()

    return detail
