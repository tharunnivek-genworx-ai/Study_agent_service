"""Integration-style tests for QC checkpoint resume with frozen section state."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.api.control.study_agent.graph.resume_router import (
    hydrate_checkpoint_state,
    resolve_resume_next_node,
)
from src.api.control.study_agent.nodes.concept_checklist_node import (
    concept_checklist_node,
)
from src.api.control.study_agent.nodes.study_agent_node import study_agent_node
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    merge_section_patches,
)


def _qc_checkpoint_after_section_patch() -> dict:
    document = {
        "sections": [
            {
                "id": "s1",
                "heading": "Variables",
                "content": "Passing section content.",
            },
            {
                "id": "s2",
                "heading": "Loops",
                "content": "Needs patch.",
            },
        ]
    }
    return {
        "node_id": str(uuid4()),
        "generation_mode": "generate",
        "node_title": "Python Basics",
        "effective_instruction": "Teach Python fundamentals.",
        "must_cover_checklist": [
            {"id": "c1", "concept": "variables", "section_id": "s1"},
            {"id": "c2", "concept": "loops", "section_id": "s2"},
        ],
        "topic_split": [{"id": "s1"}, {"id": "s2"}],
        "domain": "Programming",
        "generated_content": json.dumps(document),
        "qc_attempt": 1,
        "qc_retry_mode": "section_patch",
        "qc_reverify_section_ids": ["s2"],
        "qc_frozen_check_ids": ["c1"],
        "qc_frozen_section_keys": ["s1"],
        "qc_section_failures": [
            {
                "section_id": "s2",
                "heading": "Loops",
                "current_section_json": document["sections"][1],
                "failures": [
                    {
                        "category": "content_accuracy",
                        "evidence": "Example too shallow",
                        "corrective_hint": "Add a runnable loop example",
                    }
                ],
            }
        ],
        "qc_result": {
            "overall_status": "fail",
            "checks": [],
        },
    }


def test_resume_after_qc_section_patch_routes_to_study_agent_not_checklist() -> None:
    checkpoint = _qc_checkpoint_after_section_patch()
    hydrated = hydrate_checkpoint_state(
        checkpoint,
        last_completed_node="quality_check",
    )
    assert (
        resolve_resume_next_node(hydrated, last_completed_node="quality_check")
        == "study_agent"
    )


def test_resume_after_qc_skips_concept_checklist_llm() -> None:
    checkpoint = _qc_checkpoint_after_section_patch()
    hydrated = hydrate_checkpoint_state(
        checkpoint,
        last_completed_node="quality_check",
    )

    async def _run() -> dict:
        with patch(
            "src.api.control.study_agent.nodes.concept_checklist_node.call_groq_with_rotation",
            new_callable=AsyncMock,
        ) as mock_checklist_llm:
            result = await concept_checklist_node(hydrated, config={})
        mock_checklist_llm.assert_not_called()
        return result

    result = asyncio.run(_run())
    assert result["must_cover_checklist"] == checkpoint["must_cover_checklist"]
    assert result["domain"] == "Programming"


def test_resume_section_patch_uses_checkpoint_failures_and_frozen_sections() -> None:
    checkpoint = _qc_checkpoint_after_section_patch()
    hydrated = hydrate_checkpoint_state(
        checkpoint,
        last_completed_node="quality_check",
    )

    captured_patch_sections: list[dict] = []

    async def fake_call_llm(**kwargs: object) -> MagicMock:
        del kwargs
        patch_payload = [
            {
                "id": "s2",
                "heading": "Loops",
                "content": "Updated loop section with runnable example.",
            }
        ]
        captured_patch_sections.extend(patch_payload)
        result = MagicMock()
        result.ok = True
        result.content = json.dumps({"sections": patch_payload})
        result.model = "llama-3.3-70b-versatile"
        result.token_usage = 42
        result.error_type = None
        return result

    async def _run() -> dict:
        with (
            patch(
                "src.api.utils.study_agent_utils.graph.node_helpers.call_and_parse_sections",
                new_callable=AsyncMock,
                side_effect=lambda state, **kwargs: (
                    [
                        {
                            "id": "s2",
                            "heading": "Loops",
                            "content": "Updated loop section with runnable example.",
                        }
                    ],
                    "SYSTEM:\n...\n\nUSER:\n...",
                    MagicMock(ok=True, model="llama-3.3-70b-versatile", token_usage=42),
                    "llama-3.3-70b-versatile",
                    42,
                ),
            ),
            patch(
                "src.api.control.study_agent.nodes.study_agent_node._call_study_revision_llm",
                new_callable=AsyncMock,
                side_effect=fake_call_llm,
            ),
            patch(
                "src.api.control.study_agent.nodes.study_agent_node.helpers.log_study_output",
            ),
            patch(
                "src.api.utils.study_agent_utils.graph.node_helpers.log_study_output",
            ),
        ):
            return await study_agent_node(hydrated, config={})

    result = asyncio.run(_run())

    assert "error" not in result
    document = json.loads(result["generated_content"])
    merge_result = merge_section_patches(
        json.loads(checkpoint["generated_content"]),
        [
            {
                "id": "s2",
                "heading": "Loops",
                "content": "Updated loop section with runnable example.",
            }
        ],
    )
    assert merge_result.document["sections"][0]["content"] == "Passing section content."
    assert hydrated["qc_frozen_section_keys"] == ["s1"]
    assert hydrated["qc_section_failures"][0]["section_id"] == "s2"
    assert any(section["id"] == "s1" for section in document["sections"])
    assert any(section["id"] == "s2" for section in document["sections"])
