# C:\CapStone\study_agent_service\src\api\schemas\study_material_schemas\node_media_schema.py
"""
Schemas for node_media table operations.

Three media types are supported (TDD §3.3.2):
  'image'        — file uploaded to GCS; file_url is set, url is None.
  'video_url'    — external link (YouTube, Loom, etc.); url is set, file_url None.
  'article_link' — external URL to a doc/article; url is set, file_url None.

url vs file_url cross-field constraint: enforced at service layer for the same
reason as ReferenceMaterialUploadRequest — cleaner than Pydantic root validators
on conditionally required fields.

order_index controls display order within the node's media panel.
Reordering is done via a bulk patch (list of media_ids in desired order),
same pattern as node sibling reorder in the Identity service.

LlamaParse figures extracted from reference PDFs are stored in
reference_llamaparse_images, not node_media.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Enums / Literals ─────────────────────────────────────────────────────────

NodeMediaType = Literal["image", "video_url", "article_link"]


# ── Request Schemas ──────────────────────────────────────────────────────────


class NodeMediaAttachRequest(BaseModel):
    """
    Body for POST /nodes/:id/media.
    For 'image' type: file bytes arrive via multipart UploadFile;
    this body carries the metadata fields only.
    For 'video_url' and 'article_link': url is required; no file upload.
    """

    media_type: NodeMediaType
    title: str | None = Field(default=None, max_length=300)
    url: str | None = Field(
        default=None,
        description="Required for video_url and article_link types.",
    )


class NodeMediaReorderRequest(BaseModel):
    """
    Body for PATCH /nodes/:id/media/reorder.
    media_ids must be the complete set of active media for the node —
    partial reorders are rejected (same guard as node sibling reorder).
    The list position implies the new order_index (0-indexed).
    """

    media_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="All active media_ids for the node in desired display order.",
    )


# ── Response Schemas ─────────────────────────────────────────────────────────


class NodeMediaOut(BaseModel):
    """Full representation of a mentor-attached node_media row."""

    model_config = ConfigDict(from_attributes=True)

    media_id: UUID
    node_id: UUID
    space_id: UUID
    media_type: NodeMediaType
    title: str | None
    url: str | None
    file_url: str | None
    public_url: str | None = Field(
        default=None,
        description="Browser-loadable URL resolved by the service.",
    )
    order_index: int
    uploaded_by: UUID
    created_at: datetime | None = None


class NodeMediaListOut(BaseModel):
    """
    Returned by GET /nodes/:id/media.
    Items are ordered by order_index ascending.
    """

    items: list[NodeMediaOut]
    total: int


class NodeMediaDeletedOut(BaseModel):
    """Confirmation after DELETE /nodes/:id/media/:media_id."""

    media_id: UUID
    deleted: bool = True
    message: str = "Media item removed successfully."
