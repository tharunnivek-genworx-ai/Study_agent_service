# C:\CapStone\study_agent_service\src\api\schemas\progress_schemas\mentor_progress_schema.py
from uuid import UUID

from pydantic import BaseModel, Field

from src.api.schemas.progress_schemas.trainee_progress_schema import (
    TraineeSpaceSummaryOut,
)


class MentorSpaceProgressOut(BaseModel):
    """
    Top-level response for GET /spaces/:id/progress (mentor route).

    Returns a per-trainee progress breakdown for the entire space, ordered
    by overall_progress_percentage DESC (most advanced trainees first).

    space_id and total_nodes are echoed back so the frontend can render
    the space header without an extra lookup.

    EC-23: total_nodes is consistent across all trainee rows — it reflects
    the service-recomputed count of active nodes with >= 1 published
    study material version.

    trainees_with_no_activity is the count of enrolled trainees who have
    not yet opened any study material (all completion_status='not_started').
    Useful for the mentor's at-a-glance dashboard summary.
    """

    space_id: UUID
    space_name: str
    total_nodes: int
    total_enrolled_trainees: int
    trainees_with_no_activity: int
    trainees: list[TraineeSpaceSummaryOut] = Field(default_factory=list)


class MentorSpaceProgressSummaryOut(BaseModel):
    """Lightweight progress summary response for a space."""

    space_id: UUID
    space_name: str
    total_nodes: int
    total_enrolled_trainees: int


class NodeDeleteContentCascadeRequest(BaseModel):
    """Body for POST /spaces/:id/nodes/delete-content-cascade."""

    node_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Topic node ids soft-deleted via PATCH /nodes/:id/archive.",
    )


class NodeDeletePreviewRequest(BaseModel):
    """Body for POST /spaces/:id/nodes/delete-preview."""

    node_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Topic node ids that will be soft-deleted (node + descendants).",
    )


class NodeDeletePreviewOut(BaseModel):
    """Live content counts shown before mentor confirms topic deletion."""

    live_study_material_count: int = Field(
        ...,
        ge=0,
        description="Published study material versions visible to trainees.",
    )
    live_quiz_count: int = Field(
        ...,
        ge=0,
        description="Published quizzes visible to trainees.",
    )
    topic_count: int = Field(
        ...,
        ge=1,
        description="Number of topic nodes that will be deleted.",
    )
