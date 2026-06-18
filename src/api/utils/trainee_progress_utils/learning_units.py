"""
Learning-unit counting for progress rollups.

A *learning unit* is any node in a subtree that has published study material.
These counts are used by the topic detail panel footer and subtopic completion
stats. They combine **tree shape** (``children_by_parent``, ``published_ids``)
with **progress snapshots** from ``TraineeProgressService``.
"""

from uuid import UUID

from src.api.schemas.progress_schemas.trainee_progress_schema import (
    TraineeNodeProgressBatchItemOut,
)
from src.api.utils.trainee_progress_utils.completion import is_learning_unit_complete


def collect_descendant_ids(
    root_id: UUID,
    children_by_parent: dict[UUID | None, list[UUID]],
) -> list[UUID]:
    """Return all descendant node ids for *root_id* (excluding the root)."""
    collected: list[UUID] = []

    def walk(parent_id: UUID) -> None:
        for child_id in children_by_parent.get(parent_id, []):
            collected.append(child_id)
            walk(child_id)

    walk(root_id)
    return collected


def count_learning_units(
    root_id: UUID,
    published_node_ids: set[UUID],
    children_by_parent: dict[UUID | None, list[UUID]],
) -> int:
    """Count published learning units in the subtree rooted at *root_id*."""
    total = 1 if root_id in published_node_ids else 0
    for child_id in collect_descendant_ids(root_id, children_by_parent):
        if child_id in published_node_ids:
            total += 1
    return total


def has_accessible_learning_content(
    root_id: UUID,
    published_node_ids: set[UUID],
    children_by_parent: dict[UUID | None, list[UUID]],
) -> bool:
    """True when *root_id* or any descendant has published study material."""
    return count_learning_units(root_id, published_node_ids, children_by_parent) > 0


def subtree_has_learning_activity(
    root_id: UUID,
    published_node_ids: set[UUID],
    children_by_parent: dict[UUID | None, list[UUID]],
    progress_by_node: dict[UUID, TraineeNodeProgressBatchItemOut],
) -> bool:
    """True when any published unit in the subtree has reading or quiz activity."""
    candidate_ids = [root_id, *collect_descendant_ids(root_id, children_by_parent)]
    for node_id in candidate_ids:
        if node_id not in published_node_ids:
            continue
        snapshot = progress_by_node.get(node_id)
        if snapshot is None:
            continue
        if snapshot.completion_status == "in_progress":
            return True
        if (
            snapshot.study_material_read_percent > 0
            and not snapshot.study_material_completed
        ):
            return True
        if snapshot.quiz_attempt_count > 0 and not snapshot.quiz_passed:
            return True
    return False


def sum_subtree_progress_percentage(
    root_id: UUID,
    published_node_ids: set[UUID],
    children_by_parent: dict[UUID | None, list[UUID]],
    progress_by_node: dict[UUID, TraineeNodeProgressBatchItemOut],
) -> int:
    """Sum of ``progress_percentage`` values across every published unit in the subtree.

    Each published unit contributes a value of 0–100 from its snapshot
    (already quiz-aware as recomputed by ``TraineeProgressService``).
    Divide by ``count_learning_units`` to get the weighted-average percentage.

    Examples:
      1 leaf read (no quiz)              → sum=100, avg=100 %
      1 leaf read, quiz published        → sum=50,  avg=50 %
      1 leaf read+quiz, 1 leaf not started → sum=100+0=100, avg=50 %
    """
    total = 0
    candidate_ids = [root_id, *collect_descendant_ids(root_id, children_by_parent)]
    for node_id in candidate_ids:
        if node_id not in published_node_ids:
            continue
        snapshot = progress_by_node.get(node_id)
        if snapshot is not None:
            total += snapshot.progress_percentage
    return total


def count_completed_learning_units(
    root_id: UUID,
    published_node_ids: set[UUID],
    children_by_parent: dict[UUID | None, list[UUID]],
    progress_by_node: dict[UUID, TraineeNodeProgressBatchItemOut],
    *,
    quiz_published_node_ids: set[UUID] | None = None,
) -> int:
    """Count learning units that meet current completion requirements."""
    quiz_nodes = quiz_published_node_ids or set()
    completed = 0
    candidate_ids = [root_id, *collect_descendant_ids(root_id, children_by_parent)]
    for node_id in candidate_ids:
        if node_id not in published_node_ids:
            continue
        snapshot = progress_by_node.get(node_id)
        if snapshot is None:
            continue
        if is_learning_unit_complete(
            study_material_completed=snapshot.study_material_completed,
            quiz_passed=snapshot.quiz_passed,
            study_material_read_percent=snapshot.study_material_read_percent,
            quiz_attempt_count=snapshot.quiz_attempt_count,
            has_published_quiz=node_id in quiz_nodes,
        ):
            completed += 1
    return completed
