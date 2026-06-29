"""Schemas for durable generation run checkpoints and resume."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class GenerationRunPipeline(StrEnum):
    STUDY_MATERIAL = "study_material"
    QUIZ = "quiz"
    HINT = "hint"


class GenerationRunResourceType(StrEnum):
    NODE = "node"
    QUIZ = "quiz"


class GenerationRunStatus(StrEnum):
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class GenerationRunMode(StrEnum):
    GENERATE = "generate"
    REGENERATE = "regenerate"
    IMPROVE = "improve"


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
    progress_session_id: UUID
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
