"""Tests for invoke_graph_with_progress checkpoint hooks."""

from __future__ import annotations

from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.schemas.generation_progress_schema import GenerationPipeline
from src.api.utils.generation_progress.graph_runner import (
    invoke_graph_with_progress,
    node_succeeded,
)


def test_node_succeeded_false_on_error() -> None:
    assert node_succeeded({"error": "boom"}) is False


def test_node_succeeded_false_on_terminal_llm_failure() -> None:
    assert node_succeeded({"terminal_llm_failure": True}) is False


def test_node_succeeded_true_on_normal_output() -> None:
    assert node_succeeded({"generated_content": "ok"}) is True


@pytest.mark.asyncio
async def test_invoke_graph_checkpoints_after_successful_nodes() -> None:
    run_id = uuid4()
    session = MagicMock()

    async def fake_astream(
        initial_state: dict[str, Any],
        config: dict[str, Any],
        *,
        stream_mode: str,
    ):
        del initial_state, config, stream_mode
        yield {"resolver": {"node_title": "Topic A"}}
        yield {"concept_checklist": {"must_cover_checklist": [{"id": "c1"}]}}

    graph = MagicMock()
    graph.astream = fake_astream

    checkpoint = AsyncMock()
    with patch(
        "src.api.core.services.generation_run_service.GenerationRunService"
    ) as service_cls:
        service_cls.return_value.checkpoint_after_node = checkpoint
        service_cls.return_value.fail_run = AsyncMock()

        result = await invoke_graph_with_progress(
            graph,
            {"node_id": str(uuid4())},
            {"configurable": {"session": session}},
            progress_session_id=None,
            pipeline=GenerationPipeline.STUDY_MATERIAL,
            run_id=run_id,
        )

    assert result["node_title"] == "Topic A"
    assert result["must_cover_checklist"] == [{"id": "c1"}]
    assert checkpoint.await_count == 2
    checkpoint.assert_any_await(
        run_id,
        node_name="resolver",
        state=ANY,
    )
    checkpoint.assert_any_await(
        run_id,
        node_name="concept_checklist",
        state=ANY,
    )


@pytest.mark.asyncio
async def test_invoke_graph_skips_checkpoint_on_node_error() -> None:
    run_id = uuid4()
    session = MagicMock()

    async def fake_astream(
        initial_state: dict[str, Any],
        config: dict[str, Any],
        *,
        stream_mode: str,
    ):
        del initial_state, config, stream_mode
        yield {"resolver": {"error": "Node not found"}}

    graph = MagicMock()
    graph.astream = fake_astream

    checkpoint = AsyncMock()
    on_node = AsyncMock()
    with (
        patch(
            "src.api.core.services.generation_run_service.GenerationRunService"
        ) as service_cls,
        patch(
            "src.api.utils.generation_progress.graph_runner.DbGenerationProgressStore"
        ) as db_store_cls,
    ):
        service_cls.return_value.checkpoint_after_node = checkpoint
        service_cls.return_value.fail_run = AsyncMock()
        db_store_cls.return_value.on_node = on_node

        result = await invoke_graph_with_progress(
            graph,
            {},
            {"configurable": {"session": session}},
            progress_session_id=None,
            pipeline=GenerationPipeline.STUDY_MATERIAL,
            run_id=run_id,
        )

    assert result["error"] == "Node not found"
    checkpoint.assert_not_awaited()
    on_node.assert_awaited_once_with(
        run_id, GenerationPipeline.STUDY_MATERIAL, "resolver"
    )


@pytest.mark.asyncio
async def test_invoke_graph_fail_run_on_exception() -> None:
    run_id = uuid4()
    session = MagicMock()

    async def fake_astream(
        initial_state: dict[str, Any],
        config: dict[str, Any],
        *,
        stream_mode: str,
    ):
        del initial_state, config, stream_mode
        yield {"resolver": {"node_title": "Topic A"}}
        raise RuntimeError("stream crashed")

    graph = MagicMock()
    graph.astream = fake_astream

    fail_run = AsyncMock()
    with patch(
        "src.api.core.services.generation_run_service.GenerationRunService"
    ) as service_cls:
        service_cls.return_value.checkpoint_after_node = AsyncMock()
        service_cls.return_value.fail_run = fail_run

        with pytest.raises(RuntimeError, match="stream crashed"):
            await invoke_graph_with_progress(
                graph,
                {},
                {"configurable": {"session": session}},
                progress_session_id=None,
                pipeline=GenerationPipeline.STUDY_MATERIAL,
                run_id=run_id,
            )

    fail_run.assert_awaited_once()
    kwargs = fail_run.await_args.kwargs
    assert kwargs["error_message"] == "stream crashed"
    assert kwargs["error_type"] == "RuntimeError"
