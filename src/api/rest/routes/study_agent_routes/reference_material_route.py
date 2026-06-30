# src/api/rest/routes/reference_material_route.py
"""
Routes for reference_materials and node_media.

Reference materials (TDD §3.3.2):
  Upload          → POST   /spaces/{space_id}/reference-materials
  List by space   → GET    /spaces/{space_id}/reference-materials
  List by node    → GET    /nodes/{node_id}/reference-materials
  Visibility      → PATCH  /reference-materials/{material_id}/visibility
  Delete          → DELETE /reference-materials/{material_id}

Node media:
  Attach          → POST   /nodes/{node_id}/media
  List            → GET    /nodes/{node_id}/media
                    GET    /nodes/{node_id}/media?reference_material_id=...
                    (reference_material_id returns ReferenceImageListOut)
  Reorder         → PATCH  /nodes/{node_id}/media/reorder
  Delete          → DELETE /nodes/{node_id}/media/{media_id}

Image uploads for node_media use multipart/form-data (UploadFile).
Reference material uploads also use multipart/form-data.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services import (
    ReferenceMaterialService,
)
from src.api.data.clients.postgres import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas import TokenPayload
from src.api.schemas.study_material_schemas import (
    NodeMediaAttachRequest,
    NodeMediaDeletedOut,
    NodeMediaListOut,
    NodeMediaOut,
    NodeMediaReorderRequest,
    NodeMediaType,
    ReferenceImageListOut,
    ReferenceMaterialDeletedOut,
    ReferenceMaterialListOut,
    ReferenceMaterialOut,
    ReferenceMaterialScope,
    ReferenceMaterialVisibilityUpdate,
)

router = APIRouter(tags=["Reference Materials & Node Media"])


# ── Reference Materials ──────────────────────────────────────────────────────


@router.post(
    "/spaces/{space_id}/reference-materials",
    response_model=ReferenceMaterialOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_reference_material(
    space_id: UUID,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=300),
    scope: ReferenceMaterialScope = Form(...),
    node_id: UUID | None = Form(default=None),
    is_visible_to_trainees: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> ReferenceMaterialOut:
    """Mentor uploads a reference PDF/doc to a space or a specific node.

    scope='space' → node_id must be None.
    scope='node'  → node_id is required.
    File is stored in GCS; row is inserted only after a successful upload.
    """
    service = ReferenceMaterialService(db)
    return await service.upload_reference_material(
        space_id=space_id,
        file=file,
        title=title,
        scope=scope,
        node_id=node_id,
        is_visible_to_trainees=is_visible_to_trainees,
        user_id=current_user.sub,
        role=current_user.role,
    )


@router.get(
    "/spaces/{space_id}/reference-materials",
    response_model=ReferenceMaterialListOut,
)
async def list_space_reference_materials(
    space_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> ReferenceMaterialListOut:
    """List all active reference materials scoped to a space (scope='space')."""
    service = ReferenceMaterialService(db)
    return await service.list_by_space(space_id, current_user.sub, current_user.role)


@router.get(
    "/nodes/{node_id}/reference-materials/latest",
    response_model=ReferenceMaterialOut | None,
)
async def get_latest_node_reference_material(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> ReferenceMaterialOut | None:
    """Return the most recently uploaded reference material for a node."""
    service = ReferenceMaterialService(db)
    return await service.get_latest_by_node(
        node_id, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/reference-materials",
    response_model=ReferenceMaterialListOut,
)
async def list_node_reference_materials(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> ReferenceMaterialListOut:
    """List all active reference materials scoped to a specific node (scope='node')."""
    service = ReferenceMaterialService(db)
    return await service.list_by_node(node_id, current_user.sub, current_user.role)


@router.patch(
    "/reference-materials/{material_id}/visibility",
    response_model=ReferenceMaterialOut,
)
async def update_reference_material_visibility(
    material_id: UUID,
    payload: ReferenceMaterialVisibilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> ReferenceMaterialOut:
    """Mentor toggles trainee visibility for an existing reference material.

    This is the only mutable field on a reference_material row post-upload (EC-17).
    """
    service = ReferenceMaterialService(db)
    return await service.update_visibility(
        material_id, payload, current_user.sub, current_user.role
    )


@router.delete(
    "/reference-materials/{material_id}",
    response_model=ReferenceMaterialDeletedOut,
)
async def delete_reference_material(
    material_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> ReferenceMaterialDeletedOut:
    """Mentor soft-deletes a reference material (sets deleted_at).

    The material_id on study_material_versions is frozen and unchanged (EC-17).
    """
    service = ReferenceMaterialService(db)
    return await service.delete_reference_material(
        material_id, current_user.sub, current_user.role
    )


# ── Node Media ───────────────────────────────────────────────────────────────


@router.post(
    "/nodes/{node_id}/media",
    response_model=NodeMediaOut,
    status_code=status.HTTP_201_CREATED,
)
async def attach_node_media(
    node_id: UUID,
    media_type: NodeMediaType = Form(...),
    title: str | None = Form(default=None),
    url: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> NodeMediaOut:
    """Mentor attaches media to a node.

    multipart/form-data fields:
      media_type — image | pdf | video_url | article_link
      title      — optional display label
      url        — required for video_url and article_link
      file       — required for image and pdf

    Cross-field validation is enforced at the service layer.
    """
    payload = NodeMediaAttachRequest(
        media_type=media_type,
        title=title.strip() if title and title.strip() else None,
        url=url.strip() if url and url.strip() else None,
    )
    service = ReferenceMaterialService(db)
    return await service.attach_media(
        node_id, payload, file, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/media",
    response_model=NodeMediaListOut | ReferenceImageListOut,
)
async def list_node_media(
    node_id: UUID,
    reference_material_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> NodeMediaListOut | ReferenceImageListOut:
    """List mentor media for a node, or reference LlamaParse images when scoped by PDF."""
    service = ReferenceMaterialService(db)
    return await service.list_media(
        node_id,
        current_user.sub,
        current_user.role,
        reference_material_id=reference_material_id,
    )


@router.patch(
    "/nodes/{node_id}/media/reorder",
    status_code=status.HTTP_200_OK,
)
async def reorder_node_media(
    node_id: UUID,
    payload: NodeMediaReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> dict[str, object]:
    """Bulk-update order_index for all active media items on a node.

    Partial reorders are rejected — payload must include every active media_id.
    """
    service = ReferenceMaterialService(db)
    return await service.reorder_media(
        node_id, payload, current_user.sub, current_user.role
    )


@router.delete(
    "/nodes/{node_id}/media/{media_id}",
    response_model=NodeMediaDeletedOut,
)
async def delete_node_media(
    node_id: UUID,
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> NodeMediaDeletedOut:
    """Mentor removes a media item from a node (hard delete — no soft-delete for media)."""
    service = ReferenceMaterialService(db)
    return await service.delete_media(
        node_id, media_id, current_user.sub, current_user.role
    )
