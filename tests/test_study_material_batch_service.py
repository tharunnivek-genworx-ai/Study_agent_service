from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.api.core.exceptions import GenerationRunConflictException
from src.api.core.services.study_agent_services.study_material_batch_service import (
    StudyMaterialBatchService,
)
from src.api.data.models.postgres.generation.study_material_batches import (
    StudyMaterialBatchRun,
)
from src.api.data.repositories.space_node_repository.node_repository import (
    SubtreePreviewNode,
)
from src.api.schemas.common import GenerationRunStatus
from src.api.schemas.study_material_schemas.batch_schema import (
    StudyMaterialBatchEnqueueRequest,
    StudyMaterialSpaceQueueOut,
)


def _result_with_scalars(rows):
    class _Scalars:
        def __init__(self, vals):
            self._vals = vals

        def all(self):
            return list(self._vals)

    class _Result:
        def __init__(self, vals):
            self._vals = vals

        def scalars(self):
            return _Scalars(self._vals)

    return _Result(rows)


@pytest.mark.asyncio
async def test_advance_returns_deferred_when_space_lock_unavailable() -> None:
    session = AsyncMock()
    service = StudyMaterialBatchService(session)
    deferred_snapshot = StudyMaterialSpaceQueueOut(advance_deferred=True)

    with (
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.try_acquire_generation_xact_lock",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        with (
            patch.object(
                service,
                "reconcile_space_queue",
                AsyncMock(),
            ),
            patch.object(
                service,
                "_build_queue_snapshot",
                AsyncMock(return_value=deferred_snapshot),
            ),
        ):
            result = await service.advance_space_queue(
                space_id=uuid4(),
                mentor_id=uuid4(),
                role="mentor",
            )

    assert result.snapshot.advance_deferred is True
    assert result.scheduled_run_id is None


@pytest.mark.asyncio
async def test_advance_requeues_conflicted_item() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    service = StudyMaterialBatchService(session)
    space_id = uuid4()
    mentor_id = uuid4()

    batch = SimpleNamespace(
        batch_id=uuid4(),
        policy={"existing_material_policy": "regenerate"},
        skipped_items=0,
        current_item_id=None,
        status="running",
    )
    first_item = SimpleNamespace(
        item_id=uuid4(),
        node_id=uuid4(),
        status="queued",
        error_message=None,
        generation_run_id=None,
    )
    deferred_snapshot = StudyMaterialSpaceQueueOut(advance_deferred=True)

    with (
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.try_acquire_generation_xact_lock",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.object(service, "reconcile_space_queue", AsyncMock()),
        patch.object(service, "_has_running_item", AsyncMock(return_value=False)),
        patch.object(service, "_get_running_batch", AsyncMock(return_value=batch)),
        patch.object(
            service, "_next_queued_item_for_batch", AsyncMock(return_value=first_item)
        ),
        patch.object(service, "_should_skip_item", AsyncMock(return_value=False)),
        patch.object(
            service, "_build_queue_snapshot", AsyncMock(return_value=deferred_snapshot)
        ),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.StudyMaterialService"
        ) as service_cls,
    ):
        service_instance = service_cls.return_value
        service_instance.start_generate_study_material = AsyncMock(
            side_effect=GenerationRunConflictException()
        )
        result = await service.advance_space_queue(
            space_id=space_id,
            mentor_id=mentor_id,
            role="mentor",
        )

    assert first_item.status == "queued"
    assert result.scheduled_run_id is None
    assert result.snapshot.advance_deferred is True
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_advance_marks_item_failed_on_unexpected_start_error() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    service = StudyMaterialBatchService(session)
    space_id = uuid4()
    mentor_id = uuid4()

    batch = SimpleNamespace(
        batch_id=uuid4(),
        policy={"existing_material_policy": "regenerate"},
        skipped_items=0,
        failed_items=0,
        current_item_id=None,
        status="running",
    )
    item = SimpleNamespace(
        item_id=uuid4(),
        node_id=uuid4(),
        status="queued",
        error_message=None,
        generation_run_id=None,
    )

    with (
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch.object(service, "reconcile_space_queue", AsyncMock()),
        patch.object(
            service,
            "_claim_next_item_under_lock",
            AsyncMock(side_effect=[(item, batch), None]),
        ),
        patch.object(
            service,
            "_build_queue_snapshot",
            AsyncMock(return_value=StudyMaterialSpaceQueueOut()),
        ),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.StudyMaterialService"
        ) as service_cls,
    ):
        service_instance = service_cls.return_value
        service_instance.start_generate_study_material = AsyncMock(
            side_effect=RuntimeError("start failed")
        )
        result = await service.advance_space_queue(
            space_id=space_id,
            mentor_id=mentor_id,
            role="mentor",
        )

    assert result.scheduled_run_id is None
    assert item.status == "failed"
    assert "start failed" in (item.error_message or "")
    assert batch.failed_items == 1
    assert batch.current_item_id is None


@pytest.mark.asyncio
async def test_reconcile_marks_failed_retryable_when_retry_timestamp_exists() -> None:
    session = AsyncMock()
    service = StudyMaterialBatchService(session)
    now = datetime.now(UTC)
    batch_id = uuid4()
    run_id = uuid4()

    running_item = SimpleNamespace(
        batch_id=batch_id,
        generation_run_id=run_id,
        status="running",
        error_message=None,
    )
    batch = SimpleNamespace(
        batch_id=batch_id,
        completed_items=0,
        failed_items=0,
        skipped_items=0,
        total_items=3,
        current_item_id=uuid4(),
        status="running",
    )
    run = SimpleNamespace(
        run_id=run_id,
        status=GenerationRunStatus.FAILED.value,
        next_llm_retry_at=now,
        error_message="Groq pool exhausted",
    )

    session.execute = AsyncMock(
        side_effect=[
            _result_with_scalars([]),  # orphan reset
            _result_with_scalars([running_item]),
            _result_with_scalars([run]),
            _result_with_scalars([batch]),
        ]
    )
    with patch.object(
        service, "_items_for_batch", AsyncMock(return_value=[running_item])
    ):
        await service.reconcile_space_queue(uuid4())

    assert running_item.status == "failed_retryable"
    assert running_item.error_message == "Groq pool exhausted"
    assert batch.failed_items == 1
    assert batch.current_item_id is None


def _preview_node(
    *,
    node_id,
    title: str,
    depth: int,
    path_ids,
    path_titles,
) -> SubtreePreviewNode:
    return SubtreePreviewNode(
        node=SimpleNamespace(node_id=node_id, title=title),
        depth_level=depth,
        path_node_ids=path_ids,
        path_titles=path_titles,
        effective_instruction="",
        has_effective_instruction=False,
        inherits_section_default=False,
    )


@pytest.mark.asyncio
async def test_preview_builds_deep_tree_paths_for_a_to_b_to_c_to_d() -> None:
    session = AsyncMock()
    service = StudyMaterialBatchService(session)
    space_id = uuid4()
    mentor_id = uuid4()
    root_id, b_id, c_id, d_id = uuid4(), uuid4(), uuid4(), uuid4()
    root = SimpleNamespace(node_id=root_id, title="A")
    subtree = [
        _preview_node(
            node_id=root_id,
            title="A",
            depth=1,
            path_ids=[root_id],
            path_titles=["A"],
        ),
        _preview_node(
            node_id=b_id,
            title="B",
            depth=2,
            path_ids=[root_id, b_id],
            path_titles=["A", "B"],
        ),
        _preview_node(
            node_id=c_id,
            title="C",
            depth=3,
            path_ids=[root_id, b_id, c_id],
            path_titles=["A", "B", "C"],
        ),
        _preview_node(
            node_id=d_id,
            title="D",
            depth=4,
            path_ids=[root_id, b_id, c_id, d_id],
            path_titles=["A", "B", "C", "D"],
        ),
    ]

    with (
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch.object(
            service, "_resolve_roots", AsyncMock(return_value=([root], {root_id: "A"}))
        ),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.NodeRepository"
        ) as node_repo_cls,
    ):
        node_repo_cls.return_value.get_subtree_nodes_preorder = AsyncMock(
            return_value=subtree
        )
        preview = await service.preview_generate_all(
            space_id=space_id,
            root_node_ids=[root_id],
            mentor_id=mentor_id,
            role="mentor",
        )

    assert [item.title for item in preview.items] == ["A", "B", "C", "D"]
    assert [item.depth_level for item in preview.items] == [1, 2, 3, 4]
    assert preview.items[-1].path_titles == ["A", "B", "C", "D"]
    assert preview.items[-1].root_segment_node_id == root_id


@pytest.mark.asyncio
async def test_enqueue_sets_fifo_status_running_then_queued() -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.scalar = AsyncMock(side_effect=[None, None, 1, uuid4()])
    session.add = Mock()
    service = StudyMaterialBatchService(session)
    space_id = uuid4()
    mentor_id = uuid4()
    root_id = uuid4()
    root = SimpleNamespace(node_id=root_id, title="Root")
    subtree = [
        _preview_node(
            node_id=root_id,
            title="Root",
            depth=1,
            path_ids=[root_id],
            path_titles=["Root"],
        )
    ]
    payload = StudyMaterialBatchEnqueueRequest(root_node_ids=[root_id])
    queue_snapshot = StudyMaterialSpaceQueueOut()

    with (
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch.object(service, "_require_space_xact_lock", AsyncMock()),
        patch.object(
            service,
            "_resolve_roots",
            AsyncMock(return_value=([root], {root_id: "Root"})),
        ),
        patch.object(
            service, "_build_queue_snapshot", AsyncMock(return_value=queue_snapshot)
        ),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.NodeRepository"
        ) as node_repo_cls,
    ):
        node_repo_cls.return_value.get_subtree_nodes_preorder = AsyncMock(
            return_value=subtree
        )
        await service.enqueue_batch(space_id, payload, mentor_id, "mentor")
        await service.enqueue_batch(space_id, payload, mentor_id, "mentor")

    created_batches = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], StudyMaterialBatchRun)
    ]
    assert len(created_batches) == 2
    assert created_batches[0].status == "running"
    assert created_batches[0].queue_position == 1
    assert created_batches[1].status == "queued"
    assert created_batches[1].queue_position == 2


@pytest.mark.asyncio
async def test_advance_starts_only_one_run_per_call() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    service = StudyMaterialBatchService(session)
    space_id = uuid4()
    mentor_id = uuid4()
    run_id = uuid4()

    batch = SimpleNamespace(
        batch_id=uuid4(),
        policy={"existing_material_policy": "regenerate"},
        skipped_items=0,
        current_item_id=None,
        status="running",
    )
    first_item = SimpleNamespace(
        item_id=uuid4(),
        node_id=uuid4(),
        status="queued",
        error_message=None,
        generation_run_id=None,
    )
    second_item = SimpleNamespace(
        item_id=uuid4(),
        node_id=uuid4(),
        status="queued",
        error_message=None,
        generation_run_id=None,
    )

    with (
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.try_acquire_generation_xact_lock",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.object(service, "reconcile_space_queue", AsyncMock()),
        patch.object(service, "_has_running_item", AsyncMock(return_value=False)),
        patch.object(service, "_get_running_batch", AsyncMock(return_value=batch)),
        patch.object(
            service,
            "_next_queued_item_for_batch",
            AsyncMock(side_effect=[first_item, second_item]),
        ) as next_item_mock,
        patch.object(service, "_should_skip_item", AsyncMock(return_value=False)),
        patch.object(
            service,
            "_build_queue_snapshot",
            AsyncMock(return_value=StudyMaterialSpaceQueueOut()),
        ),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.StudyMaterialService"
        ) as service_cls,
    ):
        service_instance = service_cls.return_value
        service_instance.start_generate_study_material = AsyncMock(return_value=run_id)
        result = await service.advance_space_queue(space_id, mentor_id, "mentor")

    assert result.scheduled_run_id == run_id
    assert first_item.status == "running"
    assert second_item.status == "queued"
    assert next_item_mock.await_count == 1
    assert service_cls.return_value.start_generate_study_material.await_count == 1
    assert session.commit.await_count == 1


@pytest.mark.asyncio
async def test_reconcile_marks_completed_and_sets_version_id() -> None:
    session = AsyncMock()
    service = StudyMaterialBatchService(session)
    batch_id = uuid4()
    run_id = uuid4()
    version_id = uuid4()

    running_item = SimpleNamespace(
        batch_id=batch_id,
        node_id=uuid4(),
        generation_run_id=run_id,
        status="running",
        version_id=None,
        completed_at=None,
    )
    batch = SimpleNamespace(
        batch_id=batch_id,
        completed_items=0,
        failed_items=0,
        skipped_items=0,
        total_items=1,
        current_item_id=uuid4(),
        status="running",
    )
    run = SimpleNamespace(
        run_id=run_id,
        status=GenerationRunStatus.COMPLETED.value,
        next_llm_retry_at=None,
        error_message=None,
    )

    session.execute = AsyncMock(
        side_effect=[
            _result_with_scalars([]),  # orphan reset
            _result_with_scalars([running_item]),
            _result_with_scalars([run]),
            _result_with_scalars([batch]),
        ]
    )

    with patch.object(
        service, "_resolve_latest_version_id", AsyncMock(return_value=version_id)
    ):
        with patch.object(
            service, "_items_for_batch", AsyncMock(return_value=[running_item])
        ):
            await service.reconcile_space_queue(uuid4())

    assert running_item.status == "completed"
    assert running_item.version_id == version_id
    assert batch.completed_items == 1
    assert batch.current_item_id is None
    assert batch.status == "completed"


@pytest.mark.asyncio
async def test_cancel_marks_running_item_without_run_id_cancelled() -> None:
    session = AsyncMock()
    service = StudyMaterialBatchService(session)
    batch_id = uuid4()
    space_id = uuid4()
    mentor_id = uuid4()
    now = datetime.now(UTC)

    batch = SimpleNamespace(
        batch_id=batch_id,
        space_id=space_id,
        status="running",
        current_item_id=uuid4(),
        failed_items=0,
    )
    item = SimpleNamespace(
        item_id=uuid4(),
        status="running",
        generation_run_id=None,
        error_message=None,
        completed_at=None,
    )

    with (
        patch.object(service, "_get_batch", AsyncMock(return_value=batch)),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch.object(service, "_require_space_xact_lock", AsyncMock()),
        patch.object(service, "_items_for_batch", AsyncMock(return_value=[item])),
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.utc_now",
            return_value=now,
        ),
    ):
        result, cancelled_space_id = await service.cancel_batch(
            batch_id, mentor_id, "mentor"
        )

    assert result.status == "cancelled"
    assert cancelled_space_id == space_id
    assert batch.status == "cancelled"
    assert batch.current_item_id is None
    assert batch.failed_items == 1
    assert item.status == "cancelled"
    assert item.error_message == "Cancelled by mentor."
    assert item.completed_at == now


@pytest.mark.asyncio
async def test_claim_defers_when_queued_items_are_row_locked() -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    service = StudyMaterialBatchService(session)
    space_id = uuid4()

    batch = SimpleNamespace(
        batch_id=uuid4(),
        status="running",
        current_item_id=None,
        skipped_items=0,
    )

    with (
        patch(
            "src.api.core.services.study_agent_services.study_material_batch_service.try_acquire_generation_xact_lock",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch.object(service, "reconcile_space_queue", AsyncMock()),
        patch.object(service, "_get_running_batch", AsyncMock(return_value=batch)),
        patch.object(service, "_has_running_item", AsyncMock(return_value=False)),
        patch.object(
            service, "_next_queued_item_for_batch", AsyncMock(return_value=None)
        ),
        patch.object(service, "_has_queued_items", AsyncMock(return_value=True)),
    ):
        claimed = await service._claim_next_item_under_lock(space_id)

    assert claimed is False
    assert batch.status == "running"
