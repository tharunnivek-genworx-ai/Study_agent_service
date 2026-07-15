"""Tests for the periodic stale-generation-run sweeper task."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_sweep_recovers_stale_runs_and_commits() -> None:
    from src.api.batch.tasks import sweep_stale_generation_runs

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    with (
        patch("src.api.batch.tasks.SessionLocal", return_value=session),
        patch("src.api.batch.tasks.GenerationRunService") as service_cls,
    ):
        service_cls.return_value.recover_stale_runs = AsyncMock(return_value=2)

        await sweep_stale_generation_runs(timestamp=0)

    service_cls.return_value.recover_stale_runs.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_rolls_back_on_error() -> None:
    from src.api.batch.tasks import sweep_stale_generation_runs

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    with (
        patch("src.api.batch.tasks.SessionLocal", return_value=session),
        patch("src.api.batch.tasks.GenerationRunService") as service_cls,
    ):
        service_cls.return_value.recover_stale_runs = AsyncMock(
            side_effect=RuntimeError("db down")
        )

        await sweep_stale_generation_runs(timestamp=0)

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_recover_stale_runs_uses_timestamp_and_execution_token_guards() -> None:
    from src.api.core.services.generation_run_service import GenerationRunService

    run = SimpleNamespace(
        run_id=uuid4(),
        execution_token=uuid4(),
        updated_at=datetime.now(UTC) - timedelta(minutes=21),
        pipeline="quiz",
        resource_id=uuid4(),
    )
    service = GenerationRunService(MagicMock())
    service.repo.find_stale_running_runs = AsyncMock(return_value=[run])
    service.repo.mark_stale_failed = AsyncMock(return_value=True)

    with patch(
        "src.api.core.services.generation_run_service.release_generation_lock",
        new_callable=AsyncMock,
    ):
        recovered = await service.recover_stale_runs(threshold_minutes=20)

    assert recovered == 1
    threshold = service.repo.find_stale_running_runs.await_args.args[0]
    service.repo.mark_stale_failed.assert_awaited_once_with(
        run.run_id,
        stale_before=threshold,
        expected_execution_token=run.execution_token,
    )


@pytest.mark.asyncio
async def test_recover_stale_runs_ignores_attempt_changed_during_sweep() -> None:
    from src.api.core.services.generation_run_service import GenerationRunService

    run = SimpleNamespace(
        run_id=uuid4(),
        execution_token=uuid4(),
        updated_at=datetime.now(UTC) - timedelta(minutes=21),
        pipeline="hint",
        resource_id=uuid4(),
    )
    service = GenerationRunService(MagicMock())
    service.repo.find_stale_running_runs = AsyncMock(return_value=[run])
    service.repo.mark_stale_failed = AsyncMock(return_value=False)

    with patch(
        "src.api.core.services.generation_run_service.release_generation_lock",
        new_callable=AsyncMock,
    ) as release_lock:
        recovered = await service.recover_stale_runs(threshold_minutes=20)

    assert recovered == 0
    release_lock.assert_not_awaited()
