"""Tests for generation run dispatch and completion guards."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.data.repositories.generation_run_repository import GenerationRunRepository


@pytest.mark.asyncio
async def test_complete_run_does_not_overwrite_paused_status() -> None:
    session = MagicMock()
    run_id = uuid4()

    result_mock = MagicMock()
    result_mock.rowcount = 0
    session.execute = AsyncMock(return_value=result_mock)
    session.commit = AsyncMock()

    repo = GenerationRunRepository(session)
    completed = await repo.complete_run(run_id)

    assert completed is False
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_schedule_generation_job_defers_when_procrastinate_mode() -> None:
    from src.api.utils.generation_progress.generation_job_executor import (
        schedule_generation_job,
    )

    run_id = uuid4()
    mentor_id = uuid4()
    deferred = AsyncMock()

    with (
        patch(
            "src.api.utils.generation_progress.generation_job_executor.settings"
        ) as settings,
        patch(
            "src.api.utils.generation_progress.generation_job_executor._defer_generation_run_job",
            deferred,
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        settings.batch_dispatch_mode = "procrastinate"
        task = schedule_generation_job(
            AsyncMock(),
            run_id=run_id,
            mentor_id=mentor_id,
        )
        await task

    deferred.assert_awaited_once_with(
        run_id=run_id,
        mentor_id=mentor_id,
        role="mentor",
        is_resume=False,
    )
