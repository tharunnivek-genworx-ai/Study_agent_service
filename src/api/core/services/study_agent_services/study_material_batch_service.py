"""Space-level batch queue coordinator for study-material generation.

Design goals:
- Keep queue mutations short and lock-bounded (milliseconds).
- Start at most one new generation run per `advance` call.
- Reuse existing single-item async generation path.
- Reconcile durable `generationruns` back into queue item state.

This service intentionally does not execute the graph itself. It only plans,
queues, reconciles, and decides the next item to start.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import (
    GenerationAdvisoryLockUnavailableException,
    GenerationRunConflictException,
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
from src.api.data.models.postgres.generation.generation_runs import GenerationRun
from src.api.data.models.postgres.generation.study_material_batches import (
    StudyMaterialBatchItem,
    StudyMaterialBatchRun,
)
from src.api.data.repositories.space_node_repository.node_repository import (
    NodeRepository,
    SubtreePreviewNode,
)
from src.api.schemas.common import GenerationRunStatus
from src.api.schemas.study_material_schemas.batch_schema import (
    BatchCurrentItemOut,
    BatchOverallProgressOut,
    BatchPreviewItemOut,
    BatchPreviewWarningsOut,
    BatchRootOut,
    BatchRootSegmentProgressOut,
    BatchSummaryOut,
    StudyMaterialBatchCancelResponse,
    StudyMaterialBatchDetailOut,
    StudyMaterialBatchEnqueueRequest,
    StudyMaterialBatchPreviewResponse,
    StudyMaterialSpaceQueueOut,
)
from src.api.schemas.study_material_schemas.study_material_schema import (
    StudyMaterialGenerateRequest,
)
from src.api.utils.common_utils import utc_now
from src.api.utils.generation_progress.advisory_lock import (
    try_acquire_generation_xact_lock,
)
from src.api.utils.space_node_utils.node_role_assert import _assert_space_access

logger = logging.getLogger(__name__)

# Claims without a generation_run_id longer than this are treated as orphaned.
ORPHAN_CLAIM_GRACE_SECONDS = 30


@dataclass
class AdvanceResult:
    """Result payload for advance calls.

    `scheduled_run_id` is populated only when we successfully started one next
    generation run; the caller (route layer) is responsible for scheduling the
    background job after commit.
    """

    snapshot: StudyMaterialSpaceQueueOut
    scheduled_run_id: UUID | None = None


class StudyMaterialBatchService:
    """Service layer for preview/enqueue/reconcile/advance/cancel queue operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def preview_generate_all(
        self,
        space_id: UUID,
        root_node_ids: list[UUID],
        mentor_id: UUID,
        role: str,
    ) -> StudyMaterialBatchPreviewResponse:
        """Build ordered plan items and warning metadata for modal UX.

        - Root resolution is constrained to active roots in the given space.
        - Subtree traversal is stable preorder (root, then descendants by order).
        - Warnings are precomputed so UI can render confirmation steps without
          additional round trips.
        """
        await _assert_space_access(self.session, space_id, mentor_id, role)
        root_nodes, _ = await self._resolve_roots(space_id, root_node_ids)
        items: list[BatchPreviewItemOut] = []
        missing_instruction_nodes: list[dict[str, Any]] = []
        inherits_section_default_nodes: list[dict[str, Any]] = []

        for root in root_nodes:
            subtree = await NodeRepository(self.session).get_subtree_nodes_preorder(
                root.node_id
            )
            items.extend(
                self._preview_item_from_subtree_node(
                    node_data=node_data,
                    root_node_id=root.node_id,
                    root_title=root.title,
                )
                for node_data in subtree
            )
            missing_instruction_nodes.extend(
                {
                    "node_id": node_data.node.node_id,
                    "title": node_data.node.title,
                    "path_titles": node_data.path_titles,
                }
                for node_data in subtree
                if not node_data.has_effective_instruction
            )
            inherits_section_default_nodes.extend(
                {
                    "node_id": node_data.node.node_id,
                    "title": node_data.node.title,
                    "path_titles": node_data.path_titles,
                }
                for node_data in subtree
                if node_data.inherits_section_default
            )

        return StudyMaterialBatchPreviewResponse(
            roots=[
                BatchRootOut(node_id=root.node_id, title=root.title)
                for root in root_nodes
            ],
            items=items,
            warnings=BatchPreviewWarningsOut(
                missing_instruction_nodes=missing_instruction_nodes,
                inherits_section_default_nodes=inherits_section_default_nodes,
                show_no_instruction_warning=bool(missing_instruction_nodes),
                show_inheritance_warning=bool(inherits_section_default_nodes),
            ),
        )

    async def enqueue_batch(
        self,
        space_id: UUID,
        payload: StudyMaterialBatchEnqueueRequest,
        mentor_id: UUID,
        role: str,
    ) -> StudyMaterialSpaceQueueOut:
        """Persist a new batch and all planned items under a short space lock.

        Queue position is FIFO within a space. If no running batch exists, the
        new batch starts in `running`; otherwise it starts in `queued`.

        Important: subtree planning / instruction analysis runs *outside* the
        advisory lock. Holding the lock during that work caused client timeouts
        ("Network Error") and left concurrent enqueue/advance racing on the
        same space lock.
        """
        await _assert_space_access(self.session, space_id, mentor_id, role)
        root_nodes, _ = await self._resolve_roots(space_id, payload.root_node_ids)
        plan_items: list[tuple[SubtreePreviewNode, UUID, str]] = []
        for root in root_nodes:
            subtree = await NodeRepository(self.session).get_subtree_nodes_preorder(
                root.node_id
            )
            plan_items.extend((item, root.node_id, root.title) for item in subtree)

        await self._require_space_xact_lock(space_id)
        max_position = await self.session.scalar(
            select(func.max(StudyMaterialBatchRun.queue_position)).where(
                StudyMaterialBatchRun.space_id == space_id
            )
        )
        queue_position = int(max_position or 0) + 1

        has_running = bool(
            await self.session.scalar(
                select(StudyMaterialBatchRun.batch_id).where(
                    StudyMaterialBatchRun.space_id == space_id,
                    StudyMaterialBatchRun.status == "running",
                )
            )
        )

        batch = StudyMaterialBatchRun(
            space_id=space_id,
            mentor_id=mentor_id,
            status="queued" if has_running else "running",
            queue_position=queue_position,
            # JSONB must be plain JSON — UUID objects are not serializable.
            selected_root_node_ids=[str(r.node_id) for r in root_nodes],
            policy=payload.policy.model_dump(mode="json"),
            total_items=len(plan_items),
        )
        self.session.add(batch)
        await self.session.flush()

        for idx, (node_data, root_node_id, _root_title) in enumerate(
            plan_items, start=1
        ):
            self.session.add(
                StudyMaterialBatchItem(
                    batch_id=batch.batch_id,
                    node_id=node_data.node.node_id,
                    root_segment_node_id=root_node_id,
                    position=idx,
                    depth_level=node_data.depth_level,
                    path_node_ids=[str(x) for x in node_data.path_node_ids],
                    path_titles=list(node_data.path_titles),
                    node_title=node_data.node.title,
                    status="queued",
                )
            )

        await self.session.flush()
        # Snapshot after inserts; xact lock releases on the route's COMMIT.
        return await self._build_queue_snapshot(space_id)

    async def get_space_queue(
        self, space_id: UUID, mentor_id: UUID, role: str
    ) -> StudyMaterialSpaceQueueOut:
        """Reconcile durable run outcomes, then return queue snapshot."""
        await _assert_space_access(self.session, space_id, mentor_id, role)
        return await self._build_queue_snapshot(space_id)

    async def reconcile_space_queue(self, space_id: UUID) -> None:
        """Project linked generation-run statuses onto running batch items.

        This is called from GET/advance entry points so queue UI reflects latest
        run terminal outcomes even if a background job finished out-of-band.
        """
        await self._reset_orphaned_running_claims(space_id)

        reconcilable_items = (
            (
                await self.session.execute(
                    select(StudyMaterialBatchItem)
                    .join(
                        StudyMaterialBatchRun,
                        StudyMaterialBatchRun.batch_id
                        == StudyMaterialBatchItem.batch_id,
                    )
                    .where(
                        StudyMaterialBatchRun.space_id == space_id,
                        StudyMaterialBatchItem.status.in_(
                            ["running", "failed_retryable"]
                        ),
                        StudyMaterialBatchItem.generation_run_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not reconcilable_items:
            return

        run_ids = [
            item.generation_run_id
            for item in reconcilable_items
            if item.generation_run_id
        ]
        run_rows = (
            (
                await self.session.execute(
                    select(GenerationRun).where(GenerationRun.run_id.in_(run_ids))
                )
            )
            .scalars()
            .all()
        )
        run_by_id = {run.run_id: run for run in run_rows}

        batch_ids = {item.batch_id for item in reconcilable_items}
        batch_rows = (
            (
                await self.session.execute(
                    select(StudyMaterialBatchRun).where(
                        StudyMaterialBatchRun.batch_id.in_(batch_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        batch_by_id = {batch.batch_id: batch for batch in batch_rows}

        for item in reconcilable_items:
            run = run_by_id.get(item.generation_run_id)
            if run is None:
                continue
            batch = batch_by_id.get(item.batch_id)
            if batch is None:
                continue

            previous_status = item.status
            if run.status == GenerationRunStatus.COMPLETED.value:
                item.status = "completed"
                item.version_id = await self._resolve_latest_version_id(item.node_id)
                item.completed_at = utc_now()
                if previous_status == "running":
                    batch.completed_items += 1
                elif previous_status == "failed_retryable":
                    batch.failed_items = max(0, batch.failed_items - 1)
                    batch.completed_items += 1
                batch.current_item_id = None
            elif run.status == GenerationRunStatus.CANCELLED.value:
                item.status = "cancelled"
                item.error_message = run.error_message
                item.completed_at = utc_now()
                if previous_status == "running":
                    batch.failed_items += 1
                batch.current_item_id = None
            elif run.status == GenerationRunStatus.FAILED.value:
                next_status = (
                    "failed_retryable"
                    if run.next_llm_retry_at is not None
                    else "failed"
                )
                item.status = next_status
                item.error_message = run.error_message
                if previous_status == "running":
                    batch.failed_items += 1
                batch.current_item_id = None
            elif run.status == GenerationRunStatus.RUNNING.value:
                if previous_status == "failed_retryable":
                    item.status = "running"
                    batch.failed_items = max(0, batch.failed_items - 1)
                    batch.current_item_id = item.item_id

        for batch in batch_rows:
            items = await self._items_for_batch(batch.batch_id)
            has_running = any(item.status == "running" for item in items)
            has_queued = any(item.status == "queued" for item in items)

            # Recompute counters from item state so stale `running 0/N` snapshots
            # self-heal after crashes/reloads.
            batch.completed_items = sum(
                1 for item in items if item.status == "completed"
            )
            batch.failed_items = sum(
                1
                for item in items
                if item.status in {"failed", "failed_retryable", "cancelled"}
            )
            batch.skipped_items = sum(1 for item in items if item.status == "skipped")

            if not has_running and not has_queued:
                batch.status = "completed"
                batch.current_item_id = None

    async def advance_space_queue(
        self,
        space_id: UUID,
        mentor_id: UUID,
        role: str,
    ) -> AdvanceResult:
        """Attempt to start exactly one next eligible item.

        Concurrency design (single-attempt, server-owned kick):
        - Uses a short-lived *transaction* space try-lock for claim.
          That lock auto-releases on COMMIT/ROLLBACK and cannot leak across
          Cloud Run connection pooling (unlike session advisory locks).
        - Claim → commit (releases xact lock) → start_generate → return.
        - If space lock unavailable: return ``advance_deferred=True``.
        - If node lock unavailable: **skip** the item (not re-queue) so the
          next kick picks the following queued item.
        - Callers should be ``batch_queue_kick.kick_space_queue``, not the browser.
        """
        await _assert_space_access(self.session, space_id, mentor_id, role)
        await self.reconcile_space_queue(space_id)

        claimed = await self._claim_next_item_under_lock(space_id)
        if claimed is None:
            return AdvanceResult(snapshot=await self._build_queue_snapshot(space_id))
        if claimed is False:
            return AdvanceResult(
                snapshot=await self._build_queue_snapshot(
                    space_id, advance_deferred=True
                )
            )

        item, batch = claimed
        # Persist the claim and drop the xact lock before the node start path
        # (which commits internally and would release the space lock).
        await self.session.commit()

        try:
            run_id = await StudyMaterialService(
                self.session
            ).start_generate_study_material(
                item.node_id,
                StudyMaterialGenerateRequest(
                    reference_material_id=self._policy_reference_material_id(
                        batch.policy
                    )
                ),
                mentor_id,
                role,
            )
        except (
            GenerationRunConflictException,
            GenerationAdvisoryLockUnavailableException,
        ) as exc:
            # Node is busy with its normal generate lock. Put this item back in
            # queued and defer — the next kick (completion or poll) will retry.
            item.status = "queued"
            item.generation_run_id = None
            item.error_message = None
            batch.current_item_id = None
            await self.session.flush()
            logger.info(
                "Generate-all item re-queued; node lock/conflict busy",
                extra={
                    "space_id": str(space_id),
                    "batch_id": str(batch.batch_id),
                    "item_id": str(item.item_id),
                    "node_id": str(item.node_id),
                    "reason": str(getattr(exc, "detail", exc)),
                },
            )
            return AdvanceResult(
                snapshot=await self._build_queue_snapshot(
                    space_id, advance_deferred=True
                )
            )
        except Exception as exc:
            # Non-lock startup failures should not poison the whole queue.
            item.status = "failed"
            item.error_message = str(exc)
            item.generation_run_id = None
            batch.failed_items += 1
            batch.current_item_id = None
            await self.session.flush()
            logger.exception(
                "Batch advance failed to start item run",
                extra={
                    "space_id": str(space_id),
                    "batch_id": str(batch.batch_id),
                    "item_id": str(item.item_id),
                    "node_id": str(item.node_id),
                    "mentor_id": str(mentor_id),
                },
            )
            return AdvanceResult(snapshot=await self._build_queue_snapshot(space_id))

        item.generation_run_id = run_id
        await self.session.flush()
        return AdvanceResult(
            snapshot=await self._build_queue_snapshot(space_id),
            scheduled_run_id=run_id,
        )

    async def _claim_next_item_under_lock(
        self, space_id: UUID
    ) -> tuple[StudyMaterialBatchItem, StudyMaterialBatchRun] | None | bool:
        """Claim the next queued item under a transaction space lock.

        Returns:
            ``(item, batch)`` on successful claim,
            ``None`` when there is nothing to start,
            ``False`` when the space lock could not be acquired (defer).
        """
        if not await try_acquire_generation_xact_lock(
            self.session,
            pipeline="study_material_batch_queue",
            resource_id=space_id,
        ):
            return False

        running_batch = await self._get_running_batch(space_id)
        if running_batch is None:
            running_batch = await self._promote_oldest_queued_batch(space_id)
        if running_batch is None:
            return None

        if await self._has_running_item(running_batch.batch_id):
            # Not a lock deferral — work is already in flight. Callers must
            # treat this as idle-until-completion (needs_advance=false after
            # snapshot), not as a contention retry storm.
            logger.info(
                "Batch advance: running item already exists",
                extra={
                    "space_id": str(space_id),
                    "batch_id": str(running_batch.batch_id),
                },
            )
            return None

        while True:
            next_item = await self._next_queued_item_for_batch(running_batch.batch_id)
            if next_item is None:
                if await self._has_queued_items(running_batch.batch_id):
                    logger.info(
                        "Batch advance deferred: queued items locked by another worker",
                        extra={
                            "space_id": str(space_id),
                            "batch_id": str(running_batch.batch_id),
                        },
                    )
                    return False
                running_batch.status = "completed"
                running_batch.current_item_id = None
                logger.info(
                    "Batch marked completed during claim: no queued items",
                    extra={
                        "space_id": str(space_id),
                        "batch_id": str(running_batch.batch_id),
                    },
                )
                return None

            if await self._should_skip_item(running_batch, next_item):
                next_item.status = "skipped"
                running_batch.skipped_items += 1
                continue

            next_item.status = "running"
            next_item.generation_run_id = None
            running_batch.current_item_id = next_item.item_id
            running_batch.status = "running"
            await self.session.flush()
            return next_item, running_batch

    async def _reset_orphaned_running_claims(self, space_id: UUID) -> None:
        """Re-queue claims that never received a generation_run_id.

        Happens if the process dies after claim-commit but before start_generate,
        or if start_generate fails without unclaiming. Without this, ``_has_running_item``
        blocks the whole space forever.
        """
        orphan_cutoff = utc_now() - timedelta(seconds=ORPHAN_CLAIM_GRACE_SECONDS)
        orphans = (
            (
                await self.session.execute(
                    select(StudyMaterialBatchItem)
                    .join(
                        StudyMaterialBatchRun,
                        StudyMaterialBatchRun.batch_id
                        == StudyMaterialBatchItem.batch_id,
                    )
                    .where(
                        StudyMaterialBatchRun.space_id == space_id,
                        StudyMaterialBatchRun.status == "running",
                        StudyMaterialBatchItem.status == "running",
                        StudyMaterialBatchItem.generation_run_id.is_(None),
                        StudyMaterialBatchItem.updated_at < orphan_cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        if not orphans:
            return

        batch_ids = {item.batch_id for item in orphans}
        batches = (
            (
                await self.session.execute(
                    select(StudyMaterialBatchRun).where(
                        StudyMaterialBatchRun.batch_id.in_(batch_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        batch_by_id = {batch.batch_id: batch for batch in batches}

        for item in orphans:
            item.status = "queued"
            batch = batch_by_id.get(item.batch_id)
            if batch is not None and batch.current_item_id == item.item_id:
                batch.current_item_id = None

    async def cancel_batch(
        self,
        batch_id: UUID,
        mentor_id: UUID,
        role: str,
    ) -> tuple[StudyMaterialBatchCancelResponse, UUID]:
        """Cancel queued/retryable items in a batch under space lock.

        Returns the API response plus ``space_id`` so callers can kick the
        remaining space queue after commit.
        """
        batch = await self._get_batch(batch_id)
        if batch is None:
            raise ValueError("Batch not found")
        space_id = batch.space_id
        await _assert_space_access(self.session, space_id, mentor_id, role)
        await self._require_space_xact_lock(space_id)
        batch.status = "cancelled"
        batch.current_item_id = None
        now = utc_now()
        items = await self._items_for_batch(batch_id)
        for item in items:
            if item.status == "running":
                if item.generation_run_id is not None:
                    try:
                        await GenerationRunService(self.session).cancel_run(
                            item.generation_run_id,
                            mentor_id=mentor_id,
                        )
                    except (
                        GenerationRunNotFoundException,
                        GenerationRunNotCancellableException,
                    ):
                        # Run may have completed between snapshot and cancel action.
                        pass
                # Also cancel claimed-but-not-started items (running with no run_id).
                item.status = "cancelled"
                item.error_message = "Cancelled by mentor."
                item.completed_at = now
                batch.failed_items += 1
            if item.status in {"queued", "failed_retryable"}:
                item.status = "cancelled"
                item.completed_at = now
        return (
            StudyMaterialBatchCancelResponse(
                batch_id=batch.batch_id, status="cancelled"
            ),
            space_id,
        )

    async def get_batch_detail(
        self, batch_id: UUID, mentor_id: UUID, role: str
    ) -> StudyMaterialBatchDetailOut:
        """Return denormalized batch detail with per-item run status."""
        batch = await self._get_batch(batch_id)
        if batch is None:
            raise ValueError("Batch not found")
        await _assert_space_access(self.session, batch.space_id, mentor_id, role)
        # Keep detail endpoint consistent with queue snapshot reconciliation.
        await self.reconcile_space_queue(batch.space_id)
        runs = await self._runs_for_batch(batch.batch_id)
        run_status_by_id = {run.run_id: run.status for run in runs}
        items = await self._items_for_batch(batch.batch_id)
        return StudyMaterialBatchDetailOut(
            batch=self._batch_summary(batch),
            items=[
                BatchCurrentItemOut(
                    item_id=item.item_id,
                    node_id=item.node_id,
                    node_title=item.node_title,
                    depth_level=item.depth_level,
                    path_titles=item.path_titles or [],
                    generation_run_id=item.generation_run_id,
                    run_status=run_status_by_id.get(item.generation_run_id),
                    status=item.status,
                    error_message=item.error_message,
                )
                for item in items
            ],
        )

    async def _build_queue_snapshot(
        self, space_id: UUID, advance_deferred: bool = False
    ) -> StudyMaterialSpaceQueueOut:
        """Compute UI-facing queue snapshot for one space.

        Snapshot includes:
        - current running and queued batches
        - whether caller should invoke `advance`
        - overall and current-root-segment progress
        - current running item + linked durable run status
        """
        await self.reconcile_space_queue(space_id)
        running_batch = await self._get_running_batch(space_id)
        recent_terminal_batch = await self._latest_terminal_batch(space_id)
        queued_batches = await self._queued_batches(space_id)
        current_item: BatchCurrentItemOut | None = None
        current_root_segment: BatchRootSegmentProgressOut | None = None
        needs_advance = False

        if running_batch is not None:
            items = await self._items_for_batch(running_batch.batch_id)
            run_ids = [
                item.generation_run_id for item in items if item.generation_run_id
            ]
            runs = cast(
                list[GenerationRun],
                (
                    await self.session.execute(
                        select(GenerationRun).where(GenerationRun.run_id.in_(run_ids))
                    )
                )
                .scalars()
                .all(),
            )
            run_by_id = {run.run_id: run for run in runs}
            running_item = next(
                (item for item in items if item.status == "running"), None
            )
            if running_item is not None:
                run_status = None
                if running_item.generation_run_id:
                    run_obj = run_by_id.get(running_item.generation_run_id)
                    run_status = run_obj.status if run_obj else None
                current_item = BatchCurrentItemOut(
                    item_id=running_item.item_id,
                    node_id=running_item.node_id,
                    node_title=running_item.node_title,
                    depth_level=running_item.depth_level,
                    path_titles=running_item.path_titles or [],
                    generation_run_id=running_item.generation_run_id,
                    run_status=run_status,
                    status=running_item.status,
                    error_message=running_item.error_message,
                )
            needs_advance = running_item is None and any(
                item.status == "queued" for item in items
            )
            if current_item is not None:
                current_db_item = next(
                    (item for item in items if item.item_id == current_item.item_id),
                    None,
                )
                if current_db_item is not None:
                    segment_items = [
                        item
                        for item in items
                        if item.root_segment_node_id
                        == current_db_item.root_segment_node_id
                    ]
                    segment_done = sum(
                        1 for item in segment_items if item.status in {"completed"}
                    )
                    current_root_segment = BatchRootSegmentProgressOut(
                        root_node_id=current_db_item.root_segment_node_id,
                        root_title=(
                            current_db_item.path_titles or [current_db_item.node_title]
                        )[0],
                        completed=segment_done,
                        total=len(segment_items),
                    )

            overall_progress = BatchOverallProgressOut(
                completed=running_batch.completed_items,
                total=running_batch.total_items,
                failed=running_batch.failed_items,
                skipped=running_batch.skipped_items,
            )
        else:
            overall_progress = BatchOverallProgressOut(
                completed=0,
                total=0,
                failed=0,
                skipped=0,
            )

        return StudyMaterialSpaceQueueOut(
            running_batch=self._batch_summary(running_batch) if running_batch else None,
            recent_terminal_batch=self._batch_summary(recent_terminal_batch)
            if recent_terminal_batch
            else None,
            queued_batches=[self._batch_summary(batch) for batch in queued_batches],
            needs_advance=needs_advance,
            advance_deferred=advance_deferred,
            overall_progress=overall_progress,
            current_root_segment=current_root_segment,
            current_item=current_item,
        )

    async def _resolve_roots(
        self, space_id: UUID, root_node_ids: list[UUID]
    ) -> tuple[list, dict[UUID, str]]:
        """Resolve selected roots; defaults to all active roots when empty."""
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

    def _preview_item_from_subtree_node(
        self,
        *,
        node_data: SubtreePreviewNode,
        root_node_id: UUID,
        root_title: str,
    ) -> BatchPreviewItemOut:
        """Convert repository subtree node shape into preview response item."""
        return BatchPreviewItemOut(
            node_id=node_data.node.node_id,
            title=node_data.node.title,
            depth_level=node_data.depth_level,
            path_node_ids=node_data.path_node_ids,
            path_titles=node_data.path_titles,
            root_segment_node_id=root_node_id,
            root_segment_title=root_title,
        )

    async def _resolve_latest_version_id(self, node_id: UUID) -> UUID | None:
        """Fetch latest study-material version id for completed queue items."""
        version = (
            (
                await self.session.execute(
                    select(StudyMaterialVersion)
                    .where(StudyMaterialVersion.node_id == node_id)
                    .order_by(StudyMaterialVersion.version_number.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        return version.version_id if version else None

    async def _has_running_item(self, batch_id: UUID) -> bool:
        """Return True when any item in the active batch is currently running."""
        value = await self.session.scalar(
            select(func.count())
            .select_from(StudyMaterialBatchItem)
            .where(
                StudyMaterialBatchItem.batch_id == batch_id,
                StudyMaterialBatchItem.status == "running",
            )
        )
        return bool(value and value > 0)

    async def _has_queued_items(self, batch_id: UUID) -> bool:
        """Return True when the batch still has queued items."""
        value = await self.session.scalar(
            select(func.count())
            .select_from(StudyMaterialBatchItem)
            .where(
                StudyMaterialBatchItem.batch_id == batch_id,
                StudyMaterialBatchItem.status == "queued",
            )
        )
        return bool(value and value > 0)

    async def _next_queued_item_for_batch(
        self, batch_id: UUID
    ) -> StudyMaterialBatchItem | None:
        """Pick next processable item with row lock to avoid double-start races."""
        result = await self.session.execute(
            select(StudyMaterialBatchItem)
            .where(
                StudyMaterialBatchItem.batch_id == batch_id,
                StudyMaterialBatchItem.status == "queued",
            )
            .order_by(StudyMaterialBatchItem.position.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return cast(StudyMaterialBatchItem | None, result.scalars().first())

    async def _should_skip_item(
        self, batch: StudyMaterialBatchRun, item: StudyMaterialBatchItem
    ) -> bool:
        """Apply existing-material policy (`skip` vs `regenerate`)."""
        policy = (batch.policy or {}).get("existing_material_policy", "skip")
        if policy != "skip":
            return False
        has_version = bool(
            await self.session.scalar(
                select(StudyMaterialVersion.version_id)
                .where(StudyMaterialVersion.node_id == item.node_id)
                .limit(1)
            )
        )
        return has_version

    def _policy_reference_material_id(self, policy: dict | None) -> UUID | None:
        """Extract optional reference material id from batch policy JSON."""
        raw = (policy or {}).get("reference_material_id")
        if raw is None:
            return None
        return UUID(str(raw))

    async def _require_space_xact_lock(self, space_id: UUID) -> None:
        """Acquire transaction-scoped queue lock or raise advisory-lock conflict.

        Retries briefly because enqueue can race advance for a few milliseconds.
        """
        for attempt in range(12):
            if await try_acquire_generation_xact_lock(
                self.session,
                pipeline="study_material_batch_queue",
                resource_id=space_id,
            ):
                return
            await asyncio.sleep(0.05 * (attempt + 1))
        raise GenerationAdvisoryLockUnavailableException()

    async def _get_running_batch(self, space_id: UUID) -> StudyMaterialBatchRun | None:
        """Fetch active running batch for a space."""
        result = await self.session.execute(
            self._base_batch_query(space_id).where(
                StudyMaterialBatchRun.status == "running"
            )
        )
        return cast(StudyMaterialBatchRun | None, result.scalars().first())

    async def _queued_batches(self, space_id: UUID) -> list[StudyMaterialBatchRun]:
        """Fetch queued batches ordered by FIFO queue position."""
        return list(
            (
                await self.session.execute(
                    self._base_batch_query(space_id).where(
                        StudyMaterialBatchRun.status == "queued"
                    )
                )
            )
            .scalars()
            .all()
        )

    async def _latest_terminal_batch(
        self, space_id: UUID
    ) -> StudyMaterialBatchRun | None:
        """Newest completed/failed/cancelled batch for reload visibility."""
        result = await self.session.execute(
            self._base_batch_query(space_id)
            .where(
                StudyMaterialBatchRun.status.in_(["completed", "failed", "cancelled"])
            )
            .limit(1)
        )
        return cast(StudyMaterialBatchRun | None, result.scalars().first())

    def _base_batch_query(self, space_id: UUID) -> Select[tuple[StudyMaterialBatchRun]]:
        """Base ordered batch query used by running/queued selectors."""
        return (
            select(StudyMaterialBatchRun)
            .where(StudyMaterialBatchRun.space_id == space_id)
            .order_by(
                StudyMaterialBatchRun.queue_position.asc(),
                StudyMaterialBatchRun.created_at.asc(),
            )
        )

    async def _promote_oldest_queued_batch(
        self, space_id: UUID
    ) -> StudyMaterialBatchRun | None:
        """Promote oldest queued batch to running when no running batch exists."""
        result = await self.session.execute(
            self._base_batch_query(space_id)
            .where(StudyMaterialBatchRun.status == "queued")
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        queued = cast(StudyMaterialBatchRun | None, result.scalars().first())
        if queued is not None:
            queued.status = "running"
        return queued

    async def _get_batch(self, batch_id: UUID) -> StudyMaterialBatchRun | None:
        """Load one batch by id."""
        return cast(
            StudyMaterialBatchRun | None,
            await self.session.get(StudyMaterialBatchRun, batch_id),
        )

    async def _items_for_batch(self, batch_id: UUID) -> list[StudyMaterialBatchItem]:
        """Load all items for batch in stable position order."""
        return list(
            (
                await self.session.execute(
                    select(StudyMaterialBatchItem)
                    .where(StudyMaterialBatchItem.batch_id == batch_id)
                    .order_by(StudyMaterialBatchItem.position.asc())
                )
            )
            .scalars()
            .all()
        )

    async def _runs_for_batch(self, batch_id: UUID) -> list[GenerationRun]:
        """Load durable generation runs linked from batch items."""
        run_ids = [
            item.generation_run_id
            for item in await self._items_for_batch(batch_id)
            if item.generation_run_id
        ]
        if not run_ids:
            return []
        return list(
            (
                await self.session.execute(
                    select(GenerationRun).where(GenerationRun.run_id.in_(run_ids))
                )
            )
            .scalars()
            .all()
        )

    def _batch_summary(self, batch: StudyMaterialBatchRun) -> BatchSummaryOut:
        """Map ORM batch row to response summary DTO."""
        selected_ids: list[Any] = (
            batch.selected_root_node_ids
            if isinstance(batch.selected_root_node_ids, list)
            else []
        )
        return BatchSummaryOut(
            batch_id=batch.batch_id,
            space_id=batch.space_id,
            mentor_id=batch.mentor_id,
            status=batch.status,
            queue_position=batch.queue_position,
            selected_root_node_ids=[UUID(str(x)) for x in selected_ids],
            total_items=batch.total_items,
            completed_items=batch.completed_items,
            failed_items=batch.failed_items,
            skipped_items=batch.skipped_items,
            current_item_id=batch.current_item_id,
            created_at=batch.created_at,
            updated_at=batch.updated_at,
        )
