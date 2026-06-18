"""
Routes for trainee study material and topic detail panel.

Progress writes and batch reads live in ``trainee_progress_route`` /
``TraineeProgressService``. The panel endpoint orchestrates both domains
in-process (Option 1).
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.trainee_study_services.trainee_node_panel_service import (
    TraineeNodePanelService,
)
from src.api.core.services.trainee_study_services.trainee_study_service import (
    TraineeStudyService,
)
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.schemas.study_material_schemas.study_material_schema import (
    TraineeStudyMaterialOut,
)
from src.api.schemas.study_material_schemas.trainee_node_panel_schema import (
    TraineeNodePanelOut,
)

router = APIRouter(prefix="/trainee", tags=["Trainee Study"])


@router.get(
    "/nodes/{node_id}/panel",
    response_model=TraineeNodePanelOut,
)
async def get_node_panel(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeNodePanelOut:
    """Topic detail panel — orchestrates study content + progress service."""
    service = TraineeNodePanelService(db)
    return await service.get_node_panel(node_id, current_user.sub, current_user.role)


@router.get(
    "/nodes/{node_id}/study-material",
    response_model=TraineeStudyMaterialOut,
)
async def get_published_study_material(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeStudyMaterialOut:
    """Full published study material for the in-panel reading view."""
    service = TraineeStudyService(db)
    return await service.get_published_study_material(
        node_id, current_user.sub, current_user.role
    )


@router.get("/nodes/{node_id}/study-material/pdf")
async def download_published_study_material_pdf(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> Response:
    """Download published study material as a PDF attachment."""
    service = TraineeStudyService(db)
    pdf_bytes, filename = await service.download_published_pdf(
        node_id, current_user.sub, current_user.role
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
