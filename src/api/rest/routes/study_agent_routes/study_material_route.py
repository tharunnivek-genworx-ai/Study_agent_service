# src/api/rest/routes/study_material_route.py
"""
Routes for study_material_versions.

  generate    → POST  /nodes/{node_id}/study-material/generate
  regenerate  → POST  /nodes/{node_id}/study-material/regenerate
  improve     → POST  /nodes/{node_id}/study-material/improve
  manual_edit → PATCH /nodes/{node_id}/study-material/manual-edit
  publish     → PATCH /nodes/{node_id}/study-material/publish
  activate    → PATCH /nodes/{node_id}/study-material/activate
  versions    → GET   /nodes/{node_id}/study-material/versions
  version     → GET   /nodes/{node_id}/study-material/versions/{version_id}
  trainee routes → see ``trainee_study_routes`` (GET study-material, PDF, panel, progress)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.study_agent_services.study_material_service import (
    StudyMaterialService,
)
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.schemas.study_material_schemas.study_material_schema import (
    SpacePublishedResourcesResponse,
    SpaceRepublishChecklistOut,
    StudyMaterialActivateRequest,
    StudyMaterialClearDraftsEligibilityOut,
    StudyMaterialClearDraftsOut,
    StudyMaterialFeedbackResponse,
    StudyMaterialGenerateRequest,
    StudyMaterialGenerateResponse,
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

router = APIRouter(tags=["Study Material"])


@router.post(
    "/nodes/{node_id}/study-material/generate",
    status_code=status.HTTP_201_CREATED,
    response_model=StudyMaterialGenerateResponse,
)
async def generate_study_material(
    node_id: UUID,
    payload: StudyMaterialGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialGenerateResponse:
    """Mentor triggers first-time study material generation."""
    service = StudyMaterialService(db)
    return await service.generate_study_material(
        node_id, payload, current_user.sub, current_user.role
    )


@router.post(
    "/nodes/{node_id}/study-material/regenerate",
    status_code=status.HTTP_201_CREATED,
    response_model=StudyMaterialFeedbackResponse,
)
async def regenerate_study_material(
    node_id: UUID,
    payload: StudyMaterialRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialFeedbackResponse:
    """Mentor rewrites the active draft with feedback. No LlamaParse re-run."""
    service = StudyMaterialService(db)
    return await service.regenerate_study_material(
        node_id, payload, current_user.sub, current_user.role
    )


@router.post(
    "/nodes/{node_id}/study-material/improve",
    status_code=status.HTTP_201_CREATED,
    response_model=StudyMaterialFeedbackResponse,
)
async def improve_study_material(
    node_id: UUID,
    payload: StudyMaterialImproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> StudyMaterialFeedbackResponse:
    """Mentor submits feedback to improve the current active version."""
    service = StudyMaterialService(db)
    return await service.improve_study_material(
        node_id, payload, current_user.sub, current_user.role
    )


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
