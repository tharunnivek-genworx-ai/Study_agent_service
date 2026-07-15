"""
One-time recovery for stacked reference_materials rows and stuck generation_runs.

Symptoms addressed (see reference PDF state bug plan):
  - Multiple active reference_materials rows for one node (ghost PDFs after delete)
  - generation_runs stuck in 'running' holding the per-node advisory lock

Usage (from study_agent_service/, with DB reachable):
  .venv/bin/python scripts/cleanup_reference_materials_and_generation_runs.py --node-id <uuid> --dry-run
  .venv/bin/python scripts/cleanup_reference_materials_and_generation_runs.py --node-id <uuid> --apply

Optional lookup by topic title (first match):
  .venv/bin/python scripts/cleanup_reference_materials_and_generation_runs.py --node-title Calculus --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, select, update

from src.api.data.clients.postgres.database import SessionLocal
from src.api.data.models.postgres.e_learning_content.reference_materials import (
    ReferenceMaterial,
)
from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.models.postgres.generation.generation_runs import GenerationRun
from src.api.schemas import ACTIVE_RUN_STATUSES, GenerationRunStatus


async def resolve_node_id(
    session, node_id: UUID | None, node_title: str | None
) -> UUID:
    if node_id is not None:
        return node_id
    if not node_title:
        raise SystemExit("Provide --node-id or --node-title.")

    result = await session.execute(
        select(TopicNode.node_id, TopicNode.title).where(
            func.lower(TopicNode.title) == node_title.strip().lower()
        )
    )
    rows = list(result.all())
    if not rows:
        raise SystemExit(f"No topic node found with title {node_title!r}.")
    if len(rows) > 1:
        print("Multiple nodes match; use --node-id instead:")
        for nid, title in rows:
            print(f"  {nid}  {title}")
        raise SystemExit(1)
    return rows[0][0]


async def list_active_reference_materials(
    session, node_id: UUID
) -> list[ReferenceMaterial]:
    result = await session.execute(
        select(ReferenceMaterial)
        .where(
            and_(
                ReferenceMaterial.node_id == node_id,
                ReferenceMaterial.scope == "node",
                ReferenceMaterial.deleted_at.is_(None),
            )
        )
        .order_by(ReferenceMaterial.created_at.desc())
    )
    return list(result.scalars().all())


async def list_stuck_generation_runs(session, node_id: UUID) -> list[GenerationRun]:
    result = await session.execute(
        select(GenerationRun)
        .where(
            and_(
                GenerationRun.resource_id == node_id,
                GenerationRun.pipeline == "study_material",
                GenerationRun.status.in_(tuple(s.value for s in ACTIVE_RUN_STATUSES)),
            )
        )
        .order_by(GenerationRun.created_at.desc())
    )
    return list(result.scalars().all())


async def soft_delete_reference_materials(
    session, materials: list[ReferenceMaterial], *, keep_latest: bool
) -> list[UUID]:
    if not materials:
        return []
    to_delete = materials[1:] if keep_latest and len(materials) > 1 else materials
    if not to_delete:
        return []
    now = datetime.now(UTC)
    ids = [m.material_id for m in to_delete]
    await session.execute(
        update(ReferenceMaterial)
        .where(ReferenceMaterial.material_id.in_(ids))
        .values(deleted_at=now, updated_at=now)
    )
    return ids


async def abandon_generation_runs(session, runs: list[GenerationRun]) -> list[UUID]:
    if not runs:
        return []
    now = datetime.now(UTC)
    ids = [r.run_id for r in runs]
    await session.execute(
        update(GenerationRun)
        .where(GenerationRun.run_id.in_(ids))
        .values(
            status=GenerationRunStatus.ABANDONED.value,
            error_message="Abandoned by cleanup_reference_materials_and_generation_runs.py",
            error_type="abandoned",
            abandoned_at=now,
            abandon_reason="cleanup_script",
            updated_at=now,
        )
    )
    return ids


def print_reference_materials(materials: list[ReferenceMaterial]) -> None:
    if not materials:
        print("  (none)")
        return
    for m in materials:
        print(
            f"  {m.material_id}  created={m.created_at.isoformat()}  title={m.title!r}"
        )


def print_generation_runs(runs: list[GenerationRun]) -> None:
    if not runs:
        print("  (none)")
        return
    for r in runs:
        print(
            f"  {r.run_id}  status={r.status}  mode={r.generation_mode}  "
            f"created={r.created_at.isoformat()}"
        )


async def run(args: argparse.Namespace) -> int:
    async with SessionLocal() as session:
        node_id = await resolve_node_id(
            session,
            UUID(args.node_id) if args.node_id else None,
            args.node_title,
        )

        node_row = await session.execute(
            select(TopicNode.title).where(TopicNode.node_id == node_id)
        )
        node_title = node_row.scalar_one_or_none() or "(unknown)"

        print(f"Node: {node_id} ({node_title})")
        print()

        materials = await list_active_reference_materials(session, node_id)
        print(f"Active node-scoped reference_materials ({len(materials)}):")
        print_reference_materials(materials)
        print()

        runs = await list_stuck_generation_runs(session, node_id)
        print(f"Active study_material generation_runs ({len(runs)}):")
        print_generation_runs(runs)
        print()

        if args.dry_run:
            if len(materials) > 1:
                print(
                    f"DRY RUN: would soft-delete {len(materials) - 1} older stacked row(s), "
                    f"keeping latest {materials[0].material_id}"
                )
            elif len(materials) == 1 and args.delete_all_reference_materials:
                print(
                    f"DRY RUN: would soft-delete sole active row {materials[0].material_id}"
                )
            if runs:
                print(f"DRY RUN: would cancel {len(runs)} generation run(s)")
            if (
                len(materials) <= 1
                and not runs
                and not (len(materials) == 1 and args.delete_all_reference_materials)
            ):
                print("Nothing to clean up.")
            return 0

        deleted_material_ids: list[UUID] = []
        if len(materials) > 1:
            deleted_material_ids = await soft_delete_reference_materials(
                session, materials, keep_latest=True
            )
        elif len(materials) == 1 and args.delete_all_reference_materials:
            deleted_material_ids = await soft_delete_reference_materials(
                session, materials, keep_latest=False
            )

        abandoned_run_ids = await abandon_generation_runs(session, runs)

        if deleted_material_ids or abandoned_run_ids:
            await session.commit()
            if deleted_material_ids:
                print(
                    f"Soft-deleted reference_materials: {', '.join(map(str, deleted_material_ids))}"
                )
            if abandoned_run_ids:
                print(
                    f"Abandoned generation_runs: {', '.join(map(str, abandoned_run_ids))}"
                )
        else:
            print("Nothing to clean up.")

    print()
    print(
        "Done. Hard-refresh the mentor UI so lifted nodeStudyStates reload from the API."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean stacked reference_materials and stuck generation_runs for a topic node."
    )
    parser.add_argument("--node-id", help="Topic node UUID")
    parser.add_argument(
        "--node-title", help="Exact topic title (case-insensitive); first match wins"
    )
    parser.add_argument(
        "--delete-all-reference-materials",
        action="store_true",
        help="When only one active row remains, soft-delete it too (start clean)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply soft-deletes and cancel stuck runs (default is dry-run)",
    )
    args = parser.parse_args()
    args.dry_run = not args.apply
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
