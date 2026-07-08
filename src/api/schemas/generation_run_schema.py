"""Schemas for durable generation run checkpoints and resume."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.api.schemas.common import (
    GenerationRunMode,
    GenerationRunPipeline,
    GenerationRunStatus,
)

# Re-exported for callers that import from this module.
__all__ = [
    "ACTIVE_RUN_STATUSES",
    "GenerationJobStartResponse",
    "GenerationRunActiveOut",
    "GenerationRunCancelResponse",
    "GenerationRunCreate",
    "GenerationRunMode",
    "GenerationRunOut",
    "GenerationRunPipeline",
    "GenerationRunResourceType",
    "GenerationRunResultOut",
    "GenerationRunResumeResponse",
    "GenerationRunResumeResult",
    "GenerationRunStatus",
    "MAX_RESUME_ATTEMPTS",
    "RESUMABLE_RUN_STATUSES",
]


class GenerationRunResourceType(StrEnum):
    NODE = "node"
    QUIZ = "quiz"


ACTIVE_RUN_STATUSES = frozenset(
    {GenerationRunStatus.RUNNING, GenerationRunStatus.FAILED}
)
RESUMABLE_RUN_STATUSES = frozenset({GenerationRunStatus.FAILED})
MAX_RESUME_ATTEMPTS = 5


class GenerationRunCreate(BaseModel):
    pipeline: GenerationRunPipeline
    resource_type: GenerationRunResourceType
    resource_id: UUID
    node_id: UUID
    space_id: UUID
    mentor_id: UUID
    generation_mode: GenerationRunMode
    request_params: dict[str, Any] = Field(default_factory=dict)
    artifact_run_id: str | None = None
    run_id: UUID | None = None


class GenerationRunOut(BaseModel):
    run_id: UUID
    pipeline: str
    resource_type: str
    resource_id: UUID
    node_id: UUID
    space_id: UUID
    mentor_id: UUID
    status: str
    last_completed_node: str | None = None
    generation_mode: str
    artifact_run_id: str | None = None
    progress_step_index: int = 0
    error_message: str | None = None
    error_type: str | None = None
    next_llm_retry_at: datetime | None = None
    attempt_count: int = 0
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    resumable: bool = False
    seconds_until_retry: int | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_run(cls, run: Any) -> GenerationRunOut:
        now = datetime.now(UTC)
        cooldown_active = (
            run.next_llm_retry_at is not None and now < run.next_llm_retry_at
        )
        resumable = (
            run.status == GenerationRunStatus.FAILED.value
            and run.attempt_count < MAX_RESUME_ATTEMPTS
            and not cooldown_active
        )
        seconds_until_retry: int | None = None
        if cooldown_active and run.next_llm_retry_at is not None:
            seconds_until_retry = max(
                0, int((run.next_llm_retry_at - now).total_seconds())
            )
        return cls(
            run_id=run.run_id,
            pipeline=run.pipeline,
            resource_type=run.resource_type,
            resource_id=run.resource_id,
            node_id=run.node_id,
            space_id=run.space_id,
            mentor_id=run.mentor_id,
            status=run.status,
            last_completed_node=run.last_completed_node,
            generation_mode=run.generation_mode,
            artifact_run_id=run.artifact_run_id,
            progress_step_index=run.progress_step_index,
            error_message=run.error_message,
            error_type=run.error_type,
            next_llm_retry_at=run.next_llm_retry_at,
            attempt_count=run.attempt_count,
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
            resumable=resumable,
            seconds_until_retry=seconds_until_retry,
        )


class GenerationRunResumeResponse(BaseModel):
    """Response after a successful resume request starts pipeline execution."""

    run_id: UUID
    progress_session_id: UUID = Field(
        description=(
            "Deprecated alias for run_id. Poll GET /generation-progress/{run_id}."
        ),
    )
    pipeline: str
    status: str = GenerationRunStatus.RUNNING.value


class GenerationRunCancelResponse(BaseModel):
    """Response after cancelling a generation run."""

    run_id: UUID
    status: str = GenerationRunStatus.CANCELLED.value


class GenerationRunResumeResult(BaseModel):
    run_id: UUID
    pipeline: str
    generation_mode: str
    checkpoint_state: dict[str, Any]
    request_params: dict[str, Any]
    last_completed_node: str | None = None
    artifact_run_id: str | None = None


class GenerationJobStartResponse(BaseModel):
    """Returned immediately when a generation job is accepted (HTTP 202)."""

    run_id: UUID
    pipeline: str
    status: Literal["running"] = "running"


class GenerationRunActiveOut(BaseModel):
    """Active generation run for a resource, if any."""

    run_id: UUID
    pipeline: str
    status: str
    step_profile: str | None = None
    generation_mode: str | None = None


class GenerationRunResultOut(BaseModel):
    """Materialized result of a completed or failed generation run."""

    run_id: UUID
    pipeline: str
    status: str
    error_message: str | None = None
    study_material_generate: dict[str, Any] | None = None
    study_material_feedback: dict[str, Any] | None = None
    quiz: dict[str, Any] | None = None
