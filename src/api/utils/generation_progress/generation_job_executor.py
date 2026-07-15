"""Background execution of long-running generation jobs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import settings
from src.api.data.clients.postgres.database import SessionLocal, engine

logger = logging.getLogger(__name__)

# Let the HTTP handler commit the run row before the worker tries to load it.
_JOB_START_DELAY_SECONDS = 0.05

T = TypeVar("T")

JobCallable = Callable[[AsyncSession], Awaitable[T]]


async def run_generation_job[T](job: JobCallable[T]) -> T:
    """Execute a generation job in an isolated DB session."""
    from src.api.utils.generation_progress.advisory_lock import (
        prepare_session_for_generation,
        release_all_generation_locks,
    )

    # Session-level PostgreSQL advisory locks belong to one physical connection.
    # Bind the session to a checked-out connection for the entire job so commits
    # cannot return the lock-owning connection to the pool before final cleanup.
    async with engine.connect() as connection:
        async with SessionLocal(bind=connection) as session:
            await prepare_session_for_generation(session)
            try:
                result = await job(session)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
            finally:
                await release_all_generation_locks(session)


async def _defer_generation_run_job(
    *,
    run_id: UUID,
    mentor_id: UUID,
    role: str,
    is_resume: bool,
) -> None:
    from src.api.batch.procrastinate_app import app
    from src.api.batch.tasks import execute_generation_run_job

    async with app.open_async():
        task = execute_generation_run_job
        configure = getattr(task, "configure", None)
        if callable(configure):
            task = configure(task_id=f"generation-run:{run_id}")
        await task.defer_async(
            run_id=str(run_id),
            mentor_id=str(mentor_id),
            role=role,
            is_resume=is_resume,
        )


def schedule_generation_job(
    job: JobCallable[Any],
    *,
    run_id: UUID | None = None,
    mentor_id: UUID | None = None,
    role: str = "mentor",
    is_resume: bool = False,
) -> asyncio.Task[Any]:
    """Fire-and-forget a generation job on the event loop or Procrastinate worker.

    When ``batch_dispatch_mode`` is ``procrastinate`` and ``run_id`` / ``mentor_id``
    are provided, the job is enqueued for the durable worker instead of running
    inline on the API Cloud Run instance (which may scale down after HTTP 202).
    """

    async def _wrapper() -> Any:
        try:
            await asyncio.sleep(_JOB_START_DELAY_SECONDS)
            if (
                settings.batch_dispatch_mode == "procrastinate"
                and run_id is not None
                and mentor_id is not None
            ):
                await _defer_generation_run_job(
                    run_id=run_id,
                    mentor_id=mentor_id,
                    role=role,
                    is_resume=is_resume,
                )
                return None
            return await run_generation_job(job)
        except Exception:
            logger.exception("Background generation job failed")
            return None

    return asyncio.create_task(_wrapper())
