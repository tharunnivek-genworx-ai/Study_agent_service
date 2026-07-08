"""DB-backed generation progress using the generationruns table."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.repositories import GenerationRunRepository
from src.api.schemas import (
    GenerationJobStatus,
    GenerationPipeline,
    GenerationProgressOut,
    GenerationProgressRecord,
    GenerationRunStatus,
)
from src.api.utils.generation_progress.store import (
    build_steps_for_profile,
    node_to_step_for_profile,
    step_defs_for_profile,
    step_profile_from_request_params,
)


def _status_from_run(run_status: str) -> GenerationJobStatus:
    if run_status == GenerationRunStatus.COMPLETED.value:
        return GenerationJobStatus.COMPLETED
    if run_status in (
        GenerationRunStatus.FAILED.value,
        GenerationRunStatus.CANCELLED.value,
        GenerationRunStatus.SUPERSEDED.value,
    ):
        return GenerationJobStatus.FAILED
    return GenerationJobStatus.RUNNING


class DbGenerationProgressStore:
    """Async progress store backed by generationruns.progressstepindex."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = GenerationRunRepository(session)
        self._session = session

    async def start(
        self,
        run_id: UUID,
        pipeline: GenerationPipeline,
    ) -> None:
        await self._repo.update_progress(
            run_id,
            progress_step_index=0,
        )
        await self._session.commit()

    async def set_step(self, run_id: UUID, step_index: int) -> None:
        await self._repo.update_progress(
            run_id,
            progress_step_index=step_index,
        )
        await self._session.commit()

    async def on_node(
        self,
        run_id: UUID,
        pipeline: GenerationPipeline,
        node_name: str,
        *,
        step_profile: str | None = None,
    ) -> None:
        run = await self._repo.get_by_id(run_id)
        if run is None or run.status != GenerationRunStatus.RUNNING.value:
            return
        profile = step_profile_from_request_params(
            run.request_params,
            pipeline=GenerationPipeline(run.pipeline),
        )
        if step_profile is not None:
            from src.api.utils.generation_progress.store import GenerationStepProfile

            try:
                profile = GenerationStepProfile(step_profile)
            except ValueError:
                pass
        step_index = node_to_step_for_profile(profile, node_name)
        if step_index is not None:
            await self.set_step(run_id, step_index)

    async def complete(self, run_id: UUID) -> None:
        run = await self._repo.get_by_id(run_id)
        if run is None:
            return
        pipeline = GenerationPipeline(run.pipeline)
        profile = step_profile_from_request_params(
            run.request_params, pipeline=pipeline
        )
        final_index = len(step_defs_for_profile(profile)) - 1
        await self._repo.update_progress(run_id, progress_step_index=final_index)
        await self._repo.complete_run(run_id)

    async def fail(self, run_id: UUID, error: str) -> None:
        await self._repo.fail_run(run_id, error_message=error)

    async def get_record(self, run_id: UUID) -> GenerationProgressRecord | None:
        run = await self._repo.get_by_id(run_id)
        if run is None:
            return None

        pipeline = GenerationPipeline(run.pipeline)
        profile = step_profile_from_request_params(
            run.request_params, pipeline=pipeline
        )
        job_status = _status_from_run(run.status)
        active_index = run.progress_step_index
        if job_status == GenerationJobStatus.COMPLETED:
            active_index = len(step_defs_for_profile(profile)) - 1

        return GenerationProgressRecord(
            session_id=str(run.run_id),
            pipeline=pipeline,
            status=job_status,
            current_step_index=active_index,
            steps=build_steps_for_profile(profile, active_index),
            error=run.error_message,
            started_at=run.created_at.timestamp(),
            updated_at=run.updated_at.timestamp(),
        )

    async def to_progress_out(self, run_id: UUID) -> GenerationProgressOut | None:
        record = await self.get_record(run_id)
        if record is None:
            return None
        return record.to_progress_out()
