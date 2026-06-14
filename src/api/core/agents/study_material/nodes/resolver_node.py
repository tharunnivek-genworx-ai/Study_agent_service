"""Resolve effective teaching instruction and optional reference material."""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from src.api.core.agents.study_material.state import StudyMaterialGraphState
from src.api.core.exceptions.study_material_exceptions.reference_material_exceptions import (  # noqa: E501
    ReferenceMaterialNotFoundForDeleteException,
)
from src.api.data.repositories.space_node_repository.node_repository import (
    NodeRepository,
)
from src.api.data.repositories.study_agent_repositories.reference_material_repository import (  # noqa: E501
    ReferenceMaterialRepository,
)
from src.api.utils.space_node_utils.build_node import (
    format_effective_instruction,
    resolve_effective_instruction_parts,
)
from src.api.utils.study_agent_utils.reference_download import (
    download_reference_to_temp,
)


async def resolve_instruction_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    configurable = config.get("configurable") or {}
    session = configurable.get("session")
    if session is None:
        return {"error": "Database session is required for instruction resolution."}

    node_id = state.get("node_id")
    if node_id is None:
        return {"error": "node_id is required."}

    node_repo = NodeRepository(session)
    node = await node_repo.get_node_by_id(node_id)
    if node is None:
        return {"error": f"Node not found: {node_id}"}

    ancestors = await node_repo.get_ancestors(node)
    instruction_parts = resolve_effective_instruction_parts(node, ancestors)
    effective_instruction = format_effective_instruction(instruction_parts)

    updates: dict[str, Any] = {
        "node_title": node.title,
        "effective_instruction": effective_instruction,
        "has_reference_material": False,
        "reference_file_path": None,
        "reference_file_is_temp": False,
    }

    reference_material_id = state.get("reference_material_id")
    if reference_material_id is None:
        return updates

    material_repo = ReferenceMaterialRepository(session)
    material = await material_repo.get_by_id(reference_material_id)
    if material is None or material.deleted_at is not None:
        raise ReferenceMaterialNotFoundForDeleteException()

    if material.space_id != node.space_id:
        raise ReferenceMaterialNotFoundForDeleteException()

    if material.scope == "node" and material.node_id != node_id:
        raise ReferenceMaterialNotFoundForDeleteException()

    resolved_path, is_temp = await download_reference_to_temp(
        material.file_url, material.file_name
    )
    updates["has_reference_material"] = True
    updates["reference_file_path"] = str(resolved_path)
    updates["reference_file_is_temp"] = is_temp
    updates["reference_material_title"] = material.title
    return updates
