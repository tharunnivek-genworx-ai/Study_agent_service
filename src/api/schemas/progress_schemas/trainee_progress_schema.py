# src/api/schemas/content_schemas/progress_schema.py
"""
Schemas for trainee_node_progress and trainee_space_progress.

Progress model (TDD §3.2.4):
  Node-level (trainee_node_progress):
    - Study material portion (50%): study_material_completed=True when
      scroll read_percent reaches 100.
    - Quiz portion (50%): quiz_passed=True when best attempt score >= threshold.
    - completion_status:
        'not_started'  — neither component started.
        'in_progress'  — at least one component partially or fully satisfied.
        'completed'    — all current requirements satisfied (see EC-21 when no quiz).

  Space-level (trainee_space_progress):
    - total_nodes  = active nodes with >= 1 published study material version.
    - completed_nodes = eligible nodes where live completion derivation is
      ``completed`` for this trainee (not stale stored status).
    - Recomputed on tree changes and publish/unpublish events.

API endpoints covered (TDD §3.5.3 & §3.5.4):
  TRAINEE:
    PATCH /nodes/:id/study-material/progress
      — TraineeProgressUpdateRequest → TraineeNodeProgressOut
  MENTOR:
    GET /spaces/:id/progress
      — (no request body) → MentorSpaceProgressOut (mentor_progress_schema)

Edge cases (TDD §3.6):
  EC-20 — New quiz resets completion: quiz_passed=False, completion_status
           rolls back to 'in_progress' when a new quiz is published
           (handled by service on publish; not a trainee-triggered update).
  EC-21 — Study material done but no published quiz: counts as fully complete
           (progress_percentage=100, completion_status='completed').
           Once a quiz is published, both reading and a passing score are required.
  EC-22 — quiz_best_score=MAX() across attempts; quiz_passed stays True
           once achieved even if later attempts score lower.
  EC-23 — Space progress recomputed by service on tree/publish changes;
           stale reads are bounded by polling frequency.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Enums / Literals ──────────────────────────────────────────────────────────

CompletionStatus = Literal["not_started", "in_progress", "completed"]


# ─────────────────────────────────────────────────────────────────────────────
# TRAINEE-FACING: Study Material Scroll Progress Update
# ─────────────────────────────────────────────────────────────────────────────


class TraineeProgressUpdateRequest(BaseModel):
    """
    Body for PATCH /nodes/:id/study-material/progress.

    Sent by the frontend as the trainee scrolls through published study material.
    read_percent is 0–100; the service accepts it only if it is >= the current
    stored value (scroll progress is monotonically increasing — EC-22 analogue
    for read progress).

    The service sets study_material_completed=True when read_percent reaches 100
    and upserts the trainee_node_progress row, creating it if this is the
    trainee's first interaction with the node.

    first_viewed_at is recorded on the first write (when study_material_viewed
    transitions from False to True); last_viewed_at is updated on every write.
    """

    read_percent: int = Field(
        ...,
        ge=0,
        le=100,
        description=(
            "Current scroll percentage (0–100). Must not be lower than the "
            "currently stored value — scroll progress is monotonically increasing."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# TRAINEE-FACING: Node Progress Response
# ─────────────────────────────────────────────────────────────────────────────


class TraineeNodeProgressOut(BaseModel):
    """
    Returned after PATCH /nodes/:id/study-material/progress.
    Carries the full updated node progress state so the frontend can
    immediately update the progress bar and completion indicators
    without a separate GET call.

    progress_percentage is computed at the service layer:
      study_material portion = 50 if study_material_completed else 0
      quiz portion           = 50 if quiz_passed else 0
      total                  = study_material_portion + quiz_portion

    EC-21: if no quiz exists for the node, finishing the study material counts
    as completed with progress_percentage=100. Once a quiz is published,
    completion requires both reading and a passing score (50% each).
    EC-22: quiz_passed remains True once achieved regardless of later
    attempt scores.
    """

    model_config = ConfigDict(from_attributes=True)

    progress_id: UUID
    trainee_id: UUID
    node_id: UUID
    space_id: UUID

    # Study material component
    study_material_viewed: bool
    first_viewed_at: datetime | None
    last_viewed_at: datetime | None
    study_material_read_percent: int
    study_material_completed: bool

    # Quiz component
    quiz_best_score: float | None
    quiz_attempt_count: int
    quiz_passed: bool

    # Derived completion state
    completion_status: CompletionStatus
    progress_percentage: int = Field(
        ...,
        ge=0,
        le=100,
        description=(
            "Overall node progress as a percentage (0, 50, or 100). "
            "50 = study material complete only; 100 = both components done."
        ),
    )

    updated_at: datetime


class TraineeNodeProgressBatchItemOut(BaseModel):
    """
    Lightweight per-node progress snapshot for batch reads.

    Returned by ``GET /trainee/nodes/progress/batch`` and consumed internally
    by ``TraineeNodePanelService`` when assembling the topic detail panel.
    Nodes with no stored row yet are omitted from the list — callers treat
    missing ids as ``not_started``.
    """

    node_id: UUID
    study_material_read_percent: int = Field(default=0, ge=0, le=100)
    study_material_completed: bool = False
    quiz_passed: bool = False
    quiz_attempt_count: int = 0
    completion_status: CompletionStatus = "not_started"
    progress_percentage: int = Field(default=0, ge=0, le=100)


class TraineeNodeProgressBatchRequest(BaseModel):
    """Body for POST /trainee/nodes/progress/batch."""

    node_ids: list[UUID] = Field(..., min_length=1)


class TraineeNodeProgressBatchOut(BaseModel):
    """Batch progress response keyed by the requested node ids."""

    node_progress: list[TraineeNodeProgressBatchItemOut] = Field(default_factory=list)


class TraineeNodeProgressSummaryOut(BaseModel):
    """
    Per-node progress summary for a single trainee.
    Nested inside TraineeSpaceSummaryOut for the mentor dashboard.
    Includes node title (denormalized from topic_nodes at query time)
    so the frontend can render the tree without a secondary lookup.

    is_active=False means the node was soft-deleted after the trainee started it;
    the frontend renders it with a '(Deleted)' label (EC-3). Deleted nodes
    are excluded from both total_nodes and completed_nodes when space progress
    is calculated (live rollup treats them as removed from the course).
    """

    model_config = ConfigDict(from_attributes=True)

    node_id: UUID
    node_title: str
    node_level: int
    is_active: bool

    study_material_completed: bool
    study_material_read_percent: int
    quiz_passed: bool
    quiz_best_score: float | None
    quiz_attempt_count: int
    completion_status: CompletionStatus
    progress_percentage: int = Field(..., ge=0, le=100)
    last_viewed_at: datetime | None
    updated_at: datetime


class TraineeSpaceSummaryOut(BaseModel):
    """
    Full progress summary for a single trainee within the space.
    Used to populate each trainee row in the mentor's progress dashboard and
    also for the trainee's own progress dashboard
    (GET /spaces/:id/progress).

    overall_progress_percentage is derived at the service layer:
      (completed_nodes / total_nodes) * 100, rounded to nearest integer.
      Returns 0 when total_nodes=0 (no published content yet).

    EC-23: total_nodes is recomputed on tree and publish changes;
    the value here reflects the latest recomputed state.
    """

    model_config = ConfigDict(from_attributes=True)

    trainee_id: UUID
    trainee_full_name: str
    trainee_email: str

    # Space-level rollup (from trainee_space_progress)
    total_nodes: int
    completed_nodes: int
    overall_score_avg: float | None = Field(
        default=None,
        description=(
            "Average of quiz_best_score across all nodes the trainee has attempted. "
            "None if no quiz attempts exist yet."
        ),
    )
    overall_progress_percentage: int = Field(
        ...,
        ge=0,
        le=100,
        description="(completed_nodes / total_nodes) * 100, rounded. 0 if total_nodes=0.",
    )
    last_activity_at: datetime | None

    # Per-node breakdown
    node_progress: list[TraineeNodeProgressSummaryOut] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# SHARED: Lightweight node-level progress for trainee self-view
# ─────────────────────────────────────────────────────────────────────────────


class TraineeOwnSpaceProgressOut(BaseModel):
    """
    Trainee self-view of their progress in a space.
    Returned on GET /spaces/:id/progress (trainee route, if implemented).

    This schema is a lighter variant of ``MentorSpaceProgressOut`` (see
    ``mentor_progress_schema``) scoped to a single trainee — it omits other
    trainees' data entirely.
    The service filters trainee_node_progress to the requesting trainee_id.

    Included here as a defined contract so the trainee-facing endpoint
    can be added in a later sprint without a schema change.
    """

    model_config = ConfigDict(from_attributes=True)

    space_id: UUID
    space_name: str
    trainee_id: UUID

    # Space-level rollup
    total_nodes: int
    completed_nodes: int
    overall_progress_percentage: int = Field(..., ge=0, le=100)
    overall_score_avg: float | None = None
    overall_score_percentage: int | None = Field(default=None, ge=0, le=100)
    last_activity_at: datetime | None

    # Per-node breakdown
    node_progress: list[TraineeNodeProgressSummaryOut] = Field(default_factory=list)
