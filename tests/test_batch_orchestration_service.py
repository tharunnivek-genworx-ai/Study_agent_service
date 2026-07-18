"""Unit tests for BatchOrchestrationService."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.core.services.batch_orchestration_service import BatchOrchestrationService
from src.api.data.models.postgres.generation.batch_jobs import BatchJob, BatchJobStep
from src.api.data.repositories.space_node_repository.node_repository import (
    SubtreePreviewNode,
)
from src.api.schemas.batch_schemas import BatchCreateRequest, BatchPolicyIn
from src.api.schemas.common import GenerationRunStatus
from src.api.schemas.study_material_schemas.study_material_schema import (
    StudyMaterialClearDraftsEligibilityOut,
)


def _make_root(*, node_id=None, title: str = "Root A") -> SimpleNamespace:
    return SimpleNamespace(node_id=node_id or uuid4(), title=title)


def _make_subtree_node(
    *,
    node_id=None,
    title: str = "Topic",
    depth_level: int = 1,
    path_titles: list[str] | None = None,
    has_effective_instruction: bool = True,
    inherits_section_default: bool = False,
) -> SubtreePreviewNode:
    nid = node_id or uuid4()
    return SubtreePreviewNode(
        node=SimpleNamespace(node_id=nid, title=title),
        depth_level=depth_level,
        path_node_ids=[nid],
        path_titles=path_titles or [title],
        effective_instruction="instruction",
        has_effective_instruction=has_effective_instruction,
        inherits_section_default=inherits_section_default,
    )


def _make_batch(
    *,
    batch_id=None,
    space_id=None,
    mentor_id=None,
    status: str = "pending",
    policy: dict | None = None,
    total_steps: int = 0,
    completed_steps: int = 0,
    failed_steps: int = 0,
    skipped_steps: int = 0,
) -> BatchJob:
    now = datetime.now(UTC)
    batch = BatchJob(
        batch_id=batch_id or uuid4(),
        space_id=space_id or uuid4(),
        mentor_id=mentor_id or uuid4(),
        status=status,
        policy=policy or {"mode": "skip_existing"},
        selected_root_node_ids=[],
        total_steps=total_steps,
        completed_steps=completed_steps,
        failed_steps=failed_steps,
        skipped_steps=skipped_steps,
        created_at=now,
        updated_at=now,
    )
    return batch


def _make_step(
    *,
    batch_id,
    position: int,
    node_id=None,
    status: str = "pending",
    step_id=None,
) -> BatchJobStep:
    return BatchJobStep(
        step_id=step_id or uuid4(),
        batch_id=batch_id,
        position=position,
        node_id=node_id or uuid4(),
        node_title=f"Topic {position}",
        path_titles=[f"Topic {position}"],
        depth_level=1,
        root_segment_node_id=uuid4(),
        status=status,
    )


def _result_with_scalars(value):
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    result.scalars.return_value.all.return_value = (
        value if isinstance(value, list) else []
    )
    return result


@pytest.mark.asyncio
async def test_preview_marks_nodes_with_active_runs_as_blocked() -> None:
    space_id = uuid4()
    mentor_id = uuid4()
    root = _make_root()
    node_a = _make_subtree_node(title="A")
    node_b = _make_subtree_node(title="B")

    session = MagicMock()
    session.execute = AsyncMock(return_value=_result_with_scalars([]))
    service = BatchOrchestrationService(session)

    with (
        patch(
            "src.api.core.services.batch_orchestration_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.core.services.batch_orchestration_service.NodeRepository"
        ) as repo_cls,
        patch.object(
            service,
            "_node_ids_with_active_runs",
            new_callable=AsyncMock,
            return_value={node_b.node.node_id},
        ),
    ):
        repo = repo_cls.return_value
        repo.get_space_root_nodes = AsyncMock(return_value=[root])
        repo.get_subtree_nodes_preorder = AsyncMock(return_value=[node_a, node_b])

        preview = await service.preview_generate_all(
            space_id, [root.node_id], mentor_id, "mentor"
        )

    assert len(preview.items) == 2
    by_id = {item.node_id: item for item in preview.items}
    assert by_id[node_a.node.node_id].can_generate is True
    assert by_id[node_b.node.node_id].can_generate is False
    assert "active generation run" in (by_id[node_b.node.node_id].block_reason or "")


@pytest.mark.asyncio
async def test_preview_builds_deep_tree_paths() -> None:
    space_id = uuid4()
    mentor_id = uuid4()
    root = _make_root(title="A")
    nodes = [
        _make_subtree_node(title="A", depth_level=1, path_titles=["A"]),
        _make_subtree_node(title="B", depth_level=2, path_titles=["A", "B"]),
        _make_subtree_node(title="C", depth_level=3, path_titles=["A", "B", "C"]),
        _make_subtree_node(title="D", depth_level=4, path_titles=["A", "B", "C", "D"]),
    ]

    session = MagicMock()
    service = BatchOrchestrationService(session)

    with (
        patch(
            "src.api.core.services.batch_orchestration_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.core.services.batch_orchestration_service.NodeRepository"
        ) as repo_cls,
        patch.object(
            service,
            "_node_ids_with_active_runs",
            new_callable=AsyncMock,
            return_value=set(),
        ),
    ):
        repo = repo_cls.return_value
        repo.get_space_root_nodes = AsyncMock(return_value=[root])
        repo.get_subtree_nodes_preorder = AsyncMock(return_value=nodes)

        preview = await service.preview_generate_all(
            space_id, [root.node_id], mentor_id, "mentor"
        )

    assert [item.title for item in preview.items] == ["A", "B", "C", "D"]
    assert preview.items[-1].path_titles == ["A", "B", "C", "D"]


@pytest.mark.asyncio
async def test_create_batch_inserts_ordered_steps() -> None:
    space_id = uuid4()
    mentor_id = uuid4()
    root = _make_root()
    nodes = [
        _make_subtree_node(title="One"),
        _make_subtree_node(title="Two"),
        _make_subtree_node(title="Three"),
    ]

    session = MagicMock()
    session.add = MagicMock()

    async def _flush_assign_ids() -> None:
        for call in session.add.call_args_list:
            obj = call.args[0]
            if isinstance(obj, BatchJob) and obj.batch_id is None:
                obj.batch_id = uuid4()

    session.flush = AsyncMock(side_effect=_flush_assign_ids)
    service = BatchOrchestrationService(session)

    with (
        patch(
            "src.api.core.services.batch_orchestration_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.core.services.batch_orchestration_service.NodeRepository"
        ) as repo_cls,
    ):
        repo = repo_cls.return_value
        repo.get_space_root_nodes = AsyncMock(return_value=[root])
        repo.get_subtree_nodes_preorder = AsyncMock(return_value=nodes)

        response = await service.create_batch(
            space_id,
            BatchCreateRequest(
                root_node_ids=[root.node_id],
                policy=BatchPolicyIn(mode="skip_existing"),
            ),
            mentor_id,
            "mentor",
        )

    assert response.status == "pending"
    added = [call.args[0] for call in session.add.call_args_list]
    batches = [obj for obj in added if isinstance(obj, BatchJob)]
    steps = [obj for obj in added if isinstance(obj, BatchJobStep)]
    assert len(batches) == 1
    assert batches[0].total_steps == 3
    assert [step.position for step in steps] == [1, 2, 3]
    assert [step.node_title for step in steps] == ["One", "Two", "Three"]


@pytest.mark.asyncio
async def test_create_batch_stores_per_node_external_research_flags() -> None:
    space_id = uuid4()
    mentor_id = uuid4()
    root = _make_root()
    nodes = [
        _make_subtree_node(title="One"),
        _make_subtree_node(title="Two"),
        _make_subtree_node(title="Three"),
    ]
    research_node = nodes[0].node.node_id
    ignored_outside_plan = uuid4()

    session = MagicMock()
    session.add = MagicMock()

    async def _flush_assign_ids() -> None:
        for call in session.add.call_args_list:
            obj = call.args[0]
            if isinstance(obj, BatchJob) and obj.batch_id is None:
                obj.batch_id = uuid4()

    session.flush = AsyncMock(side_effect=_flush_assign_ids)
    service = BatchOrchestrationService(session)

    with (
        patch(
            "src.api.core.services.batch_orchestration_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.core.services.batch_orchestration_service.NodeRepository"
        ) as repo_cls,
    ):
        repo = repo_cls.return_value
        repo.get_space_root_nodes = AsyncMock(return_value=[root])
        repo.get_subtree_nodes_preorder = AsyncMock(return_value=nodes)

        await service.create_batch(
            space_id,
            BatchCreateRequest(
                root_node_ids=[root.node_id],
                node_ids=[nodes[0].node.node_id, nodes[1].node.node_id],
                policy=BatchPolicyIn(mode="skip_existing"),
                external_research_node_ids=[research_node, ignored_outside_plan],
            ),
            mentor_id,
            "mentor",
        )

    batches = [
        call.args[0]
        for call in session.add.call_args_list
        if isinstance(call.args[0], BatchJob)
    ]
    assert len(batches) == 1
    assert batches[0].policy["external_research_node_ids"] == [str(research_node)]


@pytest.mark.asyncio
async def test_claim_next_step_skips_existing_material() -> None:
    batch_id = uuid4()
    batch = _make_batch(batch_id=batch_id, policy={"mode": "skip_existing"})
    step = _make_step(batch_id=batch_id, position=1)

    session = MagicMock()
    session.flush = AsyncMock()
    service = BatchOrchestrationService(session)

    with (
        patch.object(service, "_get_batch", new_callable=AsyncMock, return_value=batch),
        patch.object(
            service, "_has_running_step", new_callable=AsyncMock, return_value=False
        ),
        patch.object(
            service,
            "_next_pending_step_for_batch",
            new_callable=AsyncMock,
            side_effect=[step, None],
        ),
        patch.object(
            service, "_should_skip_step", new_callable=AsyncMock, return_value=True
        ),
        patch.object(
            service, "_maybe_finalize_batch", new_callable=AsyncMock
        ) as finalize_batch,
    ):
        claimed = await service.claim_next_step(batch_id)

    assert claimed is None
    assert step.status == "skipped"
    assert batch.skipped_steps == 1
    finalize_batch.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_next_step_claims_first_pending_step() -> None:
    batch_id = uuid4()
    batch = _make_batch(batch_id=batch_id, status="pending")
    step = _make_step(batch_id=batch_id, position=1)

    session = MagicMock()
    session.flush = AsyncMock()
    service = BatchOrchestrationService(session)

    with (
        patch.object(service, "_get_batch", new_callable=AsyncMock, return_value=batch),
        patch.object(
            service, "_has_running_step", new_callable=AsyncMock, return_value=False
        ),
        patch.object(
            service,
            "_next_pending_step_for_batch",
            new_callable=AsyncMock,
            return_value=step,
        ),
        patch.object(
            service, "_should_skip_step", new_callable=AsyncMock, return_value=False
        ),
    ):
        claimed = await service.claim_next_step(batch_id)

    assert claimed is step
    assert step.status == "running"
    assert batch.status == "running"
    assert batch.started_at is not None


@pytest.mark.asyncio
async def test_claim_next_step_regenerate_all_fails_when_clear_blocked() -> None:
    batch_id = uuid4()
    batch = _make_batch(batch_id=batch_id, policy={"mode": "regenerate_all"})
    step = _make_step(batch_id=batch_id, position=1)

    session = MagicMock()
    session.flush = AsyncMock()
    service = BatchOrchestrationService(session)

    study_material_service = MagicMock()
    study_material_service.get_clear_drafts_eligibility = AsyncMock(
        return_value=StudyMaterialClearDraftsEligibilityOut(
            can_clear=False,
            version_count=1,
            quiz_count=0,
            block_reason="Published quiz blocks clear.",
        )
    )

    with (
        patch.object(service, "_get_batch", new_callable=AsyncMock, return_value=batch),
        patch.object(
            service, "_has_running_step", new_callable=AsyncMock, return_value=False
        ),
        patch.object(
            service,
            "_next_pending_step_for_batch",
            new_callable=AsyncMock,
            side_effect=[step, None],
        ),
        patch.object(
            service, "_should_skip_step", new_callable=AsyncMock, return_value=False
        ),
        patch.object(
            service,
            "_node_has_study_material_version",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "src.api.core.services.batch_orchestration_service.StudyMaterialService",
            return_value=study_material_service,
        ),
        patch.object(service, "_maybe_finalize_batch", new_callable=AsyncMock),
    ):
        claimed = await service.claim_next_step(batch_id)

    assert claimed is None
    assert step.status == "failed"
    assert batch.failed_steps == 1
    assert "Published quiz" in (step.error_message or "")


@pytest.mark.asyncio
async def test_claim_next_step_regenerate_all_skips_clear_when_no_material() -> None:
    """Discarded-only history should not block regenerate-all from claiming."""
    batch_id = uuid4()
    batch = _make_batch(batch_id=batch_id, policy={"mode": "regenerate_all"})
    step = _make_step(batch_id=batch_id, position=1)

    session = MagicMock()
    session.flush = AsyncMock()
    service = BatchOrchestrationService(session)

    study_material_service = MagicMock()
    study_material_service.get_clear_drafts_eligibility = AsyncMock()
    study_material_service.clear_all_drafts = AsyncMock()

    with (
        patch.object(service, "_get_batch", new_callable=AsyncMock, return_value=batch),
        patch.object(
            service, "_has_running_step", new_callable=AsyncMock, return_value=False
        ),
        patch.object(
            service,
            "_next_pending_step_for_batch",
            new_callable=AsyncMock,
            return_value=step,
        ),
        patch.object(
            service, "_should_skip_step", new_callable=AsyncMock, return_value=False
        ),
        patch.object(
            service,
            "_node_has_study_material_version",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "src.api.core.services.batch_orchestration_service.StudyMaterialService",
            return_value=study_material_service,
        ),
    ):
        claimed = await service.claim_next_step(batch_id)

    assert claimed is step
    assert step.status == "running"
    study_material_service.get_clear_drafts_eligibility.assert_not_awaited()
    study_material_service.clear_all_drafts.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalize_step_completed_increments_counter_and_finalizes_batch() -> None:
    batch_id = uuid4()
    step_id = uuid4()
    batch = _make_batch(batch_id=batch_id, status="running", total_steps=1)
    step = _make_step(batch_id=batch_id, position=1, status="running", step_id=step_id)

    session = MagicMock()
    session.get = AsyncMock(return_value=step)
    session.flush = AsyncMock()
    service = BatchOrchestrationService(session)

    with (
        patch.object(service, "_get_batch", new_callable=AsyncMock, return_value=batch),
        patch.object(
            service, "_steps_for_batch", new_callable=AsyncMock, return_value=[step]
        ),
        patch.object(
            service, "_maybe_finalize_batch", new_callable=AsyncMock
        ) as finalize,
    ):
        await service.finalize_step(
            batch_id,
            step_id,
            run_status=GenerationRunStatus.COMPLETED.value,
        )

    assert step.status == "completed"
    assert batch.completed_steps == 1
    finalize.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_batch_abandons_running_and_skips_pending_steps() -> None:
    batch_id = uuid4()
    mentor_id = uuid4()
    batch = _make_batch(batch_id=batch_id, mentor_id=mentor_id, status="running")
    step = _make_step(batch_id=batch_id, position=1, status="running")
    step.generation_run_id = uuid4()
    pending_step = _make_step(batch_id=batch_id, position=2, status="pending")

    session = MagicMock()
    session.flush = AsyncMock()
    service = BatchOrchestrationService(session)

    abandon_run = AsyncMock()
    with (
        patch.object(service, "_get_batch", new_callable=AsyncMock, return_value=batch),
        patch.object(
            service,
            "_steps_for_batch",
            new_callable=AsyncMock,
            return_value=[step, pending_step],
        ),
        patch(
            "src.api.core.services.batch_orchestration_service._assert_space_access",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.core.services.batch_orchestration_service.GenerationRunService"
        ) as run_service_cls,
    ):
        run_service_cls.return_value.abandon_run = abandon_run
        response = await service.cancel_batch(batch_id, mentor_id, "mentor")

    assert response.status == "cancelled"
    assert batch.status == "cancelled"
    assert step.status == "failed"
    assert pending_step.status == "skipped"
    assert pending_step.completed_at is not None
    assert batch.failed_steps == 1
    assert batch.skipped_steps == 1
    abandon_run.assert_awaited_once_with(
        step.generation_run_id,
        mentor_id=mentor_id,
        reason="batch_cancelled",
    )


@pytest.mark.asyncio
async def test_cancel_batch_is_idempotent_for_terminal_batch() -> None:
    batch_id = uuid4()
    batch = _make_batch(batch_id=batch_id, status="completed")

    session = MagicMock()
    service = BatchOrchestrationService(session)

    with (
        patch.object(service, "_get_batch", new_callable=AsyncMock, return_value=batch),
        patch(
            "src.api.core.services.batch_orchestration_service._assert_space_access",
            new_callable=AsyncMock,
        ),
    ):
        response = await service.cancel_batch(batch_id, uuid4(), "mentor")

    assert response.status == "completed"


def test_maybe_finalize_batch_marks_completed_when_no_pending_steps() -> None:
    async def _run() -> None:
        batch = _make_batch(status="running")
        completed_step = _make_step(
            batch_id=batch.batch_id, position=1, status="completed"
        )

        session = MagicMock()
        session.flush = AsyncMock()
        service = BatchOrchestrationService(session)

        with patch.object(
            service,
            "_steps_for_batch",
            new_callable=AsyncMock,
            return_value=[completed_step],
        ):
            await service._maybe_finalize_batch(batch)

        assert batch.status == "completed"
        assert batch.finished_at is not None

    asyncio.run(_run())
