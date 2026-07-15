"""Tests for idempotent generation run execution (no duplicate LLM runs)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.core.services.study_agent_services.study_material_service import (
    StudyMaterialService,
)
from src.api.schemas import GenerationRunStatus


@pytest.mark.asyncio
async def test_execute_generate_skips_graph_when_version_already_persisted() -> None:
    run_id = uuid4()
    node_id = uuid4()
    mentor_id = uuid4()
    session = MagicMock()
    service = StudyMaterialService(session)

    run = SimpleNamespace(
        run_id=run_id,
        status=GenerationRunStatus.RUNNING.value,
        request_params={"node_id": str(node_id)},
        execution_token=uuid4(),
        last_completed_node=None,
        checkpoint_state=None,
    )

    with (
        patch.object(
            StudyMaterialService,
            "_settle_run_if_output_already_persisted",
            new_callable=AsyncMock,
            return_value=True,
        ) as settle,
        patch(
            "src.api.core.services.study_agent_services.study_material_service.GenerationRunService"
        ) as run_service_cls,
        patch(
            "src.api.core.services.study_agent_services.study_material_service._get_node_and_assert_space_access",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.core.services.study_agent_services.study_material_service.run_study_material_generation",
            new_callable=AsyncMock,
        ) as run_graph,
    ):
        run_service_cls.return_value.acquire_lock_for_run = AsyncMock(return_value=run)

        await service.execute_generate_study_material(
            run_id=run_id,
            user_id=mentor_id,
        )

    settle.assert_awaited_once()
    run_graph.assert_not_awaited()
