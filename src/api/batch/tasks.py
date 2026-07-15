"""Procrastinate tasks for durable generate-all batch execution."""

from __future__ import annotations

import logging
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.batch.dispatcher import dispatch_batch_job
from src.api.batch.procrastinate_app import app
from src.api.config import settings
from src.api.core.exceptions import (
    GenerationAdvisoryLockUnavailableException,
    GenerationRunConflictException,
)
from src.api.core.services.batch_orchestration_service import (
    BatchOrchestrationService,
)
from src.api.core.services.generation_run_service import GenerationRunService
from src.api.core.services.study_agent_services.study_material_service import (
    StudyMaterialService,
)
from src.api.data.clients.postgres.database import SessionLocal
from src.api.data.models.postgres.generation.batch_jobs import BatchJob, BatchJobStep
from src.api.data.models.postgres.generation.generation_runs import GenerationRun
from src.api.schemas.common import GenerationRunStatus
from src.api.schemas.study_material_schemas.study_material_schema import (
    StudyMaterialGenerateRequest,
)
from src.api.utils.generation_progress.advisory_lock import (
    release_all_generation_locks,
)
from src.api.utils.generation_progress.generation_job_executor import (
    run_generation_job,
)

logger = logging.getLogger(__name__)

_TERMINAL_BATCH_STATUSES = frozenset({"completed", "failed", "cancelled"})
_TERMINAL_RUN_STATUSES = frozenset(
    {
        GenerationRunStatus.COMPLETED.value,
        GenerationRunStatus.FAILED.value,
        GenerationRunStatus.ABANDONED.value,
        GenerationRunStatus.SUPERSEDED.value,
    }
)


def _policy_reference_material_id(policy: dict | None) -> UUID | None:
    raw = (policy or {}).get("reference_material_id")
    if raw is None:
        return None
    return UUID(str(raw))


async def _batch_has_pending_steps(session: AsyncSession, batch_id: UUID) -> bool:
    count = await session.scalar(
        select(func.count())
        .select_from(BatchJobStep)
        .where(
            BatchJobStep.batch_id == batch_id,
            BatchJobStep.status == "pending",
        )
    )
    return bool(count and count > 0)


async def _get_running_step(
    session: AsyncSession, batch_id: UUID
) -> BatchJobStep | None:
    result = await session.execute(
        select(BatchJobStep)
        .where(
            BatchJobStep.batch_id == batch_id,
            BatchJobStep.status == "running",
        )
        .order_by(BatchJobStep.position.asc())
        .limit(1)
    )
    return cast(BatchJobStep | None, result.scalars().first())


async def _reset_step_to_pending(session: AsyncSession, step: BatchJobStep) -> None:
    step.status = "pending"
    step.started_at = None
    step.generation_run_id = None
    step.error_message = None
    await session.flush()


async def _finalize_from_run(
    session: AsyncSession,
    *,
    batch_id: UUID,
    step_id: UUID,
    run_id: UUID,
) -> None:
    orchestrator = BatchOrchestrationService(session)
    run = await session.get(GenerationRun, run_id)
    if run is None:
        await orchestrator.finalize_step(
            batch_id,
            step_id,
            run_status=GenerationRunStatus.FAILED.value,
            error_message="Generation run not found.",
        )
        return

    error_message = None
    if run.status != GenerationRunStatus.COMPLETED.value:
        error_message = run.error_message or f"Generation run ended as {run.status}."
    await orchestrator.finalize_step(
        batch_id,
        step_id,
        run_status=run.status,
        error_message=error_message,
    )


async def _execute_generation_run(*, run_id: UUID, mentor_id: UUID) -> None:
    async def job(session: AsyncSession) -> None:
        await StudyMaterialService(session).execute_generate_study_material(
            run_id=run_id,
            user_id=mentor_id,
        )

    await run_generation_job(job)


async def _fail_run_if_left_running(
    run_id: UUID,
    *,
    expected_execution_token: UUID | None = None,
) -> None:
    """Guarantee a finished worker never strands a run in RUNNING.

    If the job body was killed mid-finalize, hit a poisoned DB session, or
    returned early without settling, the row can stay ``running`` with no
    result and the UI spins forever. Flip any still-``running`` row to a
    resumable ``failed`` on a fresh session so the UI shows Continue / Delete.
    Idempotent: a no-op once the run is completed / paused / failed.
    """
    # Without the attempt token we cannot distinguish this worker from a later
    # resumed attempt. The periodic stale sweeper will safely recover the row.
    if expected_execution_token is None:
        return
    try:
        from src.api.data.repositories import GenerationRunRepository

        async with SessionLocal() as session:
            marked = await GenerationRunRepository(session).mark_stale_failed(
                run_id,
                expected_execution_token=expected_execution_token,
            )
            await session.commit()
        if marked:
            logger.warning(
                "Run left RUNNING after worker finished; marked failed/resumable",
                extra={"run_id": str(run_id)},
            )
    except Exception:
        logger.exception(
            "Failed to reconcile run status after worker finish",
            extra={"run_id": str(run_id)},
        )


@app.task(name="execute_generation_run", retry=0)
async def execute_generation_run_job(
    run_id: str,
    mentor_id: str,
    role: str = "mentor",
    *,
    is_resume: bool = False,
) -> None:
    """Durable worker entrypoint for single-node and resume generation runs."""
    from src.api.utils.generation_progress.generation_run_dispatch import (
        execute_scheduled_generation_run,
    )

    run_uuid = UUID(run_id)
    execution_token: UUID | None = None

    async def job(session: AsyncSession) -> None:
        nonlocal execution_token
        run = await session.get(GenerationRun, run_uuid)
        execution_token = run.execution_token if run is not None else None
        await execute_scheduled_generation_run(
            session,
            run_id=run_uuid,
            mentor_id=UUID(mentor_id),
            role=role,
            is_resume=is_resume,
        )

    try:
        await run_generation_job(job)
    finally:
        await _fail_run_if_left_running(
            run_uuid,
            expected_execution_token=execution_token,
        )


async def _reconcile_running_step(
    session: AsyncSession,
    *,
    batch_id: UUID,
    mentor_id: UUID,
) -> bool:
    """Recover or finalize a running step when claim_next_step returns None."""
    step = await _get_running_step(session, batch_id)
    if step is None:
        return False

    if step.generation_run_id is None:
        await _reset_step_to_pending(session, step)
        return True

    run = await session.get(GenerationRun, step.generation_run_id)
    if run is None:
        await _reset_step_to_pending(session, step)
        return True

    if run.status in _TERMINAL_RUN_STATUSES:
        await _finalize_from_run(
            session,
            batch_id=batch_id,
            step_id=step.step_id,
            run_id=run.run_id,
        )
        return True

    if run.status != GenerationRunStatus.RUNNING.value:
        return False

    # Do not retain ORM attribute reads across commit/other-session execution.
    # This also keeps the path safe with expire_on_commit=True sessions.
    run_id = run.run_id
    step_id = step.step_id
    await session.commit()
    await _execute_generation_run(run_id=run_id, mentor_id=mentor_id)

    async with SessionLocal() as finalize_session:
        await _finalize_from_run(
            finalize_session,
            batch_id=batch_id,
            step_id=step_id,
            run_id=run_id,
        )
        await finalize_session.commit()
    return True


async def _maybe_chain_next_step(batch_id: UUID) -> None:
    async with SessionLocal() as session:
        batch = await session.get(BatchJob, batch_id)
        if batch is None or batch.status in _TERMINAL_BATCH_STATUSES:
            return
        has_pending = await _batch_has_pending_steps(session, batch_id)
    if has_pending:
        await dispatch_batch_job(batch_id)


@app.task(name="process_batch", retry=3)
async def process_batch(batch_id: str) -> None:
    """Process one batch step, then chain the next step when more work remains."""
    batch_uuid = UUID(batch_id)
    run_id: UUID | None = None
    step_id: UUID | None = None
    mentor_id: UUID | None = None

    async with SessionLocal() as session:
        try:
            orchestrator = BatchOrchestrationService(session)
            batch = await orchestrator._get_batch(batch_uuid)
            if batch is None or batch.status in _TERMINAL_BATCH_STATUSES:
                return

            mentor_id = batch.mentor_id
            step = await orchestrator.claim_next_step(batch_uuid)
            if step is None:
                reconciled = await _reconcile_running_step(
                    session,
                    batch_id=batch_uuid,
                    mentor_id=mentor_id,
                )
                await session.commit()
                if reconciled:
                    await _maybe_chain_next_step(batch_uuid)
                return

            step_id = step.step_id
            step_node_id = step.node_id
            reference_material_id = _policy_reference_material_id(
                batch.policy if isinstance(batch.policy, dict) else None
            )
            study_material_service = StudyMaterialService(session)
            try:
                run_id = await study_material_service.start_generate_study_material(
                    step_node_id,
                    StudyMaterialGenerateRequest(
                        reference_material_id=reference_material_id
                    ),
                    mentor_id,
                    "mentor",
                )
            except (
                GenerationRunConflictException,
                GenerationAdvisoryLockUnavailableException,
            ) as exc:
                await _reset_step_to_pending(session, step)
                await session.commit()
                logger.info(
                    "Batch step re-queued after generation conflict",
                    extra={
                        "batch_id": batch_id,
                        "step_id": str(step_id),
                        "node_id": str(step_node_id),
                        "reason": str(getattr(exc, "detail", exc)),
                    },
                )
                raise
            except Exception as exc:
                await orchestrator.finalize_step(
                    batch_uuid,
                    step_id,
                    run_status=GenerationRunStatus.FAILED.value,
                    error_message=str(exc),
                )
                await session.commit()
                await _maybe_chain_next_step(batch_uuid)
                return

            await orchestrator.attach_generation_run(step_id, run_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await release_all_generation_locks(session)

    if run_id is None or step_id is None or mentor_id is None:
        return

    await _execute_generation_run(run_id=run_id, mentor_id=mentor_id)

    async with SessionLocal() as session:
        try:
            await _finalize_from_run(
                session,
                batch_id=batch_uuid,
                step_id=step_id,
                run_id=run_id,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await release_all_generation_locks(session)

    await _maybe_chain_next_step(batch_uuid)


@app.periodic(cron=settings.generation_stale_sweep_cron)
@app.task(name="sweep_stale_generation_runs")
async def sweep_stale_generation_runs(timestamp: int) -> None:
    """Fail runs whose worker died mid-flight so the UI stops spinning forever.

    A run stays ``running`` if the worker process is terminated (Cloud Run
    scale-down, OOM, timeout) between the final graph checkpoint and
    ``_finalize_generation_run``. This periodic sweep marks such rows as
    ``failed`` with a resumable ``stale_worker`` error once they exceed the
    stale threshold, surfacing Continue / Delete run in the UI instead of an
    infinite loader.
    """
    del timestamp
    recovered = 0
    async with SessionLocal() as session:
        try:
            recovered = await GenerationRunService(session).recover_stale_runs()
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Stale generation run sweep failed")
            return
    if recovered:
        logger.info(
            "Stale generation run sweep recovered %d run(s)",
            recovered,
        )
