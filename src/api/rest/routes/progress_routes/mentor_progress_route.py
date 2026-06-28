# C:\CapStone\study_agent_service\src\api\rest\routes\progress_routes\mentor_progress_route.py
"""Progress routes: scroll-progress update (trainee) and space progress
dashboard (mentor).

Role guards:
  Trainee — PATCH /nodes/:node_id/study-material/progress
              Update scroll read_percent for a node's published study material.
  Mentor  — GET /spaces/:space_id/progress
              Full per-trainee progress breakdown for all enrolled trainees.
            POST /spaces/:space_id/progress/recompute
              Fan-out space-level progress cache refresh for all trainees.

current_user is injected by get_current_user which decodes the JWT and
returns a TokenPayload.

TDD §3.5.3 (Mentor API) and §3.5.4 (Trainee API).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.progress_services.mentor_progress_service import (
    MentorProgressService,
)
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.schemas.progress_schemas.mentor_progress_schema import (
    MentorSpaceProgressOut,
    MentorSpaceProgressSummaryOut,
    NodeDeleteContentCascadeRequest,
    NodeDeletePreviewOut,
    NodeDeletePreviewRequest,
)

router = APIRouter(tags=["Progress"])


@router.get(
    "/spaces/{space_id}/progress",
    response_model=MentorSpaceProgressOut,
)
async def get_space_progress(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> MentorSpaceProgressOut:
    """Mentor retrieves the full per-trainee progress breakdown for a space.

    Returns all enrolled trainees with their node-level progress detail,
    space-level rollup counts, and derived progress percentages.

    Ordered by overall_progress_percentage DESC (most advanced first).

    EC-23: total_nodes reflects the latest recomputed count of active nodes
    with >= 1 published study material version at query time.
    EC-27: space ownership resolved via COALESCE(transferred_to_mentor_id,
    mentor_id) — transferred spaces are fully accessible to the new owner.
    """
    service = MentorProgressService(db)
    return await service.get_space_progress(
        space_id=space_id,
        user_id=current_user.sub,
        role=current_user.role,
    )


@router.get(
    "/spaces/{space_id}/progress/summary",
    response_model=MentorSpaceProgressSummaryOut,
)
async def get_space_progress_summary(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> MentorSpaceProgressSummaryOut:
    """Mentor retrieves a lightweight summary (total nodes & enrolled trainees) for a space."""
    service = MentorProgressService(db)
    return await service.get_space_progress_summary(
        space_id=space_id,
        user_id=current_user.sub,
        role=current_user.role,
    )


@router.post(
    "/spaces/{space_id}/progress/recompute",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def recompute_space_progress(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> None:
    """Mentor triggers a space-level progress cache refresh for all trainees.

    Used after Identity-side mutations (node archive, space unpublish) that
    change eligible learning units without study_agent publish hooks.
    Per-trainee failures are logged and skipped; returns 204 on acceptance.
    """
    service = MentorProgressService(db)
    await service.recompute_space_progress_for_space(
        space_id=space_id,
        user_id=current_user.sub,
        role=current_user.role,
    )


@router.post(
    "/spaces/{space_id}/nodes/delete-preview",
    response_model=NodeDeletePreviewOut,
)
async def preview_deleted_node_content(
    space_id: UUID,
    payload: NodeDeletePreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> NodeDeletePreviewOut:
    """Return live study material and quiz counts before topic deletion."""
    service = MentorProgressService(db)
    return await service.preview_deleted_node_content(
        space_id=space_id,
        node_ids=payload.node_ids,
        user_id=current_user.sub,
        role=current_user.role,
    )


@router.post(
    "/spaces/{space_id}/nodes/delete-content-cascade",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cascade_deleted_node_content(
    space_id: UUID,
    payload: NodeDeleteContentCascadeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> None:
    """Unpublish live study material and quizzes after mentor deletes topic nodes.

    Called immediately after Identity PATCH /nodes/:id/archive so published
    content is not left active on invisible nodes.
    """
    service = MentorProgressService(db)
    await service.cascade_deleted_node_content(
        space_id=space_id,
        node_ids=payload.node_ids,
        user_id=current_user.sub,
        role=current_user.role,
    )
