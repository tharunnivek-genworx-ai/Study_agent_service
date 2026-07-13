# src/api/rest/routes/study_agent_routes/study_material_route.py
"""
Routes for study_material_versions.

  generate    → POST  /nodes/{node_id}/study-material/generate  (202 async)
  regenerate  → POST  /nodes/{node_id}/study-material/regenerate (202 async)
  improve     → POST  /nodes/{node_id}/study-material/improve   (202 async)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.study_agent_services.study_material_service import (
    StudyMaterialService,
)
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.generation_run_schema import GenerationJobStartResponse
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.schemas.study_material_schemas.study_material_schema import (
    SpacePublishedResourcesResponse,
    SpaceRepublishChecklistOut,
    StudyMaterialActivateRequest,
    StudyMaterialClearDraftsEligibilityOut,
    StudyMaterialClearDraftsOut,
    StudyMaterialGenerateRequest,
    StudyMaterialImproveRequest,
    StudyMaterialManualEditRequest,
    StudyMaterialMentorUiStateOut,
    StudyMaterialPublishPreviewOut,
    StudyMaterialPublishRequest,
    StudyMaterialRegenerateRequest,
    StudyMaterialUnpublishPreviewOut,
    StudyMaterialUnpublishRequest,
    StudyMaterialVersionHistoryOut,
    StudyMaterialVersionOut,
)
from src.api.utils.generation_progress.generation_job_executor import (
    schedule_generation_job,
)

router = APIRouter(tags=["Study Material"])


@router.post(
    "/nodes/{node_id}/study-material/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationJobStartResponse,
)
async def generate_study_material(
    node_id: UUID,
    payload: StudyMaterialGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationJobStartResponse:
    """Mentor triggers first-time study material generation (async)."""
    service = StudyMaterialService(db)
    run_id = await service.start_generate_study_material(
        node_id, payload, current_user.sub, current_user.role
    )
    await db.commit()
    user_id = current_user.sub
    schedule_generation_job(
        lambda session: StudyMaterialService(session).execute_generate_study_material(
            run_id=run_id,
            user_id=user_id,
        ),
        run_id=run_id,
        mentor_id=user_id,
    )
    return GenerationJobStartResponse(run_id=run_id, pipeline="study_material")


@router.post(
    "/nodes/{node_id}/study-material/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationJobStartResponse,
)
async def regenerate_study_material(
    node_id: UUID,
    payload: StudyMaterialRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationJobStartResponse:
    """Mentor rewrites the active draft with feedback (async)."""
    service = StudyMaterialService(db)
    run_id = await service.start_regenerate_study_material(
        node_id, payload, current_user.sub, current_user.role
    )
    await db.commit()
    user_id = current_user.sub
    schedule_generation_job(
        lambda session: StudyMaterialService(session).execute_regenerate_study_material(
            run_id=run_id,
            user_id=user_id,
        ),
        run_id=run_id,
        mentor_id=user_id,
    )
    return GenerationJobStartResponse(run_id=run_id, pipeline="study_material")


@router.post(
    "/nodes/{node_id}/study-material/improve",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerationJobStartResponse,
)
async def improve_study_material(
    node_id: UUID,
    payload: StudyMaterialImproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> GenerationJobStartResponse:
    """Mentor submits feedback to improve the current active version (async)."""
    service = StudyMaterialService(db)
    run_id = await service.start_improve_study_material(
        node_id, payload, current_user.sub, current_user.role
    )
    await db.commit()
    user_id = current_user.sub
    schedule_generation_job(
        lambda session: StudyMaterialService(session).execute_improve_study_material(
            run_id=run_id,
            user_id=user_id,
        ),
        run_id=run_id,
        mentor_id=user_id,
    )
    return GenerationJobStartResponse(run_id=run_id, pipeline="study_material")


@router.patch(
    "/nodes/{node_id}/study-material/manual-edit",
    response_model=StudyMaterialVersionOut,
)
async def manual_edit_study_material(
    node_id: UUID,
    payload: StudyMaterialManualEditRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionOut:
    """Mentor saves a rich-text edit directly. Creates vN+1 with no LLM call."""
    service = StudyMaterialService(db)
    return await service.manual_edit_study_material(
        node_id, payload, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/study-material/publish-preview",
    response_model=StudyMaterialPublishPreviewOut,
)
async def preview_publish_study_material(
    node_id: UUID,
    version_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialPublishPreviewOut:
    """Pre-publish check: returns confirmation requirements without writing."""
    service = StudyMaterialService(db)
    return await service.preview_publish_study_material(
        node_id, version_id, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/study-material/publish",
    response_model=StudyMaterialVersionOut,
)
async def publish_study_material(
    node_id: UUID,
    payload: StudyMaterialPublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionOut:
    """Mentor publishes a specific version, making it visible to trainees."""
    service = StudyMaterialService(db)
    return await service.publish_study_material(
        node_id, payload, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/study-material/unpublish-preview",
    response_model=StudyMaterialUnpublishPreviewOut,
)
async def preview_unpublish_study_material(
    node_id: UUID,
    version_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialUnpublishPreviewOut:
    """Pre-unpublish check: returns confirmation requirements without writing."""
    service = StudyMaterialService(db)
    return await service.preview_unpublish_study_material(
        node_id, version_id, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/study-material/unpublish",
    response_model=StudyMaterialVersionOut,
)
async def unpublish_study_material(
    node_id: UUID,
    payload: StudyMaterialUnpublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionOut:
    """Mentor unpublishes a version with a retention choice (remove or keep for review)."""
    service = StudyMaterialService(db)
    return await service.unpublish_study_material(
        node_id, payload, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/study-material/activate",
    response_model=StudyMaterialVersionOut,
)
async def activate_study_material(
    node_id: UUID,
    payload: StudyMaterialActivateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionOut:
    """Mentor sets a specific version as the active working draft (is_active=True)."""
    service = StudyMaterialService(db)
    return await service.activate_study_material(
        node_id, payload, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/study-material/active",
    response_model=StudyMaterialVersionOut | None,
)
async def get_active_study_material(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionOut | None:
    """Return the current active study material version for a node."""
    service = StudyMaterialService(db)
    return await service.get_active_version(
        node_id, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/study-material/mentor-ui-state",
    response_model=StudyMaterialMentorUiStateOut,
)
async def get_study_material_mentor_ui_state(
    node_id: UUID,
    viewing_version_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialMentorUiStateOut:
    """Mentor UI flags: access, instruction drift, and allowed version actions."""
    service = StudyMaterialService(db)
    return await service.get_mentor_ui_state(
        node_id,
        current_user.sub,
        current_user.role,
        viewing_version_id=viewing_version_id,
    )


@router.get(
    "/nodes/{node_id}/study-material/drafts/delete-eligibility",
    response_model=StudyMaterialClearDraftsEligibilityOut,
)
async def get_clear_drafts_eligibility(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialClearDraftsEligibilityOut:
    """Check whether study material drafts can be cleared (blocked when quizzes exist)."""
    service = StudyMaterialService(db)
    return await service.get_clear_drafts_eligibility(
        node_id, current_user.sub, current_user.role
    )


@router.delete(
    "/nodes/{node_id}/study-material/drafts",
    response_model=StudyMaterialClearDraftsOut,
)
async def clear_study_material_drafts(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialClearDraftsOut:
    """Delete all study material drafts for a node so generation can start fresh."""
    service = StudyMaterialService(db)
    return await service.clear_all_drafts(node_id, current_user.sub, current_user.role)


@router.get(
    "/nodes/{node_id}/study-material/versions",
    response_model=StudyMaterialVersionHistoryOut,
)
async def list_study_material_versions(
    node_id: UUID,
    archived: bool = Query(
        default=False,
        description="When true, return archived versions only.",
    ),
    viewing_version_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionHistoryOut:
    """Mentor fetches version history or archive shelf for a node, newest first."""
    service = StudyMaterialService(db)
    return await service.list_versions(
        node_id,
        current_user.sub,
        current_user.role,
        archived=archived,
        viewing_version_id=viewing_version_id,
    )


@router.patch(
    "/nodes/{node_id}/study-material/versions/{version_id}/archive",
    response_model=StudyMaterialVersionOut,
)
async def archive_study_material_version(
    node_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionOut:
    """Mentor archives a version (soft-hide from working history)."""
    service = StudyMaterialService(db)
    return await service.archive_study_material_version(
        node_id, version_id, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/study-material/versions/{version_id}/unarchive",
    response_model=StudyMaterialVersionOut,
)
async def unarchive_study_material_version(
    node_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionOut:
    """Mentor restores an archived version to working history."""
    service = StudyMaterialService(db)
    return await service.unarchive_study_material_version(
        node_id, version_id, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/study-material/versions/{version_id}/dismiss-qc-warning",
    response_model=StudyMaterialVersionOut,
)
async def dismiss_study_material_qc_warning(
    node_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionOut:
    """Mentor acknowledges a QC warning and accepts the study material draft."""
    service = StudyMaterialService(db)
    return await service.dismiss_study_material_qc_warning(
        node_id, version_id, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/study-material/versions/{version_id}",
    response_model=StudyMaterialVersionOut,
)
async def get_study_material_version(
    node_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialVersionOut:
    """Mentor fetches a single version by ID."""
    service = StudyMaterialService(db)
    return await service.get_version(
        node_id, version_id, current_user.sub, current_user.role
    )


@router.get("/nodes/{node_id}/study-material/versions/{version_id}/pdf")
async def download_study_material_version_pdf(
    node_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> Response:
    """Download a mentor-accessible study material version as PDF."""
    service = StudyMaterialService(db)
    pdf_bytes, filename = await service.download_version_pdf(
        node_id, version_id, current_user.sub, current_user.role
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/spaces/{space_id}/republish-checklist",
    response_model=SpaceRepublishChecklistOut,
)
async def get_space_republish_checklist(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> SpaceRepublishChecklistOut:
    """List per-node content to re-publish after espace republish."""
    service = StudyMaterialService(db)
    return await service.get_space_republish_checklist(
        space_id, current_user.sub, current_user.role
    )


@router.get(
    "/spaces/{space_id}/published-resources",
    response_model=SpacePublishedResourcesResponse,
)
async def get_space_published_resources(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> SpacePublishedResourcesResponse:
    """Mentor fetches all published topics, study materials, and quizzes in a space."""
    service = StudyMaterialService(db)
    return await service.get_space_published_resources(
        space_id, current_user.sub, current_user.role
    )
