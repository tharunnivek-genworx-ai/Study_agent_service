"""Background execution of long-running generation jobs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.clients.postgres.database import SessionLocal

logger = logging.getLogger(__name__)

# Let the HTTP handler return its request-scoped DB session before the worker
# tries to acquire the per-node advisory lock (avoids transient lock races).
_JOB_START_DELAY_SECONDS = 0.05

T = TypeVar("T")

JobCallable = Callable[[AsyncSession], Awaitable[T]]
AfterCommitCallback = Callable[[], None]


async def run_generation_job[T](job: JobCallable[T]) -> T:
    """Execute a generation job in an isolated DB session."""
    from src.api.utils.generation_progress.advisory_lock import (
        release_all_generation_locks,
    )

    async with SessionLocal() as session:
        try:
            result = await job(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
        finally:
            await release_all_generation_locks(session)


def schedule_generation_job(
    job: JobCallable[Any],
    *,
    after_commit: AfterCommitCallback | None = None,
) -> asyncio.Task[Any]:
    """Fire-and-forget a generation job on the event loop.

    ``after_commit`` runs after the job session commits (or fails). Used by the
    batch queue to start the next item only once durable run status is visible.
    """

    async def _wrapper() -> Any:
        try:
            await asyncio.sleep(_JOB_START_DELAY_SECONDS)
            return await run_generation_job(job)
        except Exception:
            logger.exception("Background generation job failed")
            return None
        finally:
            if after_commit is not None:
                try:
                    after_commit()
                except Exception:
                    logger.exception("after_commit callback failed")

    return asyncio.create_task(_wrapper())
