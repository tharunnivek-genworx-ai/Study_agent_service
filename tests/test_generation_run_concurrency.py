"""Integration-style tests for generation run concurrency controls."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.core.services.generation_run_service import GenerationRunService
from src.api.schemas.generation_run_schema import (
    GenerationRunCreate,
    GenerationRunMode,
    GenerationRunPipeline,
    GenerationRunResourceType,
    GenerationRunStatus,
)


def _make_running_run(
    *, resource_id=None, pipeline="study_material"
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        run_id=uuid4(),
        pipeline=pipeline,
        resource_type="node",
        resource_id=resource_id or uuid4(),
        node_id=uuid4(),
        space_id=uuid4(),
        mentor_id=uuid4(),
        status=GenerationRunStatus.RUNNING.value,
        last_completed_node=None,
        generation_mode="generate",
        artifact_run_id=None,
        progress_step_index=0,
        error_message=None,
        error_type=None,
        next_llm_retry_at=None,
        attempt_count=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
        checkpoint_state={},
        request_params={},
    )


def test_start_run_raises_409_when_running_exists() -> None:
    async def _run() -> None:
        resource_id = uuid4()
        active = _make_running_run(resource_id=resource_id)

        session = MagicMock()
        session.commit = AsyncMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.supersede_stale_runs = AsyncMock(return_value=0)
        service.repo.get_active_run = AsyncMock(return_value=active)
        service.progress = MagicMock()

        payload = GenerationRunCreate(
            pipeline=GenerationRunPipeline.STUDY_MATERIAL,
            resource_type=GenerationRunResourceType.NODE,
            resource_id=resource_id,
            node_id=uuid4(),
            space_id=uuid4(),
            mentor_id=uuid4(),
            generation_mode=GenerationRunMode.GENERATE,
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.start_run(payload)

        assert exc_info.value.status_code == 409
        service.repo.create.assert_not_called()

    asyncio.run(_run())


def test_start_run_supersedes_failed_before_create() -> None:
    async def _run() -> None:
        resource_id = uuid4()
        session = MagicMock()
        session.commit = AsyncMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.supersede_stale_runs = AsyncMock(return_value=1)
        service.repo.get_active_run = AsyncMock(return_value=None)
        service.repo.create = AsyncMock(
            return_value=SimpleNamespace(
                run_id=uuid4(),
                pipeline="study_material",
                resource_type="node",
                resource_id=resource_id,
                node_id=uuid4(),
                space_id=uuid4(),
                mentor_id=uuid4(),
                status=GenerationRunStatus.RUNNING.value,
                last_completed_node=None,
                generation_mode="generate",
                artifact_run_id=None,
                progress_step_index=0,
                error_message=None,
                error_type=None,
                next_llm_retry_at=None,
                attempt_count=0,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                completed_at=None,
            )
        )
        service.progress.start = AsyncMock()

        payload = GenerationRunCreate(
            pipeline=GenerationRunPipeline.STUDY_MATERIAL,
            resource_type=GenerationRunResourceType.NODE,
            resource_id=resource_id,
            node_id=uuid4(),
            space_id=uuid4(),
            mentor_id=uuid4(),
            generation_mode=GenerationRunMode.GENERATE,
        )

        with (
            patch(
                "src.api.core.services.generation_run_service.require_generation_lock",
                new_callable=AsyncMock,
            ),
            patch(
                "src.api.core.services.generation_run_service.release_generation_lock",
                new_callable=AsyncMock,
            ) as release_lock,
        ):
            await service.start_run(payload)

        release_lock.assert_awaited_once()

        service.repo.supersede_stale_runs.assert_awaited_once_with(
            resource_id=resource_id,
            pipeline=GenerationRunPipeline.STUDY_MATERIAL.value,
        )
        service.repo.create.assert_awaited_once()

    asyncio.run(_run())


def test_cancel_run_marks_running_as_cancelled() -> None:
    async def _run() -> None:
        mentor_id = uuid4()
        run_id = uuid4()
        run = _make_running_run()
        run.run_id = run_id
        run.mentor_id = mentor_id
        run.status = GenerationRunStatus.RUNNING.value

        cancelled = SimpleNamespace(**vars(run))
        cancelled.status = GenerationRunStatus.CANCELLED.value

        session = MagicMock()
        session.execute = AsyncMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(side_effect=[run, cancelled])
        service.repo.cancel_run = AsyncMock(return_value=True)

        result = await service.cancel_run(run_id, mentor_id=mentor_id)

        assert result.status == GenerationRunStatus.CANCELLED.value
        service.repo.cancel_run.assert_awaited_once_with(run_id)

    asyncio.run(_run())


def test_cancel_run_rejects_completed_status() -> None:
    async def _run() -> None:
        mentor_id = uuid4()
        run_id = uuid4()
        run = _make_running_run()
        run.run_id = run_id
        run.mentor_id = mentor_id
        run.status = GenerationRunStatus.COMPLETED.value

        session = MagicMock()
        session.commit = AsyncMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(return_value=run)

        with pytest.raises(HTTPException) as exc_info:
            await service.cancel_run(run_id, mentor_id=mentor_id)

        assert exc_info.value.status_code == 409

    asyncio.run(_run())


def test_resume_rejects_when_another_run_is_active() -> None:
    async def _run() -> None:
        resource_id = uuid4()
        run_id = uuid4()
        mentor_id = uuid4()
        run = _make_running_run(resource_id=resource_id)
        run.run_id = run_id
        run.mentor_id = mentor_id
        run.status = GenerationRunStatus.FAILED.value

        other_active = _make_running_run(resource_id=resource_id)
        other_active.run_id = uuid4()

        session = MagicMock()
        session.commit = AsyncMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(return_value=run)
        service.repo.get_active_run = AsyncMock(return_value=other_active)

        with pytest.raises(HTTPException) as exc_info:
            await service.resume_run(run_id, mentor_id=mentor_id)

        assert exc_info.value.status_code == 409

    asyncio.run(_run())


def test_get_active_run_for_resource_returns_running_run() -> None:
    async def _run() -> None:
        mentor_id = uuid4()
        resource_id = uuid4()
        run = _make_running_run(resource_id=resource_id)
        run.mentor_id = mentor_id
        run.request_params = {"step_profile": "study_generate_with_ref"}

        session = MagicMock()
        session.commit = AsyncMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_active_run = AsyncMock(return_value=run)

        result = await service.get_active_run_for_resource(
            resource_id=resource_id,
            pipeline="study_material",
            mentor_id=mentor_id,
        )

        assert result is not None
        assert result.run_id == run.run_id
        assert result.step_profile == "study_generate_with_ref"
        assert result.status == GenerationRunStatus.RUNNING.value

    asyncio.run(_run())


def test_get_active_run_for_resource_returns_failed_resumable_run() -> None:
    async def _run() -> None:
        mentor_id = uuid4()
        resource_id = uuid4()
        run = _make_running_run(resource_id=resource_id)
        run.mentor_id = mentor_id
        run.status = GenerationRunStatus.FAILED.value
        run.error_message = "LLM unavailable"
        run.error_type = "terminal_llm_failure"
        run.request_params = {"step_profile": "study_generate_with_ref"}

        session = MagicMock()
        session.commit = AsyncMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_active_run = AsyncMock(return_value=run)

        result = await service.get_active_run_for_resource(
            resource_id=resource_id,
            pipeline="study_material",
            mentor_id=mentor_id,
        )

        assert result is not None
        assert result.run_id == run.run_id
        assert result.status == GenerationRunStatus.FAILED.value
        assert result.resumable is True
        assert result.step_profile == "study_generate_with_ref"

    asyncio.run(_run())


def test_get_active_run_for_resource_hides_other_mentor() -> None:
    async def _run() -> None:
        resource_id = uuid4()
        run = _make_running_run(resource_id=resource_id)
        run.mentor_id = uuid4()

        session = MagicMock()
        session.commit = AsyncMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_active_run = AsyncMock(return_value=run)

        result = await service.get_active_run_for_resource(
            resource_id=resource_id,
            pipeline="study_material",
            mentor_id=uuid4(),
        )

        assert result is None

    asyncio.run(_run())


def test_acquire_lock_for_run_skips_cancelled_run() -> None:
    async def _run() -> None:
        run_id = uuid4()
        run = _make_running_run()
        run.run_id = run_id
        run.status = GenerationRunStatus.CANCELLED.value

        session = MagicMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(return_value=run)

        with patch(
            "src.api.core.services.generation_run_service.try_acquire_generation_lock",
            new_callable=AsyncMock,
        ) as try_lock:
            result = await service.acquire_lock_for_run(run_id)

        assert result is None
        try_lock.assert_not_awaited()

    asyncio.run(_run())


def test_acquire_lock_for_run_fails_run_when_lock_unavailable() -> None:
    async def _run() -> None:
        run_id = uuid4()
        run = _make_running_run()
        run.run_id = run_id

        session = MagicMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(return_value=run)
        service.fail_run = AsyncMock()

        with patch(
            "src.api.core.services.generation_run_service.try_acquire_generation_lock",
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await service.acquire_lock_for_run(run_id)

        assert result is None
        service.fail_run.assert_awaited_once()

    asyncio.run(_run())
