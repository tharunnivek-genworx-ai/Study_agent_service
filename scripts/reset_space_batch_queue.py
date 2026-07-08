"""Repair or wipe study-material batch queue state for one space.

Usage examples:
  # Safe recovery: cancel stuck running/queued queue rows for a space
  python scripts/reset_space_batch_queue.py --space-id <SPACE_UUID> --mode recover

  # Hard wipe queue rows (batch runs + items) for a space
  python scripts/reset_space_batch_queue.py --space-id <SPACE_UUID> --mode wipe

Notes:
  - This script only touches study-material batch queue tables.
  - It does not delete topics, study material versions, or the space itself.
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import delete, select

from src.api.data.clients.postgres.database import SessionLocal
from src.api.data.models.postgres.generation.study_material_batches import (
    StudyMaterialBatchItem,
    StudyMaterialBatchRun,
)
from src.api.utils.common_utils import utc_now


async def recover_queue(space_id: UUID) -> dict[str, int]:
    now = utc_now()
    async with SessionLocal() as session:
        batches = (
            (
                await session.execute(
                    select(StudyMaterialBatchRun).where(
                        StudyMaterialBatchRun.space_id == space_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if not batches:
            return {"batches": 0, "items": 0}

        batch_ids = [b.batch_id for b in batches]
        items = (
            (
                await session.execute(
                    select(StudyMaterialBatchItem).where(
                        StudyMaterialBatchItem.batch_id.in_(batch_ids)
                    )
                )
            )
            .scalars()
            .all()
        )

        touched_items = 0
        for item in items:
            if item.status in {"queued", "running", "failed_retryable"}:
                item.status = "cancelled"
                item.error_message = (
                    item.error_message or "Recovered: cancelled stale queue item."
                )
                item.completed_at = now
                touched_items += 1

        for batch in batches:
            batch.status = "cancelled"
            batch.current_item_id = None
            # Recompute counters from item statuses to leave rows consistent.
            batch_items = [i for i in items if i.batch_id == batch.batch_id]
            batch.completed_items = sum(
                1 for i in batch_items if i.status == "completed"
            )
            batch.failed_items = sum(
                1
                for i in batch_items
                if i.status in {"failed", "failed_retryable", "cancelled"}
            )
            batch.skipped_items = sum(1 for i in batch_items if i.status == "skipped")

        await session.commit()
        return {"batches": len(batches), "items": touched_items}


async def wipe_queue(space_id: UUID) -> dict[str, int]:
    async with SessionLocal() as session:
        batch_ids = (
            (
                await session.execute(
                    select(StudyMaterialBatchRun.batch_id).where(
                        StudyMaterialBatchRun.space_id == space_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if not batch_ids:
            return {"batches": 0, "items": 0}

        # Items are CASCADE-linked; explicit delete gives us item count for output.
        item_delete = await session.execute(
            delete(StudyMaterialBatchItem).where(
                StudyMaterialBatchItem.batch_id.in_(batch_ids)
            )
        )
        batch_delete = await session.execute(
            delete(StudyMaterialBatchRun).where(
                StudyMaterialBatchRun.space_id == space_id
            )
        )
        await session.commit()
        return {
            "batches": int(batch_delete.rowcount or 0),
            "items": int(item_delete.rowcount or 0),
        }


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recover or wipe stale batch queue state."
    )
    parser.add_argument("--space-id", required=True, help="Target space UUID")
    parser.add_argument(
        "--mode",
        choices=["recover", "wipe"],
        default="recover",
        help="recover = mark stale queue rows cancelled, wipe = hard delete queue rows",
    )
    args = parser.parse_args()

    space_id = UUID(args.space_id)
    if args.mode == "recover":
        result = await recover_queue(space_id)
    else:
        result = await wipe_queue(space_id)

    print(
        f"Queue {args.mode} complete for space {space_id}: "
        f"{result['batches']} batches, {result['items']} items."
    )


if __name__ == "__main__":
    asyncio.run(main())
