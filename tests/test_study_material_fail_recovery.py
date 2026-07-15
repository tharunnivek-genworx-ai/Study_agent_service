"""Tests for resilient failure handling in the study material service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_fail_generation_run_recovers_from_poisoned_session() -> None:
    """A flush error during finalize must not leave the run stuck RUNNING.

    The first fail_run raises (session poisoned by the original failure); the
    service should roll back and retry so the run is recorded as FAILED.
    """
    from src.api.core.services.study_agent_services import (
        study_material_service as sms,
    )

    session = MagicMock()
    session.rollback = AsyncMock()
    service = sms.StudyMaterialService(session)
    run_id = uuid4()

    fail_run = AsyncMock(side_effect=[RuntimeError("PendingRollbackError"), None])

    with patch.object(sms, "GenerationRunService") as run_service_cls:
        run_service_cls.return_value.fail_run = fail_run
        await service._fail_generation_run(run_id, exc=ValueError("boom"))

    assert fail_run.await_count == 2
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_fail_generation_run_single_call_on_clean_session() -> None:
    from src.api.core.services.study_agent_services import (
        study_material_service as sms,
    )

    session = MagicMock()
    session.rollback = AsyncMock()
    service = sms.StudyMaterialService(session)
    run_id = uuid4()

    fail_run = AsyncMock(return_value=None)

    with patch.object(sms, "GenerationRunService") as run_service_cls:
        run_service_cls.return_value.fail_run = fail_run
        await service._fail_generation_run(run_id, exc=ValueError("boom"))

    fail_run.assert_awaited_once()
    session.rollback.assert_not_awaited()
