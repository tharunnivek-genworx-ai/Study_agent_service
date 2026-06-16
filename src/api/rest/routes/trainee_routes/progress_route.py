# src/api/rest/routes/trainee_routes/progress_route.py
"""
Routes for trainee-side progress operations.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.trainee_services.trainee_service import TraineeService
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.schemas.study_material_schemas.study_material_schema import (
    StudyMaterialProgressOut,
    StudyMaterialProgressUpdateRequest,
)

router = APIRouter(prefix="/trainee", tags=["Trainee Progress"])


@router.patch(
    "/nodes/{node_id}/study-material/progress",
    response_model=StudyMaterialProgressOut,
)
async def update_study_material_progress(
    node_id: UUID,
    payload: StudyMaterialProgressUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialProgressOut:
    """Trainee updates scroll read progress for published study material."""
    service = TraineeService(db)
    return await service.update_study_material_progress(
        node_id, payload, current_user.sub, current_user.role
    )
