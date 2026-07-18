"""Lean API contracts for Procrastinate-backed batch generate-all jobs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

BatchJobStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
BatchStepStatus = Literal["pending", "running", "completed", "failed", "skipped"]
BatchPolicyMode = Literal["skip_existing", "regenerate_all"]


class BatchRootOut(BaseModel):
    node_id: UUID
    title: str


class BatchPreviewItemOut(BaseModel):
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
    node_id: UUID
    title: str
    path_titles: list[str] = Field(default_factory=list)


class BatchPreviewWarningsOut(BaseModel):
    missing_instruction_nodes: list[BatchWarningNodeOut] = Field(default_factory=list)
    inherits_section_default_nodes: list[BatchWarningNodeOut] = Field(
        default_factory=list
    )
    show_no_instruction_warning: bool = False
    show_inheritance_warning: bool = False


class BatchPreviewRequest(BaseModel):
    root_node_ids: list[UUID] = Field(default_factory=list)
    node_ids: list[UUID] = Field(default_factory=list)


class BatchPreviewResponse(BaseModel):
    roots: list[BatchRootOut]
    items: list[BatchPreviewItemOut]
    warnings: BatchPreviewWarningsOut


class BatchPolicyIn(BaseModel):
    mode: BatchPolicyMode = "skip_existing"
    reference_material_id: UUID | None = None
    external_research_node_ids: list[UUID] = Field(default_factory=list)


class BatchCreateRequest(BaseModel):
    root_node_ids: list[UUID] = Field(default_factory=list)
    node_ids: list[UUID] = Field(default_factory=list)
    policy: BatchPolicyIn = Field(default_factory=BatchPolicyIn)
    external_research_node_ids: list[UUID] = Field(default_factory=list)


class BatchJobOut(BaseModel):
    batch_id: UUID
    space_id: UUID
    mentor_id: UUID
    status: BatchJobStatus
    policy: BatchPolicyIn
    selected_root_node_ids: list[UUID] = Field(default_factory=list)
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BatchStepOut(BaseModel):
    step_id: UUID
    batch_id: UUID
    position: int
    node_id: UUID
    node_title: str
    path_titles: list[str] = Field(default_factory=list)
    depth_level: int
    root_segment_node_id: UUID
    status: BatchStepStatus
    generation_run_id: UUID | None = None
    run_status: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BatchDetailOut(BaseModel):
    batch: BatchJobOut
    steps: list[BatchStepOut]


class BatchCreateResponse(BaseModel):
    batch_id: UUID
    status: BatchJobStatus = "pending"


class BatchCancelResponse(BaseModel):
    batch_id: UUID
    status: BatchJobStatus
