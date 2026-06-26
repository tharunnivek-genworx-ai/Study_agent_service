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
    TraineeArchivedSmListOut,
    TraineeArchivedStudyMaterialOut,
    TraineeStudyMaterialOut,
)
from src.api.schemas.study_material_schemas.trainee_node_panel_schema import (
    TraineeNodePanelOut,
)
from src.api.schemas.study_material_schemas.trainee_topic_resource_schema import (
    TraineeTopicResourceListOut,
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


@router.get(
    "/nodes/{node_id}/topic-resources",
    response_model=TraineeTopicResourceListOut,
)
async def list_topic_resources(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeTopicResourceListOut:
    """List supplementary topic resources (node_media) for trainees."""
    service = TraineeStudyService(db)
    return await service.list_topic_resources(
        node_id, current_user.sub, current_user.role
    )


@router.get("/nodes/{node_id}/topic-resources/{media_id}/file")
async def view_topic_resource_file(
    node_id: UUID,
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> Response:
    """Stream an image or PDF inline for viewing."""
    service = TraineeStudyService(db)
    content, _filename, mime_type, disposition = await service.get_topic_resource_file(
        node_id, media_id, current_user.sub, current_user.role, as_attachment=False
    )
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": disposition},
    )


@router.get("/nodes/{node_id}/topic-resources/{media_id}/download")
async def download_topic_resource_file(
    node_id: UUID,
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> Response:
    """Download an image or PDF topic resource as an attachment."""
    service = TraineeStudyService(db)
    content, _filename, mime_type, disposition = await service.get_topic_resource_file(
        node_id, media_id, current_user.sub, current_user.role, as_attachment=True
    )
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": disposition},
    )


@router.get(
    "/nodes/{node_id}/study-material/archive",
    response_model=TraineeArchivedSmListOut,
)
async def list_archived_study_material(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeArchivedSmListOut:
    """List superseded study material versions for trainee reference."""
    service = TraineeStudyService(db)
    return await service.list_archived_study_material(
        node_id, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/study-material/versions/{version_id}",
    response_model=TraineeArchivedStudyMaterialOut,
)
async def get_archived_study_material(
    node_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeArchivedStudyMaterialOut:
    """Read-only archived study material content."""
    service = TraineeStudyService(db)
    return await service.get_archived_study_material(
        node_id, version_id, current_user.sub, current_user.role
    )


@router.get("/nodes/{node_id}/study-material/versions/{version_id}/pdf")
async def download_archived_study_material_pdf(
    node_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> Response:
    """Download archived study material as PDF (read-only reference)."""
    service = TraineeStudyService(db)
    pdf_bytes, filename = await service.download_archived_pdf(
        node_id, version_id, current_user.sub, current_user.role
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
