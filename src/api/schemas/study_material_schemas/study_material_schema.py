# C:\CapStone\study_agent_service\src\api\schemas\study_material_schemas\study_material_schema.py
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
from enum import StrEnum
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.api.schemas.common.generation_diagnostics_schema import (
    GenerationDiagnosticsOut,
    QualityCheckItemOut,
)
from src.api.utils.study_agent_utils.mentor.mentor_display_badge import (
    compute_mentor_display_badge,
    compute_student_visibility_hint,
)
from src.api.utils.study_agent_utils.version.version_labels import (
    build_version_display_label,
    truncate_feedback,
)


class QualityCheckScoresOut(BaseModel):
    """Individual dimension scores from the QC evaluator."""

    content_accuracy: int | None = None
    code_quality: int | None = None
    section_depth: int | None = None
    teaching_alignment: int | None = None


class QualityCheckResultOut(BaseModel):
    """Structured QC evaluation result surfaced to the frontend.

    Included in API responses when QC permanently fails (all 3 attempts
    exhausted) so the mentor can see what quality issues were detected.
    """

    overall_status: Literal["pass", "warn", "fail"]
    is_refusal: bool = False
    hallucination_risk: Literal["none", "low", "medium", "high"]
    scores: QualityCheckScoresOut
    checks: list[QualityCheckItemOut] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    corrective_instructions: str = ""
    summary: str = ""
    must_cover_checklist: list[dict[str, Any]] | None = None
    qc_llm_model_used: str | None = None
    qc_llm_models_used: dict[str, str | None] | None = None
    checklist_llm_model_used: str | None = None
    qc_extraction: dict[str, Any] | None = None


# ── Enums / Literals ─────────────────────────────────────────────────────────

GenerationType = Literal["generate", "regenerate", "improve", "manual_edit"]


class RetentionMode(StrEnum):
    """How to treat content after unpublishing.

    remove_completely — hides the version entirely (not in Previous versions).
    keep_for_review   — archives the version so trainees can still open it.
    """

    remove_completely = "remove_completely"
    keep_for_review = "keep_for_review"


class _VersionRowLike(Protocol):
    """Minimal ORM row shape for building version summaries."""

    version_id: UUID
    version_number: int
    generation_type: GenerationType
    based_on_version_id: UUID | None
    mentor_feedback_used: str | None
    reference_material_id: UUID | None
    is_active: bool
    is_published: bool
    is_archived: bool
    archived_at: datetime | None
    published_at: datetime | None
    lifecycle_status: str
    created_by: UUID
    created_at: datetime


class StudyMaterialGenerateRequest(BaseModel):
    """
    Body for POST /nodes/:id/study-material/generate (first-time generation).

    reference_material_id is optional. When provided, the service fetches
    the file, extracts text via LlamaParse, and passes it as context to the LLM.
    """

    reference_material_id: UUID | None = Field(
        default=None,
        description=(
            "Optional: a reference_materials.material_id scoped to this node "
            "or its parent space. When set, extracted PDF text is passed to the LLM."
        ),
    )
    progress_session_id: UUID | None = Field(
        default=None,
        description="Client-generated session id for polling generation progress.",
    )


class StudyMaterialRegenerateRequest(BaseModel):
    """
    Body for POST /nodes/:id/study-material/regenerate.

    Requires an active version. The current draft and mentor feedback are passed
    to the LLM. LlamaParse is NOT re-run — cached reference text is reused when
    the active version was generated with a reference PDF.
    """

    mentor_regeneration_goal: str = Field(
        ...,
        min_length=10,
        max_length=4000,
        description=(
            "What is wrong with the current draft and what must improve in the rewrite."
        ),
    )
    progress_session_id: UUID | None = Field(
        default=None,
        description="Client-generated session id for polling generation progress.",
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
    progress_session_id: UUID | None = Field(
        default=None,
        description="Client-generated session id for polling generation progress.",
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
    to publish. Preview via GET publish-preview first when confirmation
    is required.
    """

    version_id: UUID = Field(
        ...,
        description="The study_material_versions.version_id to publish.",
    )
    superseded_retention_mode: RetentionMode | None = Field(
        default=None,
        description=(
            "When replacing a live version, controls the superseded edition. "
            "keep_for_review — moves it to Previous versions. "
            "remove_completely — hides it from students (not in Previous versions). "
            "Defaults to keep_for_review when omitted."
        ),
    )


class StudyMaterialPublishPreviewOut(BaseModel):
    """Pre-publish check returned before committing."""

    requires_confirmation: bool
    previous_version_label: str | None = None
    new_version_label: str
    is_republishing_older: bool = False
    current_published_version_label: str | None = None
    will_reset_trainee_read_progress: bool = False
    is_replacing_live_version: bool = False


class StudyMaterialUnpublishRequest(BaseModel):
    """Body for PATCH /nodes/:id/study-material/unpublish."""

    version_id: UUID = Field(..., description="The version_id to unpublish.")
    retention_mode: RetentionMode = Field(
        ...,
        description=(
            "remove_completely — hidden from students, not in Previous versions. "
            "keep_for_review — archived, accessible in Previous versions."
        ),
    )


class StudyMaterialUnpublishPreviewOut(BaseModel):
    """Pre-unpublish check returned before committing.

    Engagement counts are always present (zero when no activity yet) so the
    frontend can always render the impact block consistently.
    """

    requires_confirmation: bool
    version_label: str
    trainees_read_count: int = 0
    trainees_quiz_attempt_count: int = 0
    has_live_quiz: bool = False
    live_quiz_title: str | None = None


class VersionLineageItem(BaseModel):
    """One step in a version ancestry chain (parent → root)."""

    version_id: UUID
    version_number: int
    generation_type: GenerationType
    is_archived: bool


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
    is_archived: bool = False
    archived_at: datetime | None = None
    published_at: datetime | None
    published_by: UUID | None = None
    created_by: UUID
    created_at: datetime

    # ── Quality-Check fields (populated only on LLM-generated versions) ──
    qc_failed_permanently: bool = False
    qc_result: GenerationDiagnosticsOut | None = None
    qc_passed: bool = False
    qc_attempt_count: int = 0
    generation_run_id: str | None = None
    concept_plan: dict[str, Any] | None = None
    checklist_llm_model_used: str | None = None
    qc_verification_mode: Literal["full", "targeted"] | None = None
    qc_frozen_check_ids: list[str] | None = None
    qc_frozen_section_keys: list[str] | None = None
    next_llm_retry_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_label(self) -> str:
        return build_version_display_label(self.version_number, self.generation_type)


class StudyMaterialGenerateResponse(StudyMaterialVersionOut):
    """Generate endpoint response including durable run metadata for resume/progress."""

    run_id: UUID
    progress_session_id: UUID


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
    based_on_version_id: UUID | None = None
    based_on_version_number: int | None = None
    lineage_chain: list[VersionLineageItem] = Field(default_factory=list)
    mentor_feedback_preview: str | None = None
    reference_material_id: UUID | None = None
    is_active: bool
    is_published: bool
    is_archived: bool = False
    archived_at: datetime | None = None
    published_at: datetime | None
    lifecycle_status: str = "draft"
    mentor_display_badge: str
    student_visibility_hint: str | None = None
    created_by: UUID
    created_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def display_label(self) -> str:
        return build_version_display_label(self.version_number, self.generation_type)

    @classmethod
    def from_version_row(
        cls,
        version: _VersionRowLike,
        *,
        version_lookup: dict[UUID, _VersionRowLike] | None = None,
        viewing_version_id: UUID | None = None,
    ) -> "StudyMaterialVersionSummary":
        """Build summary with mentor-friendly display fields and lineage."""
        based_on_id = version.based_on_version_id
        based_on_number: int | None = None
        lineage_chain: list[VersionLineageItem] = []

        if version_lookup and based_on_id is not None:
            parent = version_lookup.get(based_on_id)
            if parent is not None:
                based_on_number = parent.version_number
            cursor_id: UUID | None = based_on_id
            seen: set[UUID] = set()
            while cursor_id is not None and cursor_id not in seen:
                seen.add(cursor_id)
                ancestor = version_lookup.get(cursor_id)
                if ancestor is None:
                    break
                lineage_chain.append(
                    VersionLineageItem(
                        version_id=ancestor.version_id,
                        version_number=ancestor.version_number,
                        generation_type=ancestor.generation_type,
                        is_archived=ancestor.is_archived,
                    )
                )
                cursor_id = ancestor.based_on_version_id

        data = {
            "version_id": version.version_id,
            "version_number": version.version_number,
            "generation_type": version.generation_type,
            "based_on_version_id": based_on_id,
            "based_on_version_number": based_on_number,
            "lineage_chain": lineage_chain,
            "mentor_feedback_preview": truncate_feedback(version.mentor_feedback_used),
            "reference_material_id": version.reference_material_id,
            "is_active": version.is_active,
            "is_published": version.is_published,
            "is_archived": version.is_archived,
            "archived_at": version.archived_at,
            "published_at": version.published_at,
            "lifecycle_status": version.lifecycle_status,
            "mentor_display_badge": compute_mentor_display_badge(
                is_published=version.is_published,
                lifecycle_status=version.lifecycle_status,
                is_archived=version.is_archived,
                published_at=version.published_at,
            ),
            "student_visibility_hint": compute_student_visibility_hint(
                is_published=version.is_published,
                lifecycle_status=version.lifecycle_status,
                is_archived=version.is_archived,
                published_at=version.published_at,
                is_viewing=(
                    viewing_version_id is not None
                    and viewing_version_id == version.version_id
                ),
            ),
            "created_by": version.created_by,
            "created_at": version.created_at,
        }
        return cls.model_validate(data)


class StudyMaterialVersionHistoryOut(BaseModel):
    """
    Returned by GET /nodes/:id/study-material/versions.
    Ordered by version_number descending (newest first).
    """

    node_id: UUID
    versions: list[StudyMaterialVersionSummary]
    total: int


class StudyMaterialClearDraftsEligibilityOut(BaseModel):
    """Whether the mentor can clear all study material drafts for a node."""

    can_clear: bool
    version_count: int
    quiz_count: int
    block_reason: str | None = None


class StudyMaterialClearDraftsOut(BaseModel):
    """Returned after DELETE /nodes/:id/study-material/drafts."""

    node_id: UUID
    discarded_count: int


class VersionAllowedActionsOut(BaseModel):
    version_id: UUID
    can_publish: bool
    can_unpublish: bool
    can_archive: bool
    can_edit_active_draft: bool
    is_viewing_non_active: bool
    is_viewing_archived: bool
    publish_button_label: str = "Make live for students"
    publish_disabled_tooltip: str | None = None
    unpublish_button_label: str = "Remove from students"
    unpublish_tooltip: str | None = None
    unpublish_disabled_tooltip: str | None = None


class MentorStudentVisibilityOut(BaseModel):
    """What students currently see on this topic."""

    live_material_label: str | None = None
    live_material_version_id: UUID | None = None
    previous_version_count: int = 0
    previous_version_labels: list[str] = Field(default_factory=list)
    live_quiz_title: str | None = None


class StudyMaterialMentorUiStateOut(BaseModel):
    """Mentor-facing study material UI state resolved by the backend."""

    node_id: UUID
    has_versions: bool
    has_workspace_versions: bool = False
    active_version_id: UUID | None
    published_version_id: UUID | None = None
    can_access_study_material: bool
    can_access_quiz: bool
    instruction_changed_since_generation: bool
    current_effective_instruction: str
    generation_instruction_snapshot: str | None
    displayed_version_actions: VersionAllowedActionsOut | None
    student_visibility: MentorStudentVisibilityOut


class TraineeStudyMaterialOut(BaseModel):
    """
    Trainee-safe view of published study material.
    Returned by GET /nodes/:id/study-material (trainee route).

    Strips all mentor/LLM internals: no prompt_snapshot, no token_usage,
    no mentor_feedback_used, no llm_model_used.

    Only is_published=TRUE versions are ever returned by the service
    that serves this schema — the filtering happens at query time.

    ``study_material_read_percent`` and ``study_material_completed`` are
    computed server-side from trainee_node_progress (not stored on the
    version row).
    """

    model_config = ConfigDict(from_attributes=True)

    version_id: UUID
    node_id: UUID
    space_id: UUID
    version_number: int
    content: str
    reference_material_id: UUID | None = None
    published_at: datetime | None
    study_material_read_percent: int = Field(default=0, ge=0, le=100)
    study_material_completed: bool = False


class TraineeArchivedSmItemOut(BaseModel):
    """Metadata for one superseded study material version in trainee archive."""

    version_id: UUID
    version_number: int
    version_label: str
    published_at: datetime | None
    superseded_at: datetime | None = None
    removed_at: datetime | None = None
    can_read_material: bool = True
    you_read_this: bool = False
    has_archived_quiz: bool = False
    archived_quiz_id: UUID | None = None
    is_current_version: bool = False


class TraineeArchivedSmListOut(BaseModel):
    """List of superseded SM versions for GET .../study-material/archive."""

    node_id: UUID
    versions: list[TraineeArchivedSmItemOut] = Field(default_factory=list)


class TraineeArchivedStudyMaterialOut(BaseModel):
    """Read-only archived SM body — no progress writes on this view."""

    version_id: UUID
    node_id: UUID
    space_id: UUID
    version_number: int
    version_label: str
    content: str
    reference_material_id: UUID | None = None
    published_at: datetime | None
    superseded_at: datetime | None = None
    is_archived_reference: bool = True


class PublishedResourceTopicSummary(BaseModel):
    node_id: UUID
    topic_title: str
    published_study_material_version_id: UUID | None = None
    published_quiz_id: UUID | None = None


class SpacePublishedResourcesResponse(BaseModel):
    space_id: UUID
    published_topics: list[PublishedResourceTopicSummary]


class RepublishChecklistNodeOut(BaseModel):
    """One node's publishable content after espace republish."""

    node_id: UUID
    node_title: str
    last_published_version_id: UUID | None = None
    last_published_version_label: str | None = None
    has_unpublished_quiz: bool = False
    quiz_id: UUID | None = None
    quiz_title: str | None = None


class SpaceRepublishChecklistOut(BaseModel):
    """Content summary shown after republishing an espace."""

    space_id: UUID
    nodes_with_publishable_material: list[RepublishChecklistNodeOut]


class StudyMaterialFeedbackResponse(BaseModel):
    has_new_version: bool
    new_version_id: UUID | None = None
    status: Literal["ok", "feedback_too_vague", "regeneration_goal_too_vague"]
    status_message: str | None = None
    new_version: StudyMaterialVersionOut | None = None

    # ── Quality-Check fields ──────────────────────────────────────
    qc_failed_permanently: bool = False
    qc_result: GenerationDiagnosticsOut | None = None
    next_llm_retry_at: datetime | None = None
    run_id: UUID | None = None
    progress_session_id: UUID | None = None
