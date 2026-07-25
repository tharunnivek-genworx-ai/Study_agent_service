"""Service layer for durable generation run checkpoints and resume."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config.dbconfig import settings
from src.api.core.exceptions import (
    GenerationPipelineResumeNotImplementedException,
    GenerationResumeTooEarlyException,
    GenerationRunConflictException,
    GenerationRunInputsChangedException,
    GenerationRunNotAbandonableException,
    GenerationRunNotFoundException,
    GenerationRunNotPausableException,
    GenerationRunNotResumableException,
)
from src.api.data.repositories import GenerationRunRepository
from src.api.schemas import (
    MAX_RESUME_ATTEMPTS,
    RESUMABLE_RUN_STATUSES,
    GenerationRunActionsOut,
    GenerationRunActiveOut,
    GenerationRunCreate,
    GenerationRunOut,
    GenerationRunPauseContextOut,
    GenerationRunPipeline,
    GenerationRunResourceType,
    GenerationRunResultOut,
    GenerationRunResumeResult,
    GenerationRunStatus,
)
from src.api.schemas.common import GenerationPipeline
from src.api.utils.generation_progress.advisory_lock import (
    release_generation_lock,
    require_generation_coordinator_lock,
    try_acquire_generation_lock,
)
from src.api.utils.generation_progress.db_store import DbGenerationProgressStore
from src.api.utils.generation_progress.request_fingerprint import (
    compute_request_fingerprint,
    fingerprints_match,
)
from src.api.utils.generation_progress.store import (
    node_to_step_for_profile,
    step_defs_for_profile,
    step_profile_from_request_params,
)
from src.api.utils.qc_response_projection import project_generation_run_result_payload

logger = logging.getLogger(__name__)

# With a single durable worker, the previous task has exited before its
# replacement starts. Retries only cover brief connection/dispatch overlap;
# a long wait would hide a leaked lock behind an indefinite "Starting…" UI.
_LOCK_ACQUIRE_MAX_ATTEMPTS = 25
_LOCK_ACQUIRE_BASE_DELAY_SECONDS = 0.08

_ABANDONABLE_STATUSES = frozenset(
    {
        GenerationRunStatus.RUNNING.value,
        GenerationRunStatus.PAUSED.value,
        GenerationRunStatus.FAILED.value,
    }
)


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
        await require_generation_coordinator_lock(
            self.session,
            pipeline=payload.pipeline.value,
            resource_id=payload.resource_id,
        )

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

        execution_token = uuid4()
        request_fingerprint = compute_request_fingerprint(payload)

        run = await self.repo.create(
            payload,
            execution_token=execution_token,
            request_fingerprint=request_fingerprint,
        )
        # Materialize the response before progress.start commits. This remains safe
        # if a caller supplies an AsyncSession with expire_on_commit=True.
        run_out = self._run_out(run)
        await self.progress.start(run.run_id, payload.pipeline)
        await self.session.commit()
        return run_out

    async def is_run_active(self, run_id: UUID) -> bool:
        # Live read (bypasses the identity map) so a pause committed by the API session
        # is observed by the worker despite expire_on_commit=False.
        live = await self.repo.get_live_status_and_token(run_id)
        return live is not None and live[0] == GenerationRunStatus.RUNNING.value

    async def should_continue_execution(
        self,
        run_id: UUID,
        job_token: UUID,
    ) -> bool:
        """Token-aware check for background jobs (LlamaParse poll loops, graph).

        Reads the live status/token directly from the DB (not the identity-mapped
        instance): with expire_on_commit=False the worker session would otherwise keep
        seeing the stale RUNNING status it loaded when the graph started and never
        observe a cooperative pause, so the graph would run to completion.
        """
        live = await self.repo.get_live_status_and_token(run_id)
        if live is None:
            return False
        status, execution_token = live
        if status != GenerationRunStatus.RUNNING.value:
            return False
        if execution_token is None:
            return False
        return bool(execution_token == job_token)

    async def store_llamaparse_job_ids(
        self,
        run_id: UUID,
        *,
        extract_id: str | None = None,
        parse_id: str | None = None,
    ) -> None:
        """Persist LlamaCloud job IDs on the run row for audit (no remote delete)."""
        await self.repo.store_llamaparse_job_ids(
            run_id,
            extract_id=extract_id,
            parse_id=parse_id,
        )

    async def acquire_lock_for_run(self, run_id: UUID) -> Any | None:
        """Acquire the advisory lock for an existing run (background job entry)."""
        run = await self.repo.get_by_id(run_id)
        if run is None:
            return None
        if run.status != GenerationRunStatus.RUNNING.value:
            return None

        for attempt in range(_LOCK_ACQUIRE_MAX_ATTEMPTS):
            acquired = await try_acquire_generation_lock(
                self.session,
                pipeline=run.pipeline,
                resource_id=run.resource_id,
            )
            if acquired:
                if attempt > 0:
                    logger.info(
                        "Generation lock acquired after retry",
                        extra={
                            "run_id": str(run_id),
                            "resource_id": str(run.resource_id),
                            "attempt": attempt + 1,
                        },
                    )
                return run

            if attempt < _LOCK_ACQUIRE_MAX_ATTEMPTS - 1:
                run = await self.repo.get_by_id(run_id)
                if run is None or run.status != GenerationRunStatus.RUNNING.value:
                    return None
                await asyncio.sleep(_LOCK_ACQUIRE_BASE_DELAY_SECONDS * (attempt + 1))

        await self.fail_run(
            run_id,
            error_message="Could not acquire generation lock for this resource.",
            error_type="lock_unavailable",
        )
        logger.warning(
            "Generation lock unavailable after retries",
            extra={
                "run_id": str(run_id),
                "resource_id": str(run.resource_id),
                "attempts": _LOCK_ACQUIRE_MAX_ATTEMPTS,
            },
        )
        return None

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
        profile = step_profile_from_request_params(
            run.request_params, pipeline=pipeline
        )
        step_index = node_to_step_for_profile(profile, node_name)
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

    async def fail_run(
        self,
        run_id: UUID,
        *,
        error_message: str,
        error_type: str | None = None,
        next_llm_retry_at: datetime | None = None,
    ) -> None:
        run = await self.repo.get_by_id(run_id)
        lock_identity = (run.pipeline, run.resource_id) if run is not None else None
        execution_token = run.execution_token if run is not None else None
        await self.repo.fail_run(
            run_id,
            error_message=error_message,
            error_type=error_type,
            next_llm_retry_at=next_llm_retry_at,
            expected_execution_token=execution_token,
        )
        if lock_identity is not None:
            await release_generation_lock(
                self.session,
                pipeline=lock_identity[0],
                resource_id=lock_identity[1],
            )

    async def complete_run(self, run_id: UUID) -> None:
        run = await self.repo.get_by_id(run_id)
        lock_identity = (run.pipeline, run.resource_id) if run is not None else None
        await self.progress.complete(run_id)
        if lock_identity is not None:
            await release_generation_lock(
                self.session,
                pipeline=lock_identity[0],
                resource_id=lock_identity[1],
            )

    def _run_out(self, run: Any) -> GenerationRunOut:
        return GenerationRunOut.from_orm_run(
            run,
            actions=self.build_run_actions(run),
        )

    async def get_run(self, run_id: UUID, *, mentor_id: UUID) -> GenerationRunOut:
        run = await self._get_run_for_mentor(run_id, mentor_id)
        return self._run_out(run)

    async def get_active_run_for_resource(
        self,
        *,
        resource_id: UUID,
        pipeline: str,
        mentor_id: UUID,
    ) -> GenerationRunActiveOut | None:
        run = await self.repo.get_active_run(
            resource_id=resource_id,
            pipeline=pipeline,
        )
        if run is None or run.mentor_id != mentor_id:
            return None
        params: dict[str, Any] = run.request_params or {}
        run_out = self._run_out(run)
        if run.status == GenerationRunStatus.RUNNING.value:
            return GenerationRunActiveOut(
                run_id=run.run_id,
                pipeline=run.pipeline,
                status=run.status,
                step_profile=params.get("step_profile"),
                generation_mode=run.generation_mode,
                resumable=False,
                seconds_until_retry=None,
            )
        if (
            run.status in {s.value for s in RESUMABLE_RUN_STATUSES}
            and run_out.resumable
        ):
            return GenerationRunActiveOut(
                run_id=run.run_id,
                pipeline=run.pipeline,
                status=run.status,
                step_profile=params.get("step_profile"),
                generation_mode=run.generation_mode,
                resumable=True,
                seconds_until_retry=run_out.seconds_until_retry,
            )
        return None

    async def store_run_result(
        self,
        run_id: UUID,
        result_payload: dict[str, Any],
    ) -> None:
        run = await self.repo.get_by_id(run_id)
        if run is None:
            return
        params = dict(run.request_params or {})
        params["result"] = result_payload
        await self.repo.update_request_params(run_id, params)

    async def get_run_result(
        self,
        run_id: UUID,
        *,
        mentor_id: UUID,
    ) -> GenerationRunResultOut:
        run = await self._get_run_for_mentor(run_id, mentor_id)
        params = run.request_params or {}
        stored = project_generation_run_result_payload(params.get("result") or {})
        return GenerationRunResultOut(
            run_id=run.run_id,
            pipeline=run.pipeline,
            status=run.status,
            error_message=run.error_message,
            study_material_generate=stored.get("study_material_generate"),
            study_material_feedback=stored.get("study_material_feedback"),
            quiz=stored.get("quiz"),
        )

    async def _get_run_for_mentor(self, run_id: UUID, mentor_id: UUID) -> Any:
        run = await self.repo.get_by_id(run_id)
        if run is None or run.mentor_id != mentor_id:
            raise GenerationRunNotFoundException()
        return run

    def build_run_actions(self, run: Any) -> GenerationRunActionsOut:
        run_out = GenerationRunOut.from_orm_run(run)
        status = run.status
        can_pause = status == GenerationRunStatus.RUNNING.value
        can_resume = run_out.resumable
        can_abandon = status in _ABANDONABLE_STATUSES

        pause_context: GenerationRunPauseContextOut | None = None
        if status == GenerationRunStatus.PAUSED.value:
            pause_context = self._build_pause_context(run)

        return GenerationRunActionsOut(
            can_pause=can_pause,
            can_resume=can_resume,
            can_abandon=can_abandon,
            pause_context=pause_context,
        )

    @staticmethod
    def _build_pause_context(run: Any) -> GenerationRunPauseContextOut:
        params = run.request_params or {}
        pipeline = GenerationPipeline(run.pipeline)
        profile = step_profile_from_request_params(params, pipeline=pipeline)
        step_index = int(run.progress_step_index or 0)
        step_defs = step_defs_for_profile(profile)
        interrupted_label: str | None = None
        if 0 <= step_index < len(step_defs):
            interrupted_label = step_defs[step_index].label

        return GenerationRunPauseContextOut(
            headline="Generation paused",
            interrupted_step_label=interrupted_label,
            last_completed_node=run.last_completed_node,
        )

    def _validate_fingerprint(self, run: Any) -> None:
        if not fingerprints_match(
            getattr(run, "request_fingerprint", None),
            pipeline=run.pipeline,
            node_id=run.node_id,
            generation_mode=run.generation_mode,
            request_params=run.request_params,
        ):
            raise GenerationRunInputsChangedException()

    def _validate_resumable(self, run: Any, *, run_id: UUID) -> None:
        if run.status not in {s.value for s in RESUMABLE_RUN_STATUSES}:
            raise GenerationRunNotResumableException(
                "Only paused or failed generation runs can be resumed."
            )

        self._validate_fingerprint(run)

        if run.attempt_count >= MAX_RESUME_ATTEMPTS:
            raise GenerationRunNotResumableException(
                "Maximum resume attempts reached for this generation run."
            )

        if run.status == GenerationRunStatus.FAILED.value:
            now = datetime.now(UTC)
            if run.next_llm_retry_at is not None and now < run.next_llm_retry_at:
                raise GenerationResumeTooEarlyException(
                    retry_after=run.next_llm_retry_at
                )

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

    async def _sync_resume_progress_position(
        self,
        *,
        run_id: UUID,
        pipeline: str,
        checkpoint_state: dict[str, Any],
        request_params: dict[str, Any],
        last_completed_node: str | None,
    ) -> None:
        """Project the next resume entry node onto the visible progress step.

        Without this, a resumed run can keep showing the checkpoint's previous
        active step until the next node finishes and writes a fresh checkpoint.
        That is especially visible for quiz and hint flows, whose nodes do not
        all emit explicit node-enter progress updates.
        """
        try:
            next_node: str | None = None
            pipeline_enum = GenerationPipeline(pipeline)

            if pipeline == GenerationRunPipeline.STUDY_MATERIAL.value:
                from src.api.control.study_agent.graph.resume_router import (
                    hydrate_checkpoint_state,
                    resolve_resume_next_node,
                )

                state = hydrate_checkpoint_state(
                    checkpoint_state,
                    last_completed_node=last_completed_node,
                    request_params=request_params,
                )
                next_node = resolve_resume_next_node(
                    state,
                    last_completed_node=last_completed_node,
                )
            elif pipeline == GenerationRunPipeline.QUIZ.value:
                from src.api.control.quiz_agent.graph.quiz_graph.resume_router import (
                    hydrate_checkpoint_state,
                    resolve_resume_next_node,
                )

                state = hydrate_checkpoint_state(
                    checkpoint_state,
                    last_completed_node=last_completed_node,
                    request_params=request_params,
                )
                next_node = resolve_resume_next_node(
                    state,
                    last_completed_node=last_completed_node,
                )
            elif pipeline == GenerationRunPipeline.HINT.value:
                from src.api.control.hint_agent.graph.resume_router import (
                    hydrate_checkpoint_state,
                    resolve_resume_next_node,
                )

                state = hydrate_checkpoint_state(
                    checkpoint_state,
                    last_completed_node=last_completed_node,
                    request_params=request_params,
                )
                next_node = resolve_resume_next_node(
                    state,
                    last_completed_node=last_completed_node,
                )

            if not next_node or next_node == "__end__":
                return

            profile = step_profile_from_request_params(
                request_params,
                pipeline=pipeline_enum,
            )
            step_index = node_to_step_for_profile(profile, next_node)
            if step_index is None:
                return

            await self.progress.set_step(run_id, step_index)
        except Exception:
            logger.exception(
                "Failed to sync visible resume progress position",
                extra={"run_id": str(run_id), "pipeline": pipeline},
            )

    async def resume_run(
        self,
        run_id: UUID,
        *,
        mentor_id: UUID,
    ) -> GenerationRunResumeResult:
        run = await self._get_run_for_mentor(run_id, mentor_id)
        self._validate_resumable(run, run_id=run_id)
        await self._assert_no_resume_conflict(run, run_id=run_id)

        await require_generation_coordinator_lock(
            self.session,
            pipeline=run.pipeline,
            resource_id=run.resource_id,
        )

        execution_token = uuid4()

        # Snapshot ORM attrs before writes that may commit — callers resume from
        # these values rather than re-reading the run row after mark_running.
        checkpoint = run.checkpoint_state or {}
        request_params = run.request_params or {}
        run_pipeline = run.pipeline
        run_generation_mode = run.generation_mode
        last_completed_node = run.last_completed_node
        artifact_run_id = run.artifact_run_id

        await self.repo.increment_attempt_count(run_id)
        await self.repo.mark_running(run_id, execution_token=execution_token)
        await self._sync_resume_progress_position(
            run_id=run_id,
            pipeline=run_pipeline,
            checkpoint_state=checkpoint,
            request_params=request_params,
            last_completed_node=last_completed_node,
        )

        return GenerationRunResumeResult(
            run_id=run_id,
            pipeline=run_pipeline,
            generation_mode=run_generation_mode,
            checkpoint_state=checkpoint,
            request_params=request_params,
            last_completed_node=last_completed_node,
            artifact_run_id=artifact_run_id,
            execution_token=execution_token,
        )

    async def begin_resume(
        self,
        run_id: UUID,
        *,
        mentor_id: UUID,
    ) -> GenerationRunResumeResult:
        """Validate and mark a paused or failed run as running; returns resume payload."""
        run = await self._get_run_for_mentor(run_id, mentor_id)
        self._validate_resumable(run, run_id=run_id)

        handler = _pipeline_resume_handler(run.pipeline)
        if handler is None:
            raise GenerationPipelineResumeNotImplementedException(run.pipeline)

        return await self.resume_run(run_id, mentor_id=mentor_id)

    async def run_resume_pipeline(
        self,
        resume_result: GenerationRunResumeResult,
        *,
        mentor_id: UUID,
        role: str,
    ) -> None:
        """Execute the pipeline resume handler (background job body)."""
        handler = _pipeline_resume_handler(resume_result.pipeline)
        if handler is None:
            raise GenerationPipelineResumeNotImplementedException(
                resume_result.pipeline
            )
        await handler(self.session, resume_result, mentor_id=mentor_id, role=role)

    async def pause_run(self, run_id: UUID, *, mentor_id: UUID) -> GenerationRunOut:
        """Cooperatively pause a running generation run (idempotent)."""
        run = await self._get_run_for_mentor(run_id, mentor_id)
        if run.status == GenerationRunStatus.PAUSED.value:
            return self._run_out(run)
        if run.status != GenerationRunStatus.RUNNING.value:
            raise GenerationRunNotPausableException(
                f"Generation run cannot be paused while status is '{run.status}'."
            )

        paused = await self.repo.pause_run(run_id, reason="user")
        if not paused:
            updated = await self.repo.get_by_id(run_id)
            if (
                updated is not None
                and updated.status == GenerationRunStatus.PAUSED.value
            ):
                return self._run_out(updated)
            raise GenerationRunNotPausableException()

        updated = await self.repo.get_by_id(run_id)
        if updated is None:
            raise GenerationRunNotFoundException()
        return self._run_out(updated)

    async def abandon_run(
        self,
        run_id: UUID,
        *,
        mentor_id: UUID,
        reason: str = "user",
    ) -> GenerationRunOut:
        """Terminal abandon — row retained for audit (idempotent)."""
        run = await self._get_run_for_mentor(run_id, mentor_id)
        if run.status == GenerationRunStatus.ABANDONED.value:
            return self._run_out(run)
        if run.status not in _ABANDONABLE_STATUSES:
            raise GenerationRunNotAbandonableException(
                f"Generation run cannot be abandoned while status is '{run.status}'."
            )

        if run.pipeline == GenerationRunPipeline.STUDY_MATERIAL.value:
            from src.api.core.services.study_agent_services.study_material_service import (  # noqa: PLC0415
                StudyMaterialService,
            )

            await StudyMaterialService(
                self.session
            ).discard_artifacts_for_generation_run(
                run_id,
                user_id=mentor_id,
            )

        abandoned = await self.repo.abandon_run(run_id, reason=reason)
        if not abandoned:
            updated = await self.repo.get_by_id(run_id)
            if (
                updated is not None
                and updated.status == GenerationRunStatus.ABANDONED.value
            ):
                return self._run_out(updated)
            raise GenerationRunNotAbandonableException()

        await release_generation_lock(
            self.session,
            pipeline=run.pipeline,
            resource_id=run.resource_id,
        )

        updated = await self.repo.get_by_id(run_id)
        if updated is None:
            raise GenerationRunNotFoundException()
        return self._run_out(updated)

    async def recover_stale_runs(
        self,
        threshold_minutes: int | None = None,
    ) -> int:
        """Mark stale running runs as failed with resumable stale_worker error."""
        minutes = threshold_minutes or settings.generation_stale_threshold_minutes
        threshold = GenerationRunRepository.stale_threshold(minutes)
        stale_runs = await self.repo.find_stale_running_runs(threshold)
        recovered = 0
        for run in stale_runs:
            marked = await self.repo.mark_stale_failed(
                run.run_id,
                stale_before=threshold,
                expected_execution_token=run.execution_token,
            )
            if marked:
                recovered += 1
                stale_minutes = int(
                    (datetime.now(UTC) - run.updated_at).total_seconds() // 60
                )
                logger.warning(
                    "generation.run.stale_recovered",
                    extra={
                        "run_id": str(run.run_id),
                        "stale_minutes": stale_minutes,
                        "pipeline": run.pipeline,
                        "resource_id": str(run.resource_id),
                    },
                )
                await release_generation_lock(
                    self.session,
                    pipeline=run.pipeline,
                    resource_id=run.resource_id,
                )
        return recovered

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
