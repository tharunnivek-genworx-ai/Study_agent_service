"""DB-backed generation progress using the generationruns table."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.repositories.generation_run_repository import GenerationRunRepository
from src.api.schemas.generation_progress_schema import (
    GenerationJobStatus,
    GenerationPipeline,
    GenerationProgressOut,
    GenerationProgressRecord,
    GenerationProgressStep,
    GenerationProgressStepDef,
    GenerationStepStatus,
)
from src.api.schemas.generation_run_schema import GenerationRunStatus
from src.api.utils.generation_progress.store import (
    HINT_NODE_TO_STEP,
    HINT_STEP_DEFS,
    QUIZ_CONTEXT_LOAD_NODES,
    QUIZ_NODE_TO_STEP,
    QUIZ_STEP_DEFS,
    STUDY_MATERIAL_NODE_TO_STEP,
    STUDY_MATERIAL_STEP_DEFS,
)


def _step_defs(pipeline: GenerationPipeline) -> list[GenerationProgressStepDef]:
    if pipeline == GenerationPipeline.QUIZ:
        return QUIZ_STEP_DEFS
    if pipeline == GenerationPipeline.HINT:
        return HINT_STEP_DEFS
    return STUDY_MATERIAL_STEP_DEFS


def _node_to_step(pipeline: GenerationPipeline, node_name: str) -> int | None:
    if pipeline == GenerationPipeline.QUIZ:
        if node_name in QUIZ_CONTEXT_LOAD_NODES:
            return 1
        return QUIZ_NODE_TO_STEP.get(node_name)
    if pipeline == GenerationPipeline.HINT:
        return HINT_NODE_TO_STEP.get(node_name)
    return STUDY_MATERIAL_NODE_TO_STEP.get(node_name)


def _build_steps(
    pipeline: GenerationPipeline, active_index: int
) -> list[GenerationProgressStep]:
    rendered: list[GenerationProgressStep] = []
    for index, step in enumerate(_step_defs(pipeline)):
        if index < active_index:
            status = GenerationStepStatus.COMPLETED
        elif index == active_index:
            status = GenerationStepStatus.ACTIVE
        else:
            status = GenerationStepStatus.PENDING
        rendered.append(
            GenerationProgressStep(
                id=step.id,
                label=step.label,
                status=status,
            )
        )
    return rendered


def _status_from_run(run_status: str) -> GenerationJobStatus:
    if run_status == GenerationRunStatus.COMPLETED.value:
        return GenerationJobStatus.COMPLETED
    if run_status == GenerationRunStatus.FAILED.value:
        return GenerationJobStatus.FAILED
    return GenerationJobStatus.RUNNING


class DbGenerationProgressStore:
    """Async progress store backed by generationruns.progressstepindex."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = GenerationRunRepository(session)

    async def start(
        self,
        run_id: UUID,
        pipeline: GenerationPipeline,
    ) -> None:
        await self._repo.update_progress(
            run_id,
            progress_step_index=0,
        )

    async def set_step(self, run_id: UUID, step_index: int) -> None:
        await self._repo.update_progress(
            run_id,
            progress_step_index=step_index,
        )

    async def on_node(
        self,
        run_id: UUID,
        pipeline: GenerationPipeline,
        node_name: str,
    ) -> None:
        step_index = _node_to_step(pipeline, node_name)
        if step_index is not None:
            await self.set_step(run_id, step_index)

    async def complete(self, run_id: UUID) -> None:
        run = await self._repo.get_by_id(run_id)
        if run is None:
            return
        pipeline = GenerationPipeline(run.pipeline)
        final_index = len(_step_defs(pipeline)) - 1
        await self._repo.update_progress(run_id, progress_step_index=final_index)
        await self._repo.complete_run(run_id)

    async def fail(self, run_id: UUID, error: str) -> None:
        await self._repo.fail_run(run_id, error_message=error)

    async def get_record(self, run_id: UUID) -> GenerationProgressRecord | None:
        run = await self._repo.get_by_id(run_id)
        if run is None:
            return None

        pipeline = GenerationPipeline(run.pipeline)
        job_status = _status_from_run(run.status)
        active_index = run.progress_step_index
        if job_status == GenerationJobStatus.COMPLETED:
            active_index = len(_step_defs(pipeline)) - 1

        return GenerationProgressRecord(
            session_id=str(run.run_id),
            pipeline=pipeline,
            status=job_status,
            current_step_index=active_index,
            steps=_build_steps(pipeline, active_index),
            error=run.error_message,
            started_at=run.created_at.timestamp(),
            updated_at=run.updated_at.timestamp(),
        )

    async def to_progress_out(self, run_id: UUID) -> GenerationProgressOut | None:
        record = await self.get_record(run_id)
        if record is None:
            return None
        return record.to_progress_out()
