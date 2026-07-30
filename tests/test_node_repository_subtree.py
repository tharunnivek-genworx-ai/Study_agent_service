from unittest.mock import MagicMock
from uuid import uuid4

from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.repositories.space_node_repository.node_repository import (
    _path_ancestors,
)


def test_path_ancestors_preserves_root_to_parent_order() -> None:
    root_id = uuid4()
    parent_id = uuid4()
    node_id = uuid4()
    root = MagicMock(spec=TopicNode)
    parent = MagicMock(spec=TopicNode)
    node = MagicMock(spec=TopicNode)

    ancestors = _path_ancestors(
        [root_id, parent_id, node_id],
        {node_id: node, root_id: root, parent_id: parent},
    )

    assert ancestors == [root, parent]


def test_path_ancestors_excludes_current_node_and_missing_rows() -> None:
    root_id = uuid4()
    missing_parent_id = uuid4()
    node_id = uuid4()
    root = MagicMock(spec=TopicNode)
    node = MagicMock(spec=TopicNode)

    ancestors = _path_ancestors(
        [root_id, missing_parent_id, node_id],
        {root_id: root, node_id: node},
    )

    assert ancestors == [root]
