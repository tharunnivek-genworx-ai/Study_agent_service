"""Background execution of long-running generation jobs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.clients.postgres.database import SessionLocal

logger = logging.getLogger(__name__)

JobCallable = Callable[[AsyncSession], Awaitable[Any]]


async def run_generation_job(job: JobCallable) -> Any:
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


def schedule_generation_job(job: JobCallable) -> asyncio.Task[Any]:
    """Fire-and-forget a generation job on the event loop."""

    async def _wrapper() -> Any:
        try:
            return await run_generation_job(job)
        except Exception:
            logger.exception("Background generation job failed")
            return None

    return asyncio.create_task(_wrapper())
