"""Confirm reference_mode for PDF / external / none routing (design §2.2)."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig

from src.api.control.study_agent.states.state import StudyMaterialGraphState

ReferenceMode = Literal["pdf", "external", "none"]


def resolve_reference_mode(state: StudyMaterialGraphState) -> ReferenceMode:
    """Derive reference_mode from state flags (request may also preset it)."""
    # Toggle wins over a stale preset so regenerate/improve can enable research.
    if state.get("external_research_enabled"):
        return "external"

    existing = state.get("reference_mode")
    if existing in ("pdf", "external", "none"):
        return existing

    if state.get("has_reference_material") or state.get("reference_material_id"):
        return "pdf"

    return "none"


async def reference_router_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Thin node: set/confirm ``reference_mode`` before PDF vs external vs none."""
    del config
    mode = resolve_reference_mode(state)
    if state.get("reference_mode") == mode:
        return {}
    return {"reference_mode": mode}
