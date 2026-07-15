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
    "GenerationRunActionsOut",
    "GenerationRunActiveOut",
    "GenerationRunCreate",
    "GenerationRunMode",
    "GenerationRunOut",
    "GenerationRunPauseContextOut",
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
    {
        GenerationRunStatus.RUNNING,
        GenerationRunStatus.PAUSED,
        GenerationRunStatus.FAILED,
    }
)
RESUMABLE_RUN_STATUSES = frozenset(
    {GenerationRunStatus.PAUSED, GenerationRunStatus.FAILED}
)
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


class GenerationRunPauseContextOut(BaseModel):
    headline: str
    interrupted_step_label: str | None = None
    last_completed_node: str | None = None


class GenerationRunActionsOut(BaseModel):
    can_pause: bool = False
    can_resume: bool = False
    can_abandon: bool = False
    pause_context: GenerationRunPauseContextOut | None = None


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
    paused_at: datetime | None = None
    abandoned_at: datetime | None = None
    pause_reason: str | None = None
    abandon_reason: str | None = None
    resumable: bool = False
    seconds_until_retry: int | None = None
    fingerprint_mismatch: bool = False
    actions: GenerationRunActionsOut | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_run(
        cls,
        run: Any,
        *,
        actions: GenerationRunActionsOut | None = None,
        fingerprint_mismatch: bool = False,
    ) -> GenerationRunOut:
        from src.api.utils.generation_progress.request_fingerprint import (
            fingerprints_match,
        )

        now = datetime.now(UTC)
        cooldown_active = (
            run.next_llm_retry_at is not None and now < run.next_llm_retry_at
        )
        is_paused = run.status == GenerationRunStatus.PAUSED.value
        is_failed = run.status == GenerationRunStatus.FAILED.value
        inputs_match = fingerprints_match(
            getattr(run, "request_fingerprint", None),
            pipeline=run.pipeline,
            node_id=run.node_id,
            generation_mode=run.generation_mode,
            request_params=getattr(run, "request_params", None),
        )
        resumable = (
            run.status in {s.value for s in RESUMABLE_RUN_STATUSES}
            and run.attempt_count < MAX_RESUME_ATTEMPTS
            and (is_paused or not cooldown_active)
            and inputs_match
            and not fingerprint_mismatch
        )
        seconds_until_retry: int | None = None
        if is_failed and cooldown_active and run.next_llm_retry_at is not None:
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
            paused_at=getattr(run, "paused_at", None),
            abandoned_at=getattr(run, "abandoned_at", None),
            pause_reason=getattr(run, "pause_reason", None),
            abandon_reason=getattr(run, "abandon_reason", None),
            resumable=resumable,
            seconds_until_retry=seconds_until_retry,
            fingerprint_mismatch=not inputs_match or fingerprint_mismatch,
            actions=actions,
        )


class GenerationRunResumeResponse(BaseModel):
    """Response after a successful resume request starts pipeline execution."""

    run_id: UUID
    pipeline: str
    status: str = GenerationRunStatus.RUNNING.value


class GenerationRunResumeResult(BaseModel):
    run_id: UUID
    pipeline: str
    generation_mode: str
    checkpoint_state: dict[str, Any]
    request_params: dict[str, Any]
    last_completed_node: str | None = None
    artifact_run_id: str | None = None
    execution_token: UUID | None = None


class GenerationJobStartResponse(BaseModel):
    """Returned immediately when a generation job is accepted (HTTP 202)."""

    run_id: UUID
    pipeline: str
    status: Literal["running"] = "running"


class GenerationRunActiveOut(BaseModel):
    """Active or resumable generation run for a resource, if any."""

    run_id: UUID
    pipeline: str
    status: str
    step_profile: str | None = None
    generation_mode: str | None = None
    resumable: bool = False
    seconds_until_retry: int | None = None


class GenerationRunResultOut(BaseModel):
    """Materialized result of a completed or failed generation run."""

    run_id: UUID
    pipeline: str
    status: str
    error_message: str | None = None
    study_material_generate: dict[str, Any] | None = None
    study_material_feedback: dict[str, Any] | None = None
    quiz: dict[str, Any] | None = None
