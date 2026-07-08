from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.utils.space_node_utils.build_node import (
    format_effective_instruction,
    resolve_effective_instruction_parts,
)


@dataclass(frozen=True)
class SubtreePreviewNode:
    """Precomputed subtree node payload used by batch-preview planning.

    Includes structural traversal metadata (`depth_level`, path ids/titles) and
    instruction inheritance analysis so service layer can build warnings without
    recalculating ancestor context.
    """

    node: TopicNode
    depth_level: int
    path_node_ids: list[UUID]
    path_titles: list[str]
    effective_instruction: str
    has_effective_instruction: bool
    inherits_section_default: bool


class NodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_node_by_id(self, node_id: UUID) -> TopicNode | None:
        result = await self.db.execute(
            select(TopicNode).where(TopicNode.node_id == node_id)
        )
        return cast(TopicNode | None, result.scalars().first())

    async def get_ancestors(self, node: TopicNode) -> list[TopicNode]:
        """Return ancestor nodes ordered root → parent (exclusive of *node*)."""
        ancestors: list[TopicNode] = []
        current_parent_id = node.parent_id

        while current_parent_id is not None:
            parent = await self.get_node_by_id(current_parent_id)
            if parent is None:
                break
            ancestors.append(parent)
            current_parent_id = parent.parent_id

        ancestors.reverse()
        return ancestors

    async def get_space_root_nodes(self, space_id: UUID) -> list[TopicNode]:
        """Return active root nodes for a space ordered for stable UI display."""
        result = await self.db.execute(
            select(TopicNode)
            .where(
                TopicNode.space_id == space_id,
                TopicNode.parent_id.is_(None),
                TopicNode.is_active.is_(True),
            )
            .order_by(TopicNode.order_index.asc(), TopicNode.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_subtree_nodes_preorder(
        self, root_node_id: UUID
    ) -> list[SubtreePreviewNode]:
        """Return root + descendants in stable depth-first preorder.

        Implementation notes:
        - Uses recursive CTE to support arbitrary depth trees.
        - Builds a deterministic textual `sort_key` based on sibling order index
          plus node id to keep ordering stable even for equal order indexes.
        - After traversal, enriches each row with effective-instruction analysis
          used by batch preview warnings.
        """
        traversal_query = text(
            """
            WITH RECURSIVE subtree AS (
                SELECT
                    n.nodeid AS node_id,
                    n.parentid AS parent_id,
                    1 AS depth_level,
                    ARRAY[n.nodeid]::uuid[] AS path_node_ids,
                    ARRAY[n.title]::text[] AS path_titles,
                    ARRAY[
                        lpad(n.orderindex::text, 10, '0') || ':' || n.nodeid::text
                    ]::text[] AS sort_key
                FROM topicnodes n
                WHERE n.nodeid = :root_node_id
                  AND n.isactive = TRUE

                UNION ALL

                SELECT
                    c.nodeid AS node_id,
                    c.parentid AS parent_id,
                    st.depth_level + 1 AS depth_level,
                    (st.path_node_ids || c.nodeid)::uuid[] AS path_node_ids,
                    (st.path_titles || c.title)::text[] AS path_titles,
                    (
                        st.sort_key ||
                        (lpad(c.orderindex::text, 10, '0') || ':' || c.nodeid::text)
                    )::text[] AS sort_key
                FROM topicnodes c
                JOIN subtree st ON st.node_id = c.parentid
                WHERE c.isactive = TRUE
            )
            SELECT
                node_id,
                depth_level,
                path_node_ids,
                path_titles
            FROM subtree
            ORDER BY sort_key
            """
        )
        traversal_rows = (
            await self.db.execute(traversal_query, {"root_node_id": root_node_id})
        ).mappings()
        raw_rows = list(traversal_rows.all())
        if not raw_rows:
            return []

        node_ids_in_order = [cast(UUID, row["node_id"]) for row in raw_rows]
        nodes_result = await self.db.execute(
            select(TopicNode).where(TopicNode.node_id.in_(node_ids_in_order))
        )
        node_by_id = {node.node_id: node for node in nodes_result.scalars().all()}

        preview_nodes: list[SubtreePreviewNode] = []
        for row in raw_rows:
            node_id = cast(UUID, row["node_id"])
            node = node_by_id.get(node_id)
            if node is None:
                continue

            ancestors = await self.get_ancestors(node)
            instruction_parts = resolve_effective_instruction_parts(node, ancestors)
            effective_instruction = format_effective_instruction(instruction_parts)

            path_node_ids = [
                UUID(str(v)) for v in cast(list[Any], row["path_node_ids"])
            ]
            path_titles = [str(v) for v in cast(list[Any], row["path_titles"])]

            preview_nodes.append(
                SubtreePreviewNode(
                    node=node,
                    depth_level=int(row["depth_level"]),
                    path_node_ids=path_node_ids,
                    path_titles=path_titles,
                    effective_instruction=effective_instruction,
                    has_effective_instruction=bool(instruction_parts),
                    # True when any instruction part comes from an ancestor.
                    inherits_section_default=any(
                        part.type == "inherited" for part in instruction_parts
                    ),
                )
            )

        return preview_nodes
