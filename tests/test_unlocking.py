"""Unit tests for progressive subtopic unlock resolve / eligibility rules."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.api.schemas.progress_schemas import TraineeNodeProgressBatchItemOut
from src.api.utils.trainee_progress_utils.unlocking import (
    UnlockProgressContext,
    UnlockTreeContext,
    clear_unlocks_for_reparented_node,
    eligible_children_for_unlock,
    is_parent_learning_unit,
    resolve_node_access,
)


def _tree(
    *,
    parent_id,
    child_ids,
    published,
    titles=None,
):
    children_by_parent = {None: [parent_id], parent_id: list(child_ids)}
    parent_by_node = {parent_id: None}
    for child_id in child_ids:
        parent_by_node[child_id] = parent_id
    node_titles = {parent_id: "Parent"}
    node_titles.update(titles or {cid: f"Child-{i}" for i, cid in enumerate(child_ids)})
    return UnlockTreeContext(
        children_by_parent=children_by_parent,
        published_node_ids=set(published),
        node_titles=node_titles,
        parent_by_node=parent_by_node,
    )


def _progress(*, unlocked=(), snapshots=None, quiz_nodes=()):
    return UnlockProgressContext(
        progress_by_node=dict(snapshots or {}),
        quiz_published_node_ids=set(quiz_nodes),
        unlocked_node_ids=set(unlocked),
    )


def _snap(node_id, *, completed=False, quiz_passed=False, read=0, attempts=0):
    return TraineeNodeProgressBatchItemOut(
        node_id=node_id,
        study_material_read_percent=100 if completed else read,
        study_material_completed=completed,
        quiz_passed=quiz_passed,
        quiz_attempt_count=attempts,
        completion_status=(
            "completed"
            if completed and quiz_passed
            else (
                "in_progress"
                if completed or quiz_passed or read > 0 or attempts > 0
                else "not_started"
            )
        ),
        progress_percentage=(50 if completed else 0) + (50 if quiz_passed else 0),
    )


def test_root_with_content_is_available():
    root = uuid4()
    tree = UnlockTreeContext(
        children_by_parent={None: [root]},
        published_node_ids={root},
        node_titles={root: "Root"},
        parent_by_node={root: None},
    )
    result = resolve_node_access(node_id=root, tree=tree, progress=_progress())
    assert result.status == "available"


def test_no_accessible_content_is_coming_soon():
    parent = uuid4()
    child = uuid4()
    tree = _tree(parent_id=parent, child_ids=[child], published=set())
    result = resolve_node_access(node_id=child, tree=tree, progress=_progress())
    assert result.status == "coming_soon"


def test_pure_parent_does_not_gate_children():
    parent = uuid4()
    child = uuid4()
    # Parent has no published SM; child does → pure parent, no gate
    tree = _tree(parent_id=parent, child_ids=[child], published={child})
    assert not is_parent_learning_unit(parent, tree.published_node_ids)
    result = resolve_node_access(node_id=child, tree=tree, progress=_progress())
    assert result.status == "available"


def test_gated_child_locked_when_parent_incomplete():
    parent = uuid4()
    child = uuid4()
    tree = _tree(
        parent_id=parent,
        child_ids=[child],
        published={parent, child},
        titles={child: "Intro"},
    )
    tree.node_titles[parent] = "Basics"
    result = resolve_node_access(
        node_id=child,
        tree=tree,
        progress=_progress(snapshots={parent: _snap(parent, completed=False, read=40)}),
    )
    assert result.status == "prerequisite_locked"
    assert result.blocked_by_node_id == parent
    assert result.blocked_by_title == "Basics"
    assert result.unlock_message == "Finish Basics first"


def test_durable_unlock_keeps_child_available_after_parent_reset():
    """C1/C2: parent no longer complete, but durable grant keeps child open."""
    parent = uuid4()
    child = uuid4()
    tree = _tree(parent_id=parent, child_ids=[child], published={parent, child})
    result = resolve_node_access(
        node_id=child,
        tree=tree,
        progress=_progress(
            unlocked={child},
            snapshots={parent: _snap(parent, completed=False)},
        ),
    )
    assert result.status == "available"


def test_parent_complete_makes_child_available_without_grant_yet():
    parent = uuid4()
    child = uuid4()
    tree = _tree(parent_id=parent, child_ids=[child], published={parent, child})
    result = resolve_node_access(
        node_id=child,
        tree=tree,
        progress=_progress(
            snapshots={
                parent: _snap(parent, completed=True, quiz_passed=True, attempts=1)
            },
            quiz_nodes={parent},
        ),
    )
    assert result.status == "available"


def test_c6_unpublish_parent_drops_gate():
    """C6: parent SM unpublished → no longer a learning-unit gate."""
    parent = uuid4()
    child = uuid4()
    tree = _tree(parent_id=parent, child_ids=[child], published={child})
    result = resolve_node_access(node_id=child, tree=tree, progress=_progress())
    assert result.status == "available"


def test_batch_eligible_children_skips_coming_soon():
    parent = uuid4()
    ready = uuid4()
    empty = uuid4()
    tree = _tree(
        parent_id=parent,
        child_ids=[ready, empty],
        published={parent, ready},
    )
    assert eligible_children_for_unlock(parent, tree) == [ready]


def test_read_only_parent_complete_without_quiz():
    parent = uuid4()
    child = uuid4()
    tree = _tree(parent_id=parent, child_ids=[child], published={parent, child})
    result = resolve_node_access(
        node_id=child,
        tree=tree,
        progress=_progress(
            snapshots={parent: _snap(parent, completed=True, read=100)},
        ),
    )
    assert result.status == "available"


def test_parent_read_complete_but_quiz_not_passed_keeps_child_locked():
    parent = uuid4()
    child = uuid4()
    tree = _tree(parent_id=parent, child_ids=[child], published={parent, child})
    result = resolve_node_access(
        node_id=child,
        tree=tree,
        progress=_progress(
            snapshots={
                parent: _snap(parent, completed=True, quiz_passed=False, attempts=1)
            },
            quiz_nodes={parent},
        ),
    )
    assert result.status == "prerequisite_locked"


def test_child_with_published_descendant_is_unlock_eligible():
    parent = uuid4()
    child = uuid4()
    grandchild = uuid4()
    tree = UnlockTreeContext(
        children_by_parent={
            None: [parent],
            parent: [child],
            child: [grandchild],
        },
        published_node_ids={parent, grandchild},
        node_titles={parent: "Parent", child: "Section", grandchild: "Lesson"},
        parent_by_node={parent: None, child: parent, grandchild: child},
    )
    assert eligible_children_for_unlock(parent, tree) == [child]


def test_find_next_up_skips_prerequisite_locked_siblings():
    from types import SimpleNamespace

    from src.api.utils.trainee_study_utils.tree_navigation import find_next_up

    current = uuid4()
    locked = uuid4()
    available = uuid4()
    parent = uuid4()
    siblings = [
        SimpleNamespace(node_id=current, title="Current", order_index=0),
        SimpleNamespace(node_id=locked, title="Locked", order_index=1),
        SimpleNamespace(node_id=available, title="Open", order_index=2),
    ]
    published = {current, locked, available}
    children_by_parent = {parent: [current, locked, available]}
    result = find_next_up(
        siblings[0],
        siblings,
        published,
        children_by_parent,
        parent=SimpleNamespace(node_id=parent, title="Parent"),
        navigable_node_ids={available},
    )
    assert result == (available, "Open", "Next up")


def test_reparent_clear_deletes_all_durable_grants_for_moved_node():
    node_id = uuid4()
    repo = MagicMock()
    repo.delete_unlocks_for_node = AsyncMock(return_value=3)
    with patch(
        "src.api.utils.trainee_progress_utils.unlocking.TraineeNodeUnlockRepository",
        return_value=repo,
    ):
        deleted = asyncio.run(
            clear_unlocks_for_reparented_node(MagicMock(), node_id=node_id)
        )
    assert deleted == 3
    repo.delete_unlocks_for_node.assert_awaited_once_with(node_id)
