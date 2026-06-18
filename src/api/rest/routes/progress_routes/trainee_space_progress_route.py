# src/api/rest/routes/progress_routes/trainee_space_progress_route.py
"""
Trainee space progress routes — self-view only.

Mentor-facing space progress dashboard (GET /spaces/:id/progress, mentor role)
is intentionally not implemented here; that is a separate route to be added
later. This module covers only the trainee's own rollup view.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.progress_services.trainee_space_progress_service import (
    TraineeSpaceProgressService,
)
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.schemas.progress_schemas.trainee_progress_schema import (
    TraineeOwnSpaceProgressOut,
)

router = APIRouter(prefix="/trainee", tags=["Trainee Space Progress"])


@router.get(
    "/spaces/{space_id}/progress",
    response_model=TraineeOwnSpaceProgressOut,
)
async def get_own_space_progress(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeOwnSpaceProgressOut:
    """Trainee self-view of their own progress rollup within a space."""
    service = TraineeSpaceProgressService(db)
    return await service.get_own_space_progress(
        space_id=space_id,
        user_id=current_user.sub,
        role=current_user.role,
    )
