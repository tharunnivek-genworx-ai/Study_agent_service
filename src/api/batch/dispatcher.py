"""Dispatch batch processing after the API transaction commits."""

from __future__ import annotations

import logging
from uuid import UUID

from src.api.config import settings

logger = logging.getLogger(__name__)


async def dispatch_batch_job(batch_id: UUID | str) -> None:
    """Enqueue or run ``process_batch`` once the create-batch row is committed."""
    batch_id_str = str(batch_id)
    if settings.batch_dispatch_mode == "inline":
        from src.api.batch.tasks import process_batch

        await process_batch(batch_id_str)
        return

    from src.api.batch.procrastinate_app import app
    from src.api.batch.tasks import process_batch

    async with app.open_async():
        job_id = await process_batch.defer_async(batch_id=batch_id_str)
    logger.info(
        "Deferred process_batch job",
        extra={"batch_id": batch_id_str, "procrastinate_job_id": job_id},
    )
