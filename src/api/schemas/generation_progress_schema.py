"""Schemas for generation progress tracking and polling."""

from __future__ import annotations

import time
from enum import StrEnum

from pydantic import BaseModel, Field

from src.api.schemas.common import (
    GenerationJobStatus,
    GenerationPipeline,
)


class GenerationStepStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"


class GenerationProgressStepDef(BaseModel):
    id: str
    label: str


class GenerationProgressStep(BaseModel):
    id: str
    label: str
    status: GenerationStepStatus


class GenerationProgressStepOut(BaseModel):
    id: str
    label: str
    status: str = Field(description="pending | active | completed")


class GenerationProgressOut(BaseModel):
    session_id: str
    pipeline: str = Field(description="study_material | quiz | hint")
    status: str = Field(description="running | completed | failed")
    current_step_index: int
    steps: list[GenerationProgressStepOut]
    error: str | None = None


class GenerationProgressRecord(BaseModel):
    session_id: str
    pipeline: GenerationPipeline
    status: GenerationJobStatus = GenerationJobStatus.RUNNING
    current_step_index: int = 0
    steps: list[GenerationProgressStep] = Field(default_factory=list)
    error: str | None = None
    started_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def to_progress_out(self) -> GenerationProgressOut:
        return GenerationProgressOut(
            session_id=self.session_id,
            pipeline=self.pipeline.value,
            status=self.status.value,
            current_step_index=self.current_step_index,
            steps=[
                GenerationProgressStepOut(
                    id=step.id,
                    label=step.label,
                    status=step.status.value,
                )
                for step in self.steps
            ],
            error=self.error,
        )
