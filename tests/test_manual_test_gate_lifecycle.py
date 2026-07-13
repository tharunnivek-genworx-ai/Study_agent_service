"""Manual test gate 2 — backend lifecycle scenarios (study material scope)."""

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
    GenerationRunPipeline,
    GenerationRunStatus,
)
from src.api.utils.generation_progress.request_fingerprint import (
    compute_request_fingerprint_from_run,
)


def _make_run(**overrides) -> SimpleNamespace:
    now = datetime.now(UTC)
    base = dict(
        run_id=uuid4(),
        pipeline=GenerationRunPipeline.STUDY_MATERIAL.value,
        resource_type="node",
        resource_id=uuid4(),
        node_id=uuid4(),
        space_id=uuid4(),
        mentor_id=uuid4(),
        status=GenerationRunStatus.RUNNING.value,
        last_completed_node=None,
        generation_mode="generate",
        artifact_run_id=None,
        progress_step_index=1,
        error_message=None,
        error_type=None,
        next_llm_retry_at=None,
        attempt_count=0,
        created_at=now,
        updated_at=now,
        completed_at=None,
        checkpoint_state={},
        request_params={"reference_material_id": str(uuid4())},
        request_fingerprint=None,
        execution_token=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_scenario_1_pause_running_run() -> None:
    async def _run() -> None:
        mentor_id = uuid4()
        run_id = uuid4()
        run = _make_run(run_id=run_id, mentor_id=mentor_id)
        paused = _make_run(
            run_id=run_id,
            mentor_id=mentor_id,
            status=GenerationRunStatus.PAUSED.value,
        )

        session = MagicMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(side_effect=[run, paused])
        service.repo.pause_run = AsyncMock(return_value=True)

        result = await service.pause_run(run_id, mentor_id=mentor_id)
        assert result.status == GenerationRunStatus.PAUSED.value
        service.repo.pause_run.assert_awaited_once_with(run_id, reason="user")

    asyncio.run(_run())


def test_scenario_3_abandon_calls_discard_artifacts() -> None:
    async def _run() -> None:
        mentor_id = uuid4()
        run_id = uuid4()
        run = _make_run(
            run_id=run_id,
            mentor_id=mentor_id,
            status=GenerationRunStatus.PAUSED.value,
        )
        abandoned = _make_run(
            run_id=run_id,
            mentor_id=mentor_id,
            status=GenerationRunStatus.ABANDONED.value,
        )

        session = MagicMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(side_effect=[run, abandoned])
        service.repo.abandon_run = AsyncMock(return_value=True)

        with (
            patch(
                "src.api.core.services.generation_run_service.release_generation_lock",
                new_callable=AsyncMock,
            ),
            patch(
                "src.api.core.services.study_agent_services.study_material_service.StudyMaterialService.discard_artifacts_for_generation_run",
                new_callable=AsyncMock,
            ) as discard,
        ):
            result = await service.abandon_run(run_id, mentor_id=mentor_id)

        assert result.status == GenerationRunStatus.ABANDONED.value
        discard.assert_awaited_once_with(run_id, user_id=mentor_id)

    asyncio.run(_run())


def test_scenario_4_pause_rejects_completed_run() -> None:
    async def _run() -> None:
        mentor_id = uuid4()
        run_id = uuid4()
        run = _make_run(
            run_id=run_id,
            mentor_id=mentor_id,
            status=GenerationRunStatus.COMPLETED.value,
        )

        session = MagicMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(return_value=run)

        with pytest.raises(HTTPException) as exc_info:
            await service.pause_run(run_id, mentor_id=mentor_id)

        assert exc_info.value.status_code == 409

    asyncio.run(_run())


def test_scenario_5_resume_rejects_fingerprint_mismatch() -> None:
    async def _run() -> None:
        mentor_id = uuid4()
        run_id = uuid4()
        node_id = uuid4()
        ref_id = uuid4()
        params = {"reference_material_id": str(ref_id)}
        fingerprint = compute_request_fingerprint_from_run(
            pipeline=GenerationRunPipeline.STUDY_MATERIAL.value,
            node_id=node_id,
            generation_mode="generate",
            request_params=params,
        )
        run = _make_run(
            run_id=run_id,
            mentor_id=mentor_id,
            node_id=node_id,
            status=GenerationRunStatus.PAUSED.value,
            request_params=params,
            request_fingerprint=fingerprint,
        )

        session = MagicMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(return_value=run)

        changed_params = {"reference_material_id": str(uuid4())}
        run.request_params = changed_params

        with pytest.raises(HTTPException) as exc_info:
            await service.begin_resume(run_id, mentor_id=mentor_id)

        assert exc_info.value.status_code == 409
        assert "changed" in str(exc_info.value.detail).lower()

    asyncio.run(_run())


def test_scenario_3_abandon_rejects_completed() -> None:
    async def _run() -> None:
        mentor_id = uuid4()
        run_id = uuid4()
        run = _make_run(
            run_id=run_id,
            mentor_id=mentor_id,
            status=GenerationRunStatus.COMPLETED.value,
        )

        session = MagicMock()
        service = GenerationRunService(session)
        service.repo = MagicMock()
        service.repo.get_by_id = AsyncMock(return_value=run)

        with pytest.raises(HTTPException) as exc_info:
            await service.abandon_run(run_id, mentor_id=mentor_id)

        assert exc_info.value.status_code == 409

    asyncio.run(_run())
