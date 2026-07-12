"""Batch job orchestration for durable generate-all (preview, create, claim, finalize)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import (
    GenerationRunNotCancellableException,
    GenerationRunNotFoundException,
)
from src.api.core.services.generation_run_service import GenerationRunService
from src.api.core.services.study_agent_services.study_material_service import (
    StudyMaterialService,
)
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.data.models.postgres.generation.batch_jobs import BatchJob, BatchJobStep
from src.api.data.models.postgres.generation.generation_runs import GenerationRun
from src.api.data.repositories.space_node_repository.node_repository import (
    NodeRepository,
    SubtreePreviewNode,
)
from src.api.schemas.batch_schemas import (
    BatchCancelResponse,
    BatchCreateRequest,
    BatchCreateResponse,
    BatchDetailOut,
    BatchJobOut,
    BatchPolicyIn,
    BatchPreviewItemOut,
    BatchPreviewResponse,
    BatchPreviewWarningsOut,
    BatchRootOut,
    BatchStepOut,
    BatchWarningNodeOut,
)
from src.api.schemas.common import GenerationRunStatus
from src.api.utils.common_utils import utc_now
from src.api.utils.content_lifecycle.visibility import exclude_discarded
from src.api.utils.space_node_utils.node_role_assert import _assert_space_access

_TERMINAL_BATCH_STATUSES = frozenset({"completed", "failed", "cancelled"})
_ACTIVE_BATCH_STATUSES = frozenset({"pending", "running"})


class BatchOrchestrationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def preview_generate_all(
        self,
        space_id: UUID,
        root_node_ids: list[UUID],
        mentor_id: UUID,
        role: str,
        *,
        node_ids: list[UUID] | None = None,
    ) -> BatchPreviewResponse:
        await _assert_space_access(self.session, space_id, mentor_id, role)
        plan_items, root_nodes = await self._build_plan_items(
            space_id,
            root_node_ids=root_node_ids,
            node_ids=node_ids or [],
        )
        items: list[BatchPreviewItemOut] = []
        missing_instruction_nodes: list[BatchWarningNodeOut] = []
        inherits_section_default_nodes: list[BatchWarningNodeOut] = []
        preview_node_ids: list[UUID] = []

        root_title_by_id = {root.node_id: root.title for root in root_nodes}
        for node_data, root_node_id in plan_items:
            preview_node_ids.append(node_data.node.node_id)
            items.append(
                self._preview_item_from_subtree_node(
                    node_data=node_data,
                    root_node_id=root_node_id,
                    root_title=root_title_by_id[root_node_id],
                )
            )
            if not node_data.has_effective_instruction:
                missing_instruction_nodes.append(
                    BatchWarningNodeOut(
                        node_id=node_data.node.node_id,
                        title=node_data.node.title,
                        path_titles=list(node_data.path_titles),
                    )
                )
            if node_data.inherits_section_default:
                inherits_section_default_nodes.append(
                    BatchWarningNodeOut(
                        node_id=node_data.node.node_id,
                        title=node_data.node.title,
                        path_titles=list(node_data.path_titles),
                    )
                )

        active_run_node_ids = await self._node_ids_with_active_runs(preview_node_ids)
        enriched_items = [
            item.model_copy(
                update={
                    "can_generate": item.node_id not in active_run_node_ids,
                    "block_reason": (
                        "This topic already has an active generation run."
                        if item.node_id in active_run_node_ids
                        else None
                    ),
                }
            )
            for item in items
        ]

        return BatchPreviewResponse(
            roots=[
                BatchRootOut(node_id=root.node_id, title=root.title)
                for root in root_nodes
            ],
            items=enriched_items,
            warnings=BatchPreviewWarningsOut(
                missing_instruction_nodes=missing_instruction_nodes,
                inherits_section_default_nodes=inherits_section_default_nodes,
                show_no_instruction_warning=bool(missing_instruction_nodes),
                show_inheritance_warning=bool(inherits_section_default_nodes),
            ),
        )

    async def create_batch(
        self,
        space_id: UUID,
        payload: BatchCreateRequest,
        mentor_id: UUID,
        role: str,
    ) -> BatchCreateResponse:
        await _assert_space_access(self.session, space_id, mentor_id, role)
        plan_items, root_nodes = await self._build_plan_items(
            space_id,
            root_node_ids=payload.root_node_ids,
            node_ids=payload.node_ids,
        )
        if not plan_items:
            raise ValueError("No topics selected for generation.")

        involved_root_ids = sorted({root_id for _, root_id in plan_items})
        batch = BatchJob(
            space_id=space_id,
            mentor_id=mentor_id,
            status="pending",
            selected_root_node_ids=[str(root_id) for root_id in involved_root_ids],
            policy=payload.policy.model_dump(mode="json"),
            total_steps=len(plan_items),
        )
        self.session.add(batch)
        await self.session.flush()

        for idx, (node_data, root_node_id) in enumerate(plan_items, start=1):
            self.session.add(
                BatchJobStep(
                    batch_id=batch.batch_id,
                    node_id=node_data.node.node_id,
                    root_segment_node_id=root_node_id,
                    position=idx,
                    depth_level=node_data.depth_level,
                    path_titles=list(node_data.path_titles),
                    node_title=node_data.node.title,
                    status="pending",
                )
            )

        await self.session.flush()
        return BatchCreateResponse(batch_id=batch.batch_id, status=batch.status)

    async def get_batch_detail(
        self, batch_id: UUID, mentor_id: UUID, role: str
    ) -> BatchDetailOut:
        batch = await self._get_batch(batch_id)
        if batch is None:
            raise ValueError("Batch not found")
        await _assert_space_access(self.session, batch.space_id, mentor_id, role)
        steps = await self._steps_for_batch(batch_id)
        run_status_by_id = await self._run_status_by_id_for_steps(steps)
        return BatchDetailOut(
            batch=self._batch_to_out(batch),
            steps=[
                self._step_to_out(
                    step,
                    run_status=run_status_by_id.get(step.generation_run_id),
                )
                for step in steps
            ],
        )

    async def get_active_batch_for_space(
        self, space_id: UUID, mentor_id: UUID, role: str
    ) -> BatchDetailOut | None:
        await _assert_space_access(self.session, space_id, mentor_id, role)
        result = await self.session.execute(
            select(BatchJob)
            .where(
                BatchJob.space_id == space_id,
                BatchJob.status.in_(sorted(_ACTIVE_BATCH_STATUSES)),
            )
            .order_by(BatchJob.created_at.desc())
            .limit(1)
        )
        batch = cast(BatchJob | None, result.scalars().first())
        if batch is None:
            return None
        steps = await self._steps_for_batch(batch.batch_id)
        run_status_by_id = await self._run_status_by_id_for_steps(steps)
        return BatchDetailOut(
            batch=self._batch_to_out(batch),
            steps=[
                self._step_to_out(
                    step,
                    run_status=run_status_by_id.get(step.generation_run_id),
                )
                for step in steps
            ],
        )

    async def cancel_batch(
        self,
        batch_id: UUID,
        mentor_id: UUID,
        role: str,
    ) -> BatchCancelResponse:
        batch = await self._get_batch(batch_id)
        if batch is None:
            raise ValueError("Batch not found")
        await _assert_space_access(self.session, batch.space_id, mentor_id, role)
        if batch.status in _TERMINAL_BATCH_STATUSES:
            return BatchCancelResponse(batch_id=batch.batch_id, status=batch.status)

        now = utc_now()
        batch.status = "cancelled"
        batch.finished_at = now
        batch.updated_at = now

        steps = await self._steps_for_batch(batch_id)
        for step in steps:
            if step.status == "running":
                if step.generation_run_id is not None:
                    try:
                        await GenerationRunService(self.session).cancel_run(
                            step.generation_run_id,
                            mentor_id=mentor_id,
                        )
                    except (
                        GenerationRunNotFoundException,
                        GenerationRunNotCancellableException,
                    ):
                        pass
                step.status = "failed"
                step.error_message = "Cancelled by mentor."
                step.completed_at = now
                batch.failed_steps += 1

        await self.session.flush()
        return BatchCancelResponse(batch_id=batch.batch_id, status="cancelled")

    async def claim_next_step(self, batch_id: UUID) -> BatchJobStep | None:
        batch = await self._get_batch(batch_id)
        if batch is None or batch.status in _TERMINAL_BATCH_STATUSES:
            return None

        if await self._has_running_step(batch_id):
            return None

        if batch.status == "pending":
            batch.status = "running"
            batch.started_at = utc_now()
            batch.updated_at = utc_now()

        study_material_service = StudyMaterialService(self.session)

        while True:
            step = await self._next_pending_step_for_batch(batch_id)
            if step is None:
                await self._maybe_finalize_batch(batch)
                return None

            if await self._should_skip_step(batch, step):
                step.status = "skipped"
                step.completed_at = utc_now()
                batch.skipped_steps += 1
                batch.updated_at = utc_now()
                await self.session.flush()
                continue

            policy_mode = self._policy_mode(batch.policy)
            if policy_mode == "regenerate_all":
                has_version = await self._node_has_study_material_version(step.node_id)
                if has_version:
                    eligibility = (
                        await study_material_service.get_clear_drafts_eligibility(
                            step.node_id,
                            batch.mentor_id,
                            "mentor",
                        )
                    )
                    if not eligibility.can_clear:
                        step.status = "failed"
                        step.error_message = (
                            eligibility.block_reason
                            or "Cannot regenerate — clear drafts blocked."
                        )
                        step.completed_at = utc_now()
                        batch.failed_steps += 1
                        batch.updated_at = utc_now()
                        await self.session.flush()
                        continue
                    await study_material_service.clear_all_drafts(
                        step.node_id,
                        batch.mentor_id,
                        "mentor",
                    )

            now = utc_now()
            step.status = "running"
            step.started_at = now
            step.error_message = None
            batch.updated_at = now
            await self.session.flush()
            return step

    async def finalize_step(
        self,
        batch_id: UUID,
        step_id: UUID,
        *,
        run_status: str,
        error_message: str | None = None,
    ) -> None:
        batch = await self._get_batch(batch_id)
        if batch is None:
            raise ValueError("Batch not found")

        step = await self.session.get(BatchJobStep, step_id)
        if step is None or step.batch_id != batch_id:
            raise ValueError("Batch step not found")
        if step.status != "running":
            return

        now = utc_now()
        if run_status == GenerationRunStatus.COMPLETED.value:
            step.status = "completed"
            batch.completed_steps += 1
        elif run_status == GenerationRunStatus.CANCELLED.value:
            step.status = "failed"
            step.error_message = error_message or "Cancelled."
            batch.failed_steps += 1
        else:
            step.status = "failed"
            step.error_message = error_message or "Generation failed."
            batch.failed_steps += 1

        step.completed_at = now
        batch.updated_at = now
        await self.session.flush()
        await self._maybe_finalize_batch(batch)

    async def attach_generation_run(
        self, step_id: UUID, generation_run_id: UUID
    ) -> None:
        step = await self.session.get(BatchJobStep, step_id)
        if step is None:
            raise ValueError("Batch step not found")
        step.generation_run_id = generation_run_id
        await self.session.flush()

    async def _maybe_finalize_batch(self, batch: BatchJob) -> None:
        if batch.status in _TERMINAL_BATCH_STATUSES:
            return

        steps = await self._steps_for_batch(batch.batch_id)
        if any(step.status in {"pending", "running"} for step in steps):
            return

        batch.status = "completed"
        batch.finished_at = utc_now()
        batch.updated_at = utc_now()
        await self.session.flush()

    async def _resolve_roots(
        self, space_id: UUID, root_node_ids: list[UUID]
    ) -> tuple[list, dict[UUID, str]]:
        roots = await NodeRepository(self.session).get_space_root_nodes(space_id)
        root_by_id = {root.node_id: root for root in roots}
        if root_node_ids:
            selected = [
                root_by_id[root_id]
                for root_id in root_node_ids
                if root_id in root_by_id
            ]
        else:
            selected = roots
        return selected, {root.node_id: root.title for root in selected}

    async def _build_plan_items(
        self,
        space_id: UUID,
        *,
        root_node_ids: list[UUID],
        node_ids: list[UUID],
    ) -> tuple[list[tuple[SubtreePreviewNode, UUID]], list]:
        """Return preorder plan items and the root nodes they span."""
        root_nodes, _ = await self._resolve_roots(space_id, root_node_ids)
        selected_ids = {node_id for node_id in node_ids} if node_ids else None
        repo = NodeRepository(self.session)
        plan_items: list[tuple[SubtreePreviewNode, UUID]] = []

        for root in root_nodes:
            subtree = await repo.get_subtree_nodes_preorder(root.node_id)
            for node_data in subtree:
                if (
                    selected_ids is not None
                    and node_data.node.node_id not in selected_ids
                ):
                    continue
                plan_items.append((node_data, root.node_id))

        if selected_ids is not None:
            planned_ids = {item.node.node_id for item, _ in plan_items}
            unknown = selected_ids - planned_ids
            if unknown:
                raise ValueError("One or more selected topics are not in this space.")

        involved_root_ids = {root_id for _, root_id in plan_items}
        involved_roots = [
            root for root in root_nodes if root.node_id in involved_root_ids
        ]
        return plan_items, involved_roots

    def _preview_item_from_subtree_node(
        self,
        *,
        node_data: SubtreePreviewNode,
        root_node_id: UUID,
        root_title: str,
    ) -> BatchPreviewItemOut:
        return BatchPreviewItemOut(
            node_id=node_data.node.node_id,
            title=node_data.node.title,
            depth_level=node_data.depth_level,
            path_node_ids=node_data.path_node_ids,
            path_titles=node_data.path_titles,
            root_segment_node_id=root_node_id,
            root_segment_title=root_title,
        )

    async def _should_skip_step(self, batch: BatchJob, step: BatchJobStep) -> bool:
        if self._policy_mode(batch.policy) != "skip_existing":
            return False
        return await self._node_has_study_material_version(step.node_id)

    async def _node_has_study_material_version(self, node_id: UUID) -> bool:
        """True when the node has non-discarded study material (matches repo reads)."""
        return bool(
            await self.session.scalar(
                select(StudyMaterialVersion.version_id)
                .where(
                    StudyMaterialVersion.node_id == node_id,
                    exclude_discarded(StudyMaterialVersion.lifecycle_status),
                )
                .limit(1)
            )
        )

    async def _node_ids_with_active_runs(self, node_ids: list[UUID]) -> set[UUID]:
        if not node_ids:
            return set()
        rows = (
            await self.session.execute(
                select(GenerationRun.node_id).where(
                    GenerationRun.node_id.in_(node_ids),
                    GenerationRun.status == GenerationRunStatus.RUNNING.value,
                )
            )
        ).all()
        return {row[0] for row in rows}

    def _policy_mode(self, policy: dict | None) -> str:
        return str((policy or {}).get("mode", "skip_existing"))

    async def _has_running_step(self, batch_id: UUID) -> bool:
        value = await self.session.scalar(
            select(func.count())
            .select_from(BatchJobStep)
            .where(
                BatchJobStep.batch_id == batch_id,
                BatchJobStep.status == "running",
            )
        )
        return bool(value and value > 0)

    async def _next_pending_step_for_batch(self, batch_id: UUID) -> BatchJobStep | None:
        result = await self.session.execute(
            select(BatchJobStep)
            .where(
                BatchJobStep.batch_id == batch_id,
                BatchJobStep.status == "pending",
            )
            .order_by(BatchJobStep.position.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return cast(BatchJobStep | None, result.scalars().first())

    async def _get_batch(self, batch_id: UUID) -> BatchJob | None:
        return cast(BatchJob | None, await self.session.get(BatchJob, batch_id))

    async def _steps_for_batch(self, batch_id: UUID) -> list[BatchJobStep]:
        return list(
            (
                await self.session.execute(
                    select(BatchJobStep)
                    .where(BatchJobStep.batch_id == batch_id)
                    .order_by(BatchJobStep.position.asc())
                )
            )
            .scalars()
            .all()
        )

    async def _run_status_by_id_for_steps(
        self, steps: list[BatchJobStep]
    ) -> dict[UUID, str]:
        run_ids = [step.generation_run_id for step in steps if step.generation_run_id]
        if not run_ids:
            return {}
        rows = (
            await self.session.execute(
                select(GenerationRun.run_id, GenerationRun.status).where(
                    GenerationRun.run_id.in_(run_ids)
                )
            )
        ).all()
        return {run_id: status for run_id, status in rows}

    def _batch_to_out(self, batch: BatchJob) -> BatchJobOut:
        selected_ids: list[Any] = (
            batch.selected_root_node_ids
            if isinstance(batch.selected_root_node_ids, list)
            else []
        )
        policy_raw: dict[str, Any] = (
            batch.policy if isinstance(batch.policy, dict) else {}
        )
        return BatchJobOut(
            batch_id=batch.batch_id,
            space_id=batch.space_id,
            mentor_id=batch.mentor_id,
            status=batch.status,
            policy=BatchPolicyIn.model_validate(policy_raw),
            selected_root_node_ids=[UUID(str(x)) for x in selected_ids],
            total_steps=batch.total_steps,
            completed_steps=batch.completed_steps,
            failed_steps=batch.failed_steps,
            skipped_steps=batch.skipped_steps,
            created_at=batch.created_at,
            updated_at=batch.updated_at,
            started_at=batch.started_at,
            finished_at=batch.finished_at,
        )

    def _step_to_out(
        self, step: BatchJobStep, *, run_status: str | None = None
    ) -> BatchStepOut:
        path_titles: list[Any] = (
            step.path_titles if isinstance(step.path_titles, list) else []
        )
        return BatchStepOut(
            step_id=step.step_id,
            batch_id=step.batch_id,
            position=step.position,
            node_id=step.node_id,
            node_title=step.node_title,
            path_titles=[str(title) for title in path_titles],
            depth_level=step.depth_level,
            root_segment_node_id=step.root_segment_node_id,
            status=step.status,
            generation_run_id=step.generation_run_id,
            run_status=run_status,
            error_message=step.error_message,
            started_at=step.started_at,
            completed_at=step.completed_at,
        )
