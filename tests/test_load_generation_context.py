# tests/test_load_generation_context.py
"""Tests for quiz generation context loading."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.api.control.quiz_agent.nodes.quiz_graph.load_generation_context_node import (
    load_generation_context,
)


class TestLoadGenerationContextStudyMaterialSource:
    def test_uses_active_version_when_newer_workspace_draft_is_empty(self) -> None:
        """Mentor quiz work must match get_mentor_quiz_study_material_source semantics."""

        async def _run() -> None:
            node_id = uuid4()
            mentor_id = uuid4()
            space_id = uuid4()
            active_version_id = uuid4()

            active_version = SimpleNamespace(
                version_id=active_version_id,
                content="Active study material body.",
                concept_plan=None,
            )
            empty_draft = SimpleNamespace(
                version_id=uuid4(),
                content="   ",
                concept_plan=None,
            )

            mock_node = SimpleNamespace(space_id=space_id, title="Topic A")
            mock_repo = MagicMock()
            mock_repo.get_published_version = AsyncMock(return_value=None)
            mock_repo.get_active_version = AsyncMock(return_value=active_version)
            mock_repo.get_latest_workspace_draft = AsyncMock(return_value=empty_draft)

            state = {"node_id": node_id, "mentor_id": mentor_id}
            config = {"configurable": {"session": MagicMock()}}

            with (
                patch(
                    "src.api.control.quiz_agent.nodes.quiz_graph.load_generation_context_node._get_node_and_assert_space_access",
                    AsyncMock(return_value=mock_node),
                ),
                patch(
                    "src.api.control.quiz_agent.nodes.quiz_graph.load_generation_context_node.StudyMaterialRepository",
                    return_value=mock_repo,
                ),
            ):
                result = await load_generation_context(state, config)  # type: ignore[arg-type]

            assert result["study_material_version_id"] == active_version_id
            assert result["study_material_content"] == "Active study material body."
            assert result["node_title"] == "Topic A"
            assert result["space_id"] == space_id

        asyncio.run(_run())
