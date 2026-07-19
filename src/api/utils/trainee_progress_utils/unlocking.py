"""
Progressive subtopic unlocking — single source of truth.

A parent node gates its direct children only when it is a learning unit
(has published study material). Completing that parent batch-unlocks all
direct children that have accessible learning content. Grants are durable:
C1/C2 parent progress resets and C6 parent SM unpublish do **not** revoke
them (C6 drops the gate via resolve rules instead).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import NodePrerequisiteLockedException
from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.models.postgres.progress_models.trainee_node_progress import (
    TraineeNodeProgress,
)
from src.api.data.repositories.progress_repositories.trainee_node_progress_repository import (
    TraineeNodeProgressRepository,
)
from src.api.data.repositories.progress_repositories.trainee_node_unlock_repository import (
    TraineeNodeUnlockRepository,
)
from src.api.data.repositories.trainee_quiz_repositories.trainee_quiz_repository import (
    TraineeQuizRepository,
)
from src.api.data.repositories.trainee_study_repositories.trainee_study_repository import (
    TraineeStudyRepository,
)
from src.api.schemas.progress_schemas import TraineeNodeProgressBatchItemOut
from src.api.utils.trainee_progress_utils.completion import (
    compute_completion_status,
    compute_progress_percentage,
    is_learning_unit_complete,
)
from src.api.utils.trainee_progress_utils.learning_units import (
    has_accessible_learning_content,
)

AccessStatus = Literal["coming_soon", "prerequisite_locked", "available"]
UnlockSource = Literal["parent_completed", "backfill"]


@dataclass(frozen=True)
class AccessResult:
    status: AccessStatus
    blocked_by_node_id: UUID | None = None
    blocked_by_title: str | None = None
    unlock_message: str | None = None
    newly_granted: bool = False


@dataclass(frozen=True)
class UnlockTreeContext:
    """Tree shape + publication flags needed by resolve/grant helpers."""

    children_by_parent: dict[UUID | None, list[UUID]]
    published_node_ids: set[UUID]
    node_titles: dict[UUID, str]
    parent_by_node: dict[UUID, UUID | None]


@dataclass(frozen=True)
class UnlockProgressContext:
    """Trainee progress + durable grants for resolve decisions."""

    progress_by_node: dict[UUID, TraineeNodeProgressBatchItemOut]
    quiz_published_node_ids: set[UUID]
    unlocked_node_ids: set[UUID]


def prerequisite_message(parent_title: str) -> str:
    return f"Finish {parent_title} first"


def is_parent_learning_unit(
    parent_id: UUID | None, published_node_ids: set[UUID]
) -> bool:
    """True when the direct parent itself has published study material (gate)."""
    return parent_id is not None and parent_id in published_node_ids


def is_progress_complete(
    snapshot: TraineeNodeProgressBatchItemOut | None,
    *,
    node_id: UUID,
    quiz_published_node_ids: set[UUID],
) -> bool:
    """Whether a learning unit currently meets completion requirements."""
    if snapshot is None:
        return False
    return is_learning_unit_complete(
        study_material_completed=snapshot.study_material_completed,
        quiz_passed=snapshot.quiz_passed,
        study_material_read_percent=snapshot.study_material_read_percent,
        quiz_attempt_count=snapshot.quiz_attempt_count,
        has_published_quiz=node_id in quiz_published_node_ids,
    )


def resolve_node_access(
    *,
    node_id: UUID,
    tree: UnlockTreeContext,
    progress: UnlockProgressContext,
) -> AccessResult:
    """Pure access decision (no DB writes).

    Order matches product rules:
      1. no accessible content → coming_soon
      2. root / pure parent (no published SM on parent) → available
      3. durable unlock → available
      4. parent currently completed → available (caller may grant)
      5. else → prerequisite_locked
    """
    if not has_accessible_learning_content(
        node_id, tree.published_node_ids, tree.children_by_parent
    ):
        return AccessResult(status="coming_soon")

    parent_id = tree.parent_by_node.get(node_id)
    if not is_parent_learning_unit(parent_id, tree.published_node_ids):
        return AccessResult(status="available")

    assert parent_id is not None  # gated ⇒ parent exists
    if node_id in progress.unlocked_node_ids:
        return AccessResult(status="available")

    parent_complete = is_progress_complete(
        progress.progress_by_node.get(parent_id),
        node_id=parent_id,
        quiz_published_node_ids=progress.quiz_published_node_ids,
    )
    if parent_complete:
        return AccessResult(status="available")

    parent_title = tree.node_titles.get(parent_id, "the previous topic")
    return AccessResult(
        status="prerequisite_locked",
        blocked_by_node_id=parent_id,
        blocked_by_title=parent_title,
        unlock_message=prerequisite_message(parent_title),
    )


def eligible_children_for_unlock(
    parent_id: UUID,
    tree: UnlockTreeContext,
) -> list[UUID]:
    """Direct children that have accessible learning content (batch unlock set)."""
    return [
        child_id
        for child_id in tree.children_by_parent.get(parent_id, [])
        if has_accessible_learning_content(
            child_id, tree.published_node_ids, tree.children_by_parent
        )
    ]


def _progress_snapshot_from_row(
    row: TraineeNodeProgress,
    *,
    has_published_quiz: bool,
) -> TraineeNodeProgressBatchItemOut:
    completion_status = compute_completion_status(
        study_material_completed=row.study_material_completed,
        quiz_passed=row.quiz_passed,
        study_material_read_percent=row.study_material_read_percent,
        quiz_attempt_count=row.quiz_attempt_count,
        has_published_quiz=has_published_quiz,
    )
    progress_percentage = compute_progress_percentage(
        study_material_completed=row.study_material_completed,
        quiz_passed=row.quiz_passed,
        has_published_quiz=has_published_quiz,
    )
    return TraineeNodeProgressBatchItemOut(
        node_id=row.node_id,
        study_material_read_percent=row.study_material_read_percent,
        study_material_completed=row.study_material_completed,
        quiz_passed=row.quiz_passed,
        quiz_attempt_count=row.quiz_attempt_count,
        completion_status=completion_status,
        progress_percentage=progress_percentage,
    )


async def build_unlock_tree_context(
    session: AsyncSession, *, space_id: UUID
) -> UnlockTreeContext:
    """Load active tree shape and published-SM node ids for a space."""
    result = await session.execute(
        select(TopicNode).where(
            and_(TopicNode.space_id == space_id, TopicNode.is_active.is_(True))
        )
    )
    nodes = list(result.scalars().all())
    children_by_parent: dict[UUID | None, list[UUID]] = {}
    node_titles: dict[UUID, str] = {}
    parent_by_node: dict[UUID, UUID | None] = {}
    order_by_node: dict[UUID, int] = {}
    for node in nodes:
        children_by_parent.setdefault(node.parent_id, []).append(node.node_id)
        node_titles[node.node_id] = node.title
        parent_by_node[node.node_id] = node.parent_id
        order_by_node[node.node_id] = node.order_index
    for child_ids in children_by_parent.values():
        child_ids.sort(key=lambda child_id: order_by_node.get(child_id, 0))

    study_repo = TraineeStudyRepository(session)
    published_node_ids = await study_repo.get_published_node_ids(space_id)
    return UnlockTreeContext(
        children_by_parent=children_by_parent,
        published_node_ids=published_node_ids,
        node_titles=node_titles,
        parent_by_node=parent_by_node,
    )


async def build_unlock_progress_context(
    session: AsyncSession,
    *,
    trainee_id: UUID,
    node_ids: list[UUID],
) -> UnlockProgressContext:
    """Load progress snapshots, published-quiz flags, and durable grants."""
    unique_ids = list(dict.fromkeys(node_ids))
    if not unique_ids:
        return UnlockProgressContext(
            progress_by_node={},
            quiz_published_node_ids=set(),
            unlocked_node_ids=set(),
        )

    progress_repo = TraineeNodeProgressRepository(session)
    quiz_repo = TraineeQuizRepository(session)
    unlock_repo = TraineeNodeUnlockRepository(session)

    rows = await progress_repo.get_batch_by_trainee_and_nodes(trainee_id, unique_ids)
    quiz_published_node_ids = await quiz_repo.get_published_quiz_node_ids(unique_ids)
    unlocked_node_ids = await unlock_repo.get_unlocked_node_ids(trainee_id, unique_ids)

    progress_by_node: dict[UUID, TraineeNodeProgressBatchItemOut] = {}
    for node_id in unique_ids:
        row = rows.get(node_id)
        if row is None:
            continue
        progress_by_node[node_id] = _progress_snapshot_from_row(
            row,
            has_published_quiz=node_id in quiz_published_node_ids,
        )

    return UnlockProgressContext(
        progress_by_node=progress_by_node,
        quiz_published_node_ids=quiz_published_node_ids,
        unlocked_node_ids=unlocked_node_ids,
    )


async def assert_trainee_node_unlocked(
    session: AsyncSession,
    *,
    trainee_id: UUID,
    node_id: UUID,
    space_id: UUID,
) -> AccessResult:
    """Enforce unlock on current trainee content endpoints.

    Raises ``NodePrerequisiteLockedException`` when the node is gated by an
    incomplete parent learning unit. Lazily writes a durable grant when the
    parent is already complete. Does **not** raise for ``coming_soon`` —
    publication gates remain the responsibility of content loaders.

    Archive / history / mentor paths must not call this helper.
    """
    tree = await build_unlock_tree_context(session, space_id=space_id)
    parent_id = tree.parent_by_node.get(node_id)
    relevant_ids = [node_id]
    if parent_id is not None:
        relevant_ids.append(parent_id)

    progress = await build_unlock_progress_context(
        session,
        trainee_id=trainee_id,
        node_ids=relevant_ids,
    )
    result = await resolve_node_access_with_grant(
        session,
        trainee_id=trainee_id,
        node_id=node_id,
        space_id=space_id,
        tree=tree,
        progress=progress,
    )
    if result.status == "prerequisite_locked":
        raise NodePrerequisiteLockedException(
            unlock_message=result.unlock_message
            or prerequisite_message(result.blocked_by_title or "the previous topic"),
            blocked_by_node_id=result.blocked_by_node_id,
            blocked_by_title=result.blocked_by_title,
        )
    return result


async def grant_node_unlock(
    session: AsyncSession,
    *,
    trainee_id: UUID,
    node_id: UUID,
    space_id: UUID,
    gate_node_id: UUID | None,
    source: UnlockSource = "parent_completed",
) -> bool:
    """Idempotent durable grant. Returns True when a new row was written."""
    repo = TraineeNodeUnlockRepository(session)
    return await repo.grant_unlock(
        trainee_id=trainee_id,
        node_id=node_id,
        space_id=space_id,
        gate_node_id=gate_node_id,
        source=source,
    )


async def batch_grant_children_on_parent_completed(
    session: AsyncSession,
    *,
    trainee_id: UUID,
    parent_id: UUID,
    space_id: UUID,
    tree: UnlockTreeContext | None = None,
    source: UnlockSource = "parent_completed",
) -> list[UUID]:
    """Grant durable unlocks for all eligible direct children of *parent_id*.

    Returns newly written child node ids (for optional toast payload).
    """
    ctx = tree or await build_unlock_tree_context(session, space_id=space_id)
    repo = TraineeNodeUnlockRepository(session)
    newly_unlocked: list[UUID] = []
    for child_id in eligible_children_for_unlock(parent_id, ctx):
        written = await repo.grant_unlock(
            trainee_id=trainee_id,
            node_id=child_id,
            space_id=space_id,
            gate_node_id=parent_id,
            source=source,
        )
        if written:
            newly_unlocked.append(child_id)
    return newly_unlocked


async def grant_unlocks_after_node_completed(
    session: AsyncSession,
    *,
    trainee_id: UUID,
    completed_node_id: UUID,
    space_id: UUID,
) -> list[UUID]:
    """Batch-grant after a learning unit flips to completed for a trainee."""
    return await batch_grant_children_on_parent_completed(
        session,
        trainee_id=trainee_id,
        parent_id=completed_node_id,
        space_id=space_id,
        source="parent_completed",
    )


async def resolve_node_access_with_grant(
    session: AsyncSession,
    *,
    trainee_id: UUID,
    node_id: UUID,
    space_id: UUID,
    tree: UnlockTreeContext,
    progress: UnlockProgressContext,
) -> AccessResult:
    """Resolve access and lazily write a durable grant when parent is complete.

    Covers pre-feature trainees and races where completion wrote progress
    but the batch grant did not land yet.
    """
    result = resolve_node_access(node_id=node_id, tree=tree, progress=progress)
    if result.status != "available":
        return result

    parent_id = tree.parent_by_node.get(node_id)
    if not is_parent_learning_unit(parent_id, tree.published_node_ids):
        return result
    assert parent_id is not None

    if node_id in progress.unlocked_node_ids:
        return result

    parent_complete = is_progress_complete(
        progress.progress_by_node.get(parent_id),
        node_id=parent_id,
        quiz_published_node_ids=progress.quiz_published_node_ids,
    )
    if not parent_complete:
        return result

    written = await grant_node_unlock(
        session,
        trainee_id=trainee_id,
        node_id=node_id,
        space_id=space_id,
        gate_node_id=parent_id,
        source="backfill",
    )
    return AccessResult(
        status="available",
        newly_granted=written,
    )


async def grant_unlocks_for_completed_trainees_on_node(
    session: AsyncSession,
    *,
    node_id: UUID,
    space_id: UUID,
) -> int:
    """Batch-grant children for every trainee who currently completes *node_id*.

    Uses **live** completion (published-quiz flag + progress fields), not only
    stored ``completion_status``, so C3 quiz-unpublish and threshold lowers
    grant correctly even when the cached status column is briefly stale.

    Does **not** revoke grants when a raise makes the parent incomplete (C1/C2).
    Returns the number of trainees processed (not grant count).
    """
    result = await session.execute(
        select(TraineeNodeProgress).where(
            and_(
                TraineeNodeProgress.node_id == node_id,
                TraineeNodeProgress.space_id == space_id,
            )
        )
    )
    rows = list(result.scalars().all())
    if not rows:
        return 0

    quiz_repo = TraineeQuizRepository(session)
    quiz_published_node_ids = await quiz_repo.get_published_quiz_node_ids([node_id])
    has_published_quiz = node_id in quiz_published_node_ids

    tree = await build_unlock_tree_context(session, space_id=space_id)
    processed = 0
    for row in rows:
        if not is_learning_unit_complete(
            study_material_completed=row.study_material_completed,
            quiz_passed=row.quiz_passed,
            study_material_read_percent=row.study_material_read_percent,
            quiz_attempt_count=row.quiz_attempt_count,
            has_published_quiz=has_published_quiz,
        ):
            continue
        await batch_grant_children_on_parent_completed(
            session,
            trainee_id=row.trainee_id,
            parent_id=node_id,
            space_id=space_id,
            tree=tree,
            source="parent_completed",
        )
        processed += 1
    await session.flush()
    return processed


async def grant_unlocks_after_child_content_published(
    session: AsyncSession,
    *,
    node_id: UUID,
    space_id: UUID,
) -> int:
    """When a node gains accessible content, grant it under a completed gate parent.

    Covers late-published children: parent completed earlier while this node was
    still ``coming_soon``, so the original batch grant skipped it. Idempotent.
    """
    tree = await build_unlock_tree_context(session, space_id=space_id)
    if not has_accessible_learning_content(
        node_id, tree.published_node_ids, tree.children_by_parent
    ):
        return 0

    parent_id = tree.parent_by_node.get(node_id)
    if not is_parent_learning_unit(parent_id, tree.published_node_ids):
        return 0
    assert parent_id is not None

    return await grant_unlocks_for_completed_trainees_on_node(
        session, node_id=parent_id, space_id=space_id
    )


async def clear_unlocks_for_reparented_node(
    session: AsyncSession, *, node_id: UUID
) -> int:
    """Delete durable grants for a moved node so placement rules re-apply."""
    repo = TraineeNodeUnlockRepository(session)
    return await repo.delete_unlocks_for_node(node_id)
