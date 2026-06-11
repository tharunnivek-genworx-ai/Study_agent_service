# src/api/schemas/content_schemas/reference_material_schema.py
"""
Schemas for reference_materials table operations.

Scope rules (from TDD §3.3.2):
  scope='space'  — material attached to the space itself; node_id is NULL.
  scope='node'   — material attached to a specific node; node_id is required.

Immutability rule: reference_materials rows are never updated in place.
A replacement upload creates a NEW row with a new material_id and soft-deletes
the old one. The reference_material_id on study_material_versions is frozen at
generation time and never changed — so version lineage stays intact even if
the source PDF is replaced (EC-17).

is_visible_to_trainees controls whether the file appears in the trainee-facing
Resources panel. Mentors always see all active materials regardless.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Enums / Literals ─────────────────────────────────────────────────────────

ReferenceMaterialScope = Literal["space", "node"]


# ── Request Schemas ──────────────────────────────────────────────────────────


class ReferenceMaterialUploadRequest(BaseModel):
    """
    Body fields accompanying a multipart/form-data upload.
    The actual file bytes are handled by FastAPI's UploadFile;
    these fields are sent as form fields alongside the file.

    node_id is required when scope='node', must be None when scope='space'.
    Validation of this constraint is enforced at the service layer, not here,
    because cross-field conditional validation on UUID optionals is cleaner
    in service code than in Pydantic validators.
    """

    title: str = Field(..., min_length=1, max_length=300)
    scope: ReferenceMaterialScope
    node_id: UUID | None = Field(
        default=None,
        description="Required when scope='node'. Must be None when scope='space'.",
    )
    is_visible_to_trainees: bool = Field(
        default=True,
        description="Whether trainees see this file in their Resources panel.",
    )


class ReferenceMaterialVisibilityUpdate(BaseModel):
    """
    Used by PATCH /reference-materials/:id/visibility.
    Allows mentor to toggle trainee visibility without replacing the file.
    This is the only mutable field on a reference_material row post-upload.
    """

    is_visible_to_trainees: bool


# ── Response Schemas ─────────────────────────────────────────────────────────


class ReferenceMaterialOut(BaseModel):
    """
    Full representation of a reference_materials row.
    Returned on upload and on individual fetch.
    file_url is a GCS signed URL — time-limited, generated fresh on each response.
    """

    model_config = ConfigDict(from_attributes=True)

    material_id: UUID
    space_id: UUID
    node_id: UUID | None
    title: str
    file_url: str
    file_name: str
    file_size_bytes: int | None
    mime_type: str
    scope: ReferenceMaterialScope
    is_visible_to_trainees: bool
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class ReferenceMaterialListOut(BaseModel):
    """
    Returned by GET /spaces/:id/reference-materials and
    GET /nodes/:id/reference-materials.
    Not paginated — reference materials per node/space are expected to be small
    sets. If this changes, wrap in PaginatedResponse[ReferenceMaterialOut].
    """

    items: list[ReferenceMaterialOut]
    total: int


class ReferenceMaterialDeletedOut(BaseModel):
    """
    Confirmation response after a soft-delete (replacement upload or
    explicit delete). The deleted material_id is echoed back so the
    frontend can remove it from local state without a refetch.
    """

    material_id: UUID
    deleted: bool = True
    message: str = "Reference material removed successfully."
