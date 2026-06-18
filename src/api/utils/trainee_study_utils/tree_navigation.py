"""Tree navigation helpers for trainee detail panel (breadcrumbs, siblings, next-up)."""

from uuid import UUID

from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode


def build_breadcrumbs(
    node: TopicNode,
    ancestors: list[TopicNode],
    *,
    max_levels: int = 3,
) -> list[tuple[UUID, str]]:
    """Return ancestor chain ending with the current node (max *max_levels*).

    Shown under the title in leaf panels. Ancestors are clickable in the
    frontend so the trainee can jump back up the tree.
    """
    chain = [*ancestors, node]
    if len(chain) > max_levels:
        chain = chain[-max_levels:]
    return [(item.node_id, item.title) for item in chain]


def find_available_siblings(
    node: TopicNode,
    siblings: list[TopicNode],
    published_node_ids: set[UUID],
    children_by_parent: dict[UUID | None, list[UUID]],
    *,
    limit: int = 2,
) -> list[tuple[UUID, str]]:
    """Return up to *limit* siblings with accessible content ordered by ``order_index``.

    Used by the locked-leaf "Meanwhile, continue with" chip row so trainees
    always have somewhere to go when the current lesson is unpublished.
    """
    from src.api.utils.trainee_progress_utils.learning_units import (
        has_accessible_learning_content,
    )

    results: list[tuple[UUID, str]] = []
    for sibling in siblings:
        if sibling.node_id == node.node_id:
            continue
        if not has_accessible_learning_content(
            sibling.node_id, published_node_ids, children_by_parent
        ):
            continue
        results.append((sibling.node_id, sibling.title))
        if len(results) >= limit:
            break
    return results


def find_next_up(
    node: TopicNode,
    siblings: list[TopicNode],
    published_node_ids: set[UUID],
    children_by_parent: dict[UUID | None, list[UUID]],
    *,
    parent: TopicNode | None = None,
) -> tuple[UUID, str, str] | None:
    """Return the next navigation target after *node* for the What's-next card.

    Returns ``(node_id, title, label_prefix)`` where *label_prefix* is
    ``"Next up"`` for a forward sibling or ``"Back to"`` for the parent fallback.
    """
    from src.api.utils.trainee_progress_utils.learning_units import (
        has_accessible_learning_content,
    )

    ordered = sorted(siblings, key=lambda item: item.order_index)
    seen_current = False
    for sibling in ordered:
        if sibling.node_id == node.node_id:
            seen_current = True
            continue
        if seen_current and has_accessible_learning_content(
            sibling.node_id, published_node_ids, children_by_parent
        ):
            return sibling.node_id, sibling.title, "Next up"
    if parent is not None:
        return parent.node_id, parent.title, "Back to"
    return None
