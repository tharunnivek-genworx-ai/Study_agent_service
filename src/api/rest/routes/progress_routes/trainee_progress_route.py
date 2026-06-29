# C:\CapStone\study_agent_service\src\api\rest\routes\progress_routes\trainee_progress_route.py
"""
Trainee progress routes — all learner progress reads and writes.

Study material delivery lives in ``trainee_study_routes``; that module calls
``TraineeProgressService`` internally when assembling the topic detail panel
(Option 1 orchestrator pattern).
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services import (
    TraineeProgressService,
)
from src.api.data.clients.postgres import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas import TokenPayload
from src.api.schemas.progress_schemas import (
    TraineeNodeProgressBatchOut,
    TraineeNodeProgressBatchRequest,
    TraineeNodeProgressOut,
    TraineeProgressUpdateRequest,
)

router = APIRouter(prefix="/trainee", tags=["Trainee Progress"])


@router.patch(
    "/nodes/{node_id}/study-material/progress",
    response_model=TraineeNodeProgressOut,
)
async def update_study_material_progress(
    node_id: UUID,
    payload: TraineeProgressUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeNodeProgressOut:
    """Trainee updates scroll read progress for published study material."""
    service = TraineeProgressService(db)
    return await service.update_study_material_progress(
        node_id=node_id,
        payload=payload,
        user_id=current_user.sub,
        role=current_user.role,
    )


@router.post(
    "/nodes/progress/batch",
    response_model=TraineeNodeProgressBatchOut,
)
async def get_batch_node_progress(
    payload: TraineeNodeProgressBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeNodeProgressBatchOut:
    """Batch-read progress snapshots for a set of node ids.

    Exposed for direct clients and for future microservice extraction.
    The topic detail panel uses the same service method in-process today.
    """
    service = TraineeProgressService(db)
    return await service.get_batch_node_progress_out(
        node_ids=payload.node_ids,
        user_id=current_user.sub,
        role=current_user.role,
    )
