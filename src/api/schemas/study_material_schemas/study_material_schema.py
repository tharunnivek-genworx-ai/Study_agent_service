# src/api/schemas/content_schemas/study_material_schema.py
"""
Schemas for study_material_versions table operations.

Generation modes (TDD §3.2.1):
  'generate'    — First or fresh generation. LLM input: node title +
                  effective teaching instruction + optional reference PDF text.
                  No prior content passed to LLM. Creates v1 (or vN if prior
                  versions exist for the node).

  'regenerate'  — Same inputs as generate; explicitly discards prior content.
                  Old versions are preserved (never deleted). Creates vN+1.

  'improve'     — Passes the current active version content + mentor feedback
                  to the LLM. Creates vN+1 with based_on_version_id pointing
                  to the parent. generation_type = 'improve'.

  'manual_edit' — Direct rich-text save from the editor. No LLM call.
                  Creates vN+1 with based_on_version_id pointing to the version
                  the mentor was viewing when they clicked Save.

Version activation rule: only one version per node has is_active=TRUE at a time.
This is enforced at the app/service layer, not by a DB constraint, because
flipping it requires an UPDATE on the previous active row plus an INSERT for
the new one — done atomically in a single transaction.

Publish rule: is_published=TRUE makes the version visible to trainees.
A version can be published without being the active working draft (mentor
can publish v2 but keep editing v3 as the active draft). Both flags are
independent.

SSE note: generate/regenerate/improve stream their output via Server-Sent Events.
The request bodies here are what the client POSTs to kick off the stream.
The SSE event payload is a plain text stream; no Pydantic schema is needed
for that — FastAPI's StreamingResponse handles it directly.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Enums / Literals ─────────────────────────────────────────────────────────

GenerationType = Literal["generate", "regenerate", "improve", "manual_edit"]


# ── Request Schemas ──────────────────────────────────────────────────────────


class StudyMaterialGenerateRequest(BaseModel):
    """
    Body for POST /nodes/:id/study-material/generate
    when generation_type is 'generate' or 'regenerate'.

    reference_material_id is optional. When provided, the service fetches
    the file from GCS, extracts text via LlamaParse, and passes it as
    context to the LLM. When absent, the LLM generates from the node's
    title and effective teaching instruction alone.

    The effective teaching instruction is resolved at the service layer
    (node_specific_instruction → nearest ancestor treedefaultinstruction)
    and is not a client-supplied field.
    """

    generation_type: Literal["generate", "regenerate"]
    reference_material_id: UUID | None = Field(
        default=None,
        description=(
            "Optional: a reference_materials.material_id scoped to this node "
            "or its parent space. When set, extracted PDF text is passed to the LLM."
        ),
    )


class StudyMaterialImproveRequest(BaseModel):
    """
    Body for POST /nodes/:id/study-material/improve.

    mentor_feedback is the only required field beyond the node_id in the path.
    The service resolves which version to improve from (the current is_active=TRUE
    version) without the client needing to supply a version_id. If the mentor
    wants to improve a specific non-active version, they must first activate it —
    this keeps the improve semantics simple and unambiguous.

    based_on_version_id is set by the service internally, not by the client.
    """

    mentor_feedback: str = Field(
        ...,
        min_length=10,
        max_length=4000,
        description="Mentor's improvement instructions sent to the LLM.",
    )


class StudyMaterialManualEditRequest(BaseModel):
    """
    Body for PATCH /nodes/:id/study-material/manual-edit.

    The mentor submits the full edited content from the rich-text editor.
    The service creates a new version row (generation_type='manual_edit')
    with based_on_version_id pointing to whichever version was is_active at
    save time. No LLM call is made.

    content is the full Markdown/rich-text string — no length cap enforced
    at schema level since study material can legitimately be long. Service
    layer may impose a soft warn at very high token counts for downstream
    LLM calls (improve, quiz generation).
    """

    content: str = Field(
        ...,
        min_length=1,
        description="Full Markdown/rich-text content saved by the mentor.",
    )


class StudyMaterialPublishRequest(BaseModel):
    """
    Body for PATCH /nodes/:id/study-material/publish.

    version_id is required — the mentor explicitly chooses which version
    to publish. This prevents accidental publish of a draft the mentor
    was still editing. The service validates that the version belongs to
    this node and is not already published.
    """

    version_id: UUID = Field(
        ...,
        description="The study_material_versions.version_id to publish.",
    )


class StudyMaterialActivateRequest(BaseModel):
    """
    Body for PATCH /nodes/:id/study-material/activate.

    Sets a specific version as the active working draft (is_active=TRUE).
    Used when a mentor wants to branch from or restore an older version.
    The service atomically deactivates the current active version and
    activates the requested one.
    """

    version_id: UUID = Field(
        ...,
        description="The version_id to set as the active working draft.",
    )


# ── Response Schemas ─────────────────────────────────────────────────────────


class StudyMaterialVersionOut(BaseModel):
    """
    Full representation of a study_material_versions row.
    Returned after any write operation (generate, improve, edit, publish, activate).
    Also used in the version history list.

    Fields intentionally omitted from trainee-facing responses
    (prompt_snapshot, token_usage, llm_model_used, mentor_feedback_used)
    are still present here because this schema is for mentor-facing endpoints.
    A separate TraineeStudyMaterialOut below strips those fields.
    """

    model_config = ConfigDict(from_attributes=True)

    version_id: UUID
    node_id: UUID
    space_id: UUID
    version_number: int
    content: str
    generation_type: GenerationType
    mentor_feedback_used: str | None
    reference_material_id: UUID | None
    based_on_version_id: UUID | None
    llm_model_used: str | None
    prompt_snapshot: str | None
    token_usage: int | None
    is_active: bool
    is_published: bool
    published_at: datetime | None
    published_by: UUID | None
    created_by: UUID
    created_at: datetime


class StudyMaterialVersionSummary(BaseModel):
    """
    Lightweight version row for the version history list.
    Omits full content and prompt_snapshot to keep list payloads lean.
    The frontend uses this to build the version history sidebar —
    clicking a version loads the full StudyMaterialVersionOut.
    """

    model_config = ConfigDict(from_attributes=True)

    version_id: UUID
    version_number: int
    generation_type: GenerationType
    is_active: bool
    is_published: bool
    published_at: datetime | None
    created_by: UUID
    created_at: datetime


class StudyMaterialVersionHistoryOut(BaseModel):
    """
    Returned by GET /nodes/:id/study-material/versions.
    Ordered by version_number descending (newest first).
    """

    node_id: UUID
    versions: list[StudyMaterialVersionSummary]
    total: int


class TraineeStudyMaterialOut(BaseModel):
    """
    Trainee-safe view of published study material.
    Returned by GET /nodes/:id/study-material (trainee route).

    Strips all mentor/LLM internals: no prompt_snapshot, no token_usage,
    no mentor_feedback_used, no llm_model_used.

    Only is_published=TRUE versions are ever returned by the service
    that serves this schema — the filtering happens at query time.
    """

    model_config = ConfigDict(from_attributes=True)

    version_id: UUID
    node_id: UUID
    space_id: UUID
    version_number: int
    content: str
    published_at: datetime | None
