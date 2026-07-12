"""Procrastinate tasks for durable generate-all batch execution."""

from __future__ import annotations

import logging
from typing import cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.batch.dispatcher import dispatch_batch_job
from src.api.batch.procrastinate_app import app
from src.api.core.exceptions import (
    GenerationAdvisoryLockUnavailableException,
    GenerationRunConflictException,
)
from src.api.core.services.batch_orchestration_service import (
    BatchOrchestrationService,
)
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
        GenerationRunStatus.CANCELLED.value,
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

    await session.commit()
    await _execute_generation_run(run_id=run.run_id, mentor_id=mentor_id)

    async with SessionLocal() as finalize_session:
        await _finalize_from_run(
            finalize_session,
            batch_id=batch_id,
            step_id=step.step_id,
            run_id=run.run_id,
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
            study_material_service = StudyMaterialService(session)
            try:
                run_id = await study_material_service.start_generate_study_material(
                    step.node_id,
                    StudyMaterialGenerateRequest(
                        reference_material_id=_policy_reference_material_id(
                            batch.policy if isinstance(batch.policy, dict) else None
                        )
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
                        "step_id": str(step.step_id),
                        "node_id": str(step.node_id),
                        "reason": str(getattr(exc, "detail", exc)),
                    },
                )
                raise
            except Exception as exc:
                await orchestrator.finalize_step(
                    batch_uuid,
                    step.step_id,
                    run_status=GenerationRunStatus.FAILED.value,
                    error_message=str(exc),
                )
                await session.commit()
                await _maybe_chain_next_step(batch_uuid)
                return

            await orchestrator.attach_generation_run(step.step_id, run_id)
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
