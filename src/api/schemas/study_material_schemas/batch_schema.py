"""Pydantic request/response contracts for study-material batch queue APIs.

The schema set is intentionally split by UI use-case:
- preview contracts (plan + warnings)
- enqueue input (roots + policy)
- queue snapshot contracts (running/queued/current progress)
- detail and cancel responses
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

BatchStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
BatchItemStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "failed_retryable",
    "skipped",
    "cancelled",
]
ExistingMaterialPolicy = Literal["skip", "regenerate"]


class BatchRootOut(BaseModel):
    """Minimal root-topic metadata used in preview response."""

    node_id: UUID
    title: str


class BatchPreviewItemOut(BaseModel):
    """One planned item in preorder traversal for the selected roots."""

    node_id: UUID
    title: str
    depth_level: int
    path_node_ids: list[UUID]
    path_titles: list[str]
    root_segment_node_id: UUID
    root_segment_title: str
    can_generate: bool = True
    block_reason: str | None = None


class BatchWarningNodeOut(BaseModel):
    """Node reference for preview warnings (instruction related)."""

    node_id: UUID
    title: str
    path_titles: list[str] = Field(default_factory=list)


class BatchPreviewWarningsOut(BaseModel):
    """Grouped warning sets used by multi-step confirmation modal."""

    missing_instruction_nodes: list[BatchWarningNodeOut] = Field(default_factory=list)
    inherits_section_default_nodes: list[BatchWarningNodeOut] = Field(
        default_factory=list
    )
    show_no_instruction_warning: bool = False
    show_inheritance_warning: bool = False


class StudyMaterialBatchPreviewResponse(BaseModel):
    """Payload returned by preview endpoint before enqueue."""

    roots: list[BatchRootOut]
    items: list[BatchPreviewItemOut]
    warnings: BatchPreviewWarningsOut


class StudyMaterialBatchPreviewRequest(BaseModel):
    """Input for preview endpoint (empty means all roots in space)."""

    root_node_ids: list[UUID] = Field(default_factory=list)


class StudyMaterialBatchPolicyIn(BaseModel):
    """Batch execution policy selected by mentor in enqueue modal."""

    existing_material_policy: ExistingMaterialPolicy = "skip"
    failure_policy: Literal["continue_on_error"] = "continue_on_error"
    reference_material_id: UUID | None = None


class StudyMaterialBatchEnqueueRequest(BaseModel):
    """Input for enqueue endpoint (selected roots + policy)."""

    root_node_ids: list[UUID] = Field(default_factory=list)
    policy: StudyMaterialBatchPolicyIn = Field(
        default_factory=StudyMaterialBatchPolicyIn
    )


class BatchSummaryOut(BaseModel):
    """Queue-list level batch metadata and counters."""

    batch_id: UUID
    space_id: UUID
    mentor_id: UUID
    status: BatchStatus
    queue_position: int
    selected_root_node_ids: list[UUID] = Field(default_factory=list)
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    skipped_items: int = 0
    current_item_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class BatchCurrentItemOut(BaseModel):
    """Current/expanded item shape with run linkage and breadcrumb metadata."""

    item_id: UUID
    node_id: UUID
    node_title: str
    depth_level: int
    path_titles: list[str] = Field(default_factory=list)
    generation_run_id: UUID | None = None
    run_status: str | None = None
    status: BatchItemStatus
    error_message: str | None = None


class BatchRootSegmentProgressOut(BaseModel):
    """Progress within currently active selected root segment."""

    root_node_id: UUID
    root_title: str
    completed: int
    total: int


class BatchOverallProgressOut(BaseModel):
    """Top-level progress counters for currently running batch."""

    completed: int
    total: int
    failed: int
    skipped: int


class StudyMaterialSpaceQueueOut(BaseModel):
    """Primary queue snapshot contract consumed by polling driver."""

    running_batch: BatchSummaryOut | None = None
    recent_terminal_batch: BatchSummaryOut | None = None
    queued_batches: list[BatchSummaryOut] = Field(default_factory=list)
    needs_advance: bool = False
    advance_deferred: bool = False
    overall_progress: BatchOverallProgressOut = Field(
        default_factory=lambda: BatchOverallProgressOut(
            completed=0, total=0, failed=0, skipped=0
        )
    )
    current_root_segment: BatchRootSegmentProgressOut | None = None
    current_item: BatchCurrentItemOut | None = None


class StudyMaterialBatchDetailOut(BaseModel):
    """Batch detail payload (summary + item list)."""

    batch: BatchSummaryOut
    items: list[BatchCurrentItemOut]


class StudyMaterialBatchCancelResponse(BaseModel):
    """Response after batch cancel operation is accepted."""

    batch_id: UUID
    status: BatchStatus
