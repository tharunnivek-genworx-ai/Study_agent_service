"""Service layer for durable generation run checkpoints and resume."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.generation_run_exceptions import (
    GenerationPipelineResumeNotImplementedException,
    GenerationResumeTooEarlyException,
    GenerationRunConflictException,
    GenerationRunNotCancellableException,
    GenerationRunNotFoundException,
    GenerationRunNotResumableException,
)
from src.api.data.repositories.generation_run_repository import GenerationRunRepository
from src.api.schemas.generation_progress_schema import GenerationPipeline
from src.api.schemas.generation_run_schema import (
    MAX_RESUME_ATTEMPTS,
    GenerationRunCreate,
    GenerationRunOut,
    GenerationRunPipeline,
    GenerationRunResourceType,
    GenerationRunResumeResponse,
    GenerationRunResumeResult,
    GenerationRunStatus,
)
from src.api.utils.generation_progress.advisory_lock import require_generation_lock
from src.api.utils.generation_progress.db_store import (
    DbGenerationProgressStore,
    _node_to_step,
)


def _pipeline_enum(pipeline: GenerationRunPipeline) -> GenerationPipeline:
    return GenerationPipeline(pipeline.value)


class GenerationRunService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GenerationRunRepository(session)
        self.progress = DbGenerationProgressStore(session)

    async def start_run(
        self,
        payload: GenerationRunCreate,
        *,
        supersede_existing: bool = True,
    ) -> GenerationRunOut:
        if supersede_existing:
            await self.repo.supersede_stale_runs(
                resource_id=payload.resource_id,
                pipeline=payload.pipeline.value,
            )

        active = await self.repo.get_active_run(
            resource_id=payload.resource_id,
            pipeline=payload.pipeline.value,
        )
        if active is not None and active.status == GenerationRunStatus.RUNNING.value:
            raise GenerationRunConflictException(str(active.run_id))

        await require_generation_lock(
            self.session,
            pipeline=payload.pipeline.value,
            resource_id=payload.resource_id,
        )

        run = await self.repo.create(payload)
        await self.progress.start(run.run_id, _pipeline_enum(payload.pipeline))
        return GenerationRunOut.from_orm_run(run)

    async def checkpoint_after_node(
        self,
        run_id: UUID,
        *,
        node_name: str,
        state: dict[str, Any],
    ) -> None:
        run = await self.repo.get_by_id(run_id)
        if run is None or run.status != GenerationRunStatus.RUNNING.value:
            return

        pipeline = GenerationPipeline(run.pipeline)
        step_index = _node_to_step(pipeline, node_name)
        artifact_run_id = state.get("artifact_run_id")
        if isinstance(artifact_run_id, str):
            artifact_id: str | None = artifact_run_id
        else:
            artifact_id = run.artifact_run_id

        await self.repo.checkpoint_after_node(
            run_id,
            node_name=node_name,
            checkpoint_state=state,
            progress_step_index=step_index,
            artifact_run_id=artifact_id,
        )
        if step_index is not None:
            await self.progress.set_step(run_id, step_index)

    async def fail_run(
        self,
        run_id: UUID,
        *,
        error_message: str,
        error_type: str | None = None,
        next_llm_retry_at: datetime | None = None,
    ) -> None:
        await self.repo.fail_run(
            run_id,
            error_message=error_message,
            error_type=error_type,
            next_llm_retry_at=next_llm_retry_at,
        )

    async def complete_run(self, run_id: UUID) -> None:
        await self.progress.complete(run_id)

    async def get_run(self, run_id: UUID, *, mentor_id: UUID) -> GenerationRunOut:
        run = await self._get_run_for_mentor(run_id, mentor_id)
        return GenerationRunOut.from_orm_run(run)

    async def _get_run_for_mentor(self, run_id: UUID, mentor_id: UUID) -> Any:
        run = await self.repo.get_by_id(run_id)
        if run is None or run.mentor_id != mentor_id:
            raise GenerationRunNotFoundException()
        return run

    def _validate_resumable(self, run: Any, *, run_id: UUID) -> None:
        if run.status != GenerationRunStatus.FAILED.value:
            raise GenerationRunNotResumableException(
                "Only failed generation runs can be resumed."
            )

        if run.attempt_count >= MAX_RESUME_ATTEMPTS:
            raise GenerationRunNotResumableException(
                "Maximum resume attempts reached for this generation run."
            )

        now = datetime.now(UTC)
        if run.next_llm_retry_at is not None and now < run.next_llm_retry_at:
            raise GenerationResumeTooEarlyException(retry_after=run.next_llm_retry_at)

    async def _assert_no_resume_conflict(self, run: Any, *, run_id: UUID) -> None:
        active = await self.repo.get_active_run(
            resource_id=run.resource_id,
            pipeline=run.pipeline,
        )
        if (
            active is not None
            and active.run_id != run_id
            and active.status == GenerationRunStatus.RUNNING.value
        ):
            raise GenerationRunConflictException(str(active.run_id))

    async def resume_run(
        self,
        run_id: UUID,
        *,
        mentor_id: UUID,
    ) -> GenerationRunResumeResult:
        run = await self._get_run_for_mentor(run_id, mentor_id)
        self._validate_resumable(run, run_id=run_id)
        await self._assert_no_resume_conflict(run, run_id=run_id)

        await require_generation_lock(
            self.session,
            pipeline=run.pipeline,
            resource_id=run.resource_id,
        )

        # Extract all attributes before committing — each commit() expires ORM
        # objects in the session, and accessing expired attributes in an async
        # session raises a greenlet error (lazy load without I/O permission).
        checkpoint = run.checkpoint_state or {}
        request_params = run.request_params or {}
        run_pipeline = run.pipeline
        run_generation_mode = run.generation_mode
        last_completed_node = run.last_completed_node
        artifact_run_id = run.artifact_run_id

        await self.repo.increment_attempt_count(run_id)
        await self.repo.mark_running(run_id)

        return GenerationRunResumeResult(
            run_id=run_id,
            pipeline=run_pipeline,
            generation_mode=run_generation_mode,
            checkpoint_state=checkpoint,
            request_params=request_params,
            last_completed_node=last_completed_node,
            artifact_run_id=artifact_run_id,
        )

    async def execute_resume(
        self,
        run_id: UUID,
        *,
        mentor_id: UUID,
        role: str,
    ) -> GenerationRunResumeResponse:
        """Validate, mark running, and dispatch to the pipeline resume executor."""
        run = await self._get_run_for_mentor(run_id, mentor_id)
        self._validate_resumable(run, run_id=run_id)

        handler = _pipeline_resume_handler(run.pipeline)
        if handler is None:
            raise GenerationPipelineResumeNotImplementedException(run.pipeline)

        resume_result = await self.resume_run(run_id, mentor_id=mentor_id)
        # Pipeline handler (and graph_runner inside it) call fail_run with specific
        # diagnostics on any exception — no catch needed here.
        await handler(self.session, resume_result, mentor_id=mentor_id, role=role)

        return GenerationRunResumeResponse(
            run_id=run_id,
            progress_session_id=run_id,
            pipeline=resume_result.pipeline,
            status=GenerationRunStatus.RUNNING.value,
        )

    @staticmethod
    def resource_for_study_material(
        node_id: UUID,
    ) -> tuple[GenerationRunResourceType, UUID]:
        return GenerationRunResourceType.NODE, node_id

    @staticmethod
    def resource_for_quiz(quiz_id: UUID) -> tuple[GenerationRunResourceType, UUID]:
        return GenerationRunResourceType.QUIZ, quiz_id

    @staticmethod
    def resource_for_quiz_generation(
        node_id: UUID,
        *,
        quiz_id: UUID | None = None,
    ) -> tuple[GenerationRunResourceType, UUID]:
        """Scope generation runs to quiz_id when replacing a draft, else node_id."""
        if quiz_id is not None:
            return GenerationRunResourceType.QUIZ, quiz_id
        return GenerationRunResourceType.NODE, node_id

    @staticmethod
    def resource_for_hint(quiz_id: UUID) -> tuple[GenerationRunResourceType, UUID]:
        return GenerationRunResourceType.QUIZ, quiz_id

    async def cancel_run(self, run_id: UUID, *, mentor_id: UUID) -> GenerationRunOut:
        """Cancel a running or failed generation run."""
        run = await self._get_run_for_mentor(run_id, mentor_id)
        if run.status not in (
            GenerationRunStatus.RUNNING.value,
            GenerationRunStatus.FAILED.value,
        ):
            raise GenerationRunNotCancellableException(
                f"Generation run cannot be cancelled while status is '{run.status}'."
            )

        cancelled = await self.repo.cancel_run(run_id)
        if not cancelled:
            raise GenerationRunNotCancellableException()

        updated = await self.repo.get_by_id(run_id)
        if updated is None:
            raise GenerationRunNotFoundException()
        return GenerationRunOut.from_orm_run(updated)


PipelineResumeHandler = Any


def _pipeline_resume_handler(pipeline: str) -> PipelineResumeHandler | None:
    """Return the async resume executor for a pipeline, if wired."""
    if pipeline == GenerationRunPipeline.STUDY_MATERIAL.value:
        from src.api.core.services.study_agent_services.study_material_resume import (
            execute_resume,
        )

        return execute_resume
    if pipeline == GenerationRunPipeline.QUIZ.value:
        from src.api.core.services.quiz_services.quiz_resume import execute_resume

        return execute_resume
    if pipeline == GenerationRunPipeline.HINT.value:
        from src.api.core.services.quiz_services.hint_resume import execute_resume

        return execute_resume
    return None
