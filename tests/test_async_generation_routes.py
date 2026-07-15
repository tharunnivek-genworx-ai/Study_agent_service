"""Tests that generation POST routes return 202 and schedule background jobs."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.rest.routes.study_agent_routes import study_material_route


@pytest.mark.asyncio
async def test_generate_study_material_returns_202_and_schedules_job() -> None:
    node_id = uuid4()
    user_id = uuid4()
    run_id = uuid4()

    db = MagicMock()
    db.commit = AsyncMock()

    current_user = MagicMock()
    current_user.sub = user_id
    current_user.role = "mentor"

    payload = MagicMock()

    with (
        patch(
            "src.api.rest.routes.study_agent_routes.study_material_route.StudyMaterialService",
        ) as service_cls,
        patch(
            "src.api.rest.routes.study_agent_routes.study_material_route.schedule_generation_job",
        ) as schedule_job,
    ):
        service_cls.return_value.start_generate_study_material = AsyncMock(
            return_value=run_id
        )

        response = await study_material_route.generate_study_material(
            node_id=node_id,
            payload=payload,
            db=db,
            current_user=current_user,
        )

    assert response.run_id == run_id
    assert response.pipeline == "study_material"
    assert response.status == "running"
    db.commit.assert_awaited_once()
    schedule_job.assert_called_once()


def test_generation_job_executor_runs_coro_in_isolated_session() -> None:
    async def _run() -> None:
        from src.api.utils.generation_progress.generation_job_executor import (
            run_generation_job,
        )

        executed = False

        async def job(session) -> None:
            nonlocal executed
            executed = True
            assert session is not None

        with (
            patch(
                "src.api.utils.generation_progress.generation_job_executor.engine"
            ) as db_engine,
            patch(
                "src.api.utils.generation_progress.generation_job_executor.SessionLocal"
            ) as session_local,
            patch(
                "src.api.utils.generation_progress.advisory_lock.release_all_generation_locks",
                new_callable=AsyncMock,
            ) as release_locks,
        ):
            connection = MagicMock()
            connection_context = MagicMock()
            connection_context.__aenter__ = AsyncMock(return_value=connection)
            connection_context.__aexit__ = AsyncMock(return_value=None)
            db_engine.connect.return_value = connection_context

            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            session_local.return_value = mock_session

            await run_generation_job(job)

        assert executed is True
        session_local.assert_called_once_with(bind=connection)
        mock_session.commit.assert_awaited_once()
        assert release_locks.await_count == 2

    asyncio.run(_run())
