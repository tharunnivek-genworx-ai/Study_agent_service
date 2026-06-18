"""Resolve which detail-panel layout applies to a topic node."""

from typing import Literal

NodePanelType = Literal["pure-parent", "mixed-parent", "leaf-available", "leaf-locked"]


def get_node_panel_type(
    *,
    has_study_material: bool,
    child_count: int,
) -> NodePanelType:
    """Map a node's shape to one of the four panel layouts from the UI spec.

    The frontend uses the same four cases; this function is the backend
    source of truth so panel_type in the API response always matches what
    the React router will render.

    Rules (from redesign spec):
      - Has children + no published material  → ``pure-parent``  (e.g. Hooks)
      - Has children + published material     → ``mixed-parent`` (e.g. React Fundamentals)
      - No children + published material      → ``leaf-available``
      - No children + no published material   → ``leaf-locked``
    """
    if child_count > 0:
        if has_study_material:
            return "mixed-parent"
        return "pure-parent"
    if has_study_material:
        return "leaf-available"
    return "leaf-locked"
