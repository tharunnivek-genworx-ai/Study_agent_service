# tests/test_study_agent_retry.py
"""Unit tests for study_agent_node section-level QC retry paths."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.api.control.study_agent.nodes.study_agent_node import study_agent_node


def _doc(*sections: dict) -> dict:
    return {"sections": list(sections)}


def _groq_ok(content: dict) -> SimpleNamespace:
    return SimpleNamespace(
        ok=True,
        content=json.dumps(content),
        model="test-model",
        token_usage=42,
        error_type=None,
    )


@patch("src.api.control.study_agent.nodes.study_agent_node.llm_settings")
@patch(
    "src.api.control.study_agent.nodes.study_agent_node.call_groq_with_rotation",
    new_callable=AsyncMock,
)
def test_section_patch_merges_into_document_and_sets_fixed_sections(
    mock_groq: AsyncMock,
    mock_settings: SimpleNamespace,
) -> None:
    mock_settings.groq_api_key = "key"
    mock_settings.groq_api_key_2 = None
    mock_settings.groq_api_key_3 = None
    mock_settings.groq_api_key_4 = None
    mock_settings.llm_model = "test-model"

    mock_groq.return_value = _groq_ok(
        {
            "sections": [
                {"id": "mc_2", "heading": "Examples", "content": "fixed examples"},
            ]
        }
    )

    state = {
        "node_title": "Python Decorators",
        "effective_instruction": "Teach decorators clearly.",
        "generated_content": json.dumps(
            _doc(
                {"id": "mc_1", "heading": "Intro", "content": "intro"},
                {"id": "mc_2", "heading": "Examples", "content": "bad examples"},
            )
        ),
        "qc_retry_mode": "section_patch",
        "qc_section_failures": [
            {
                "section_id": "mc_2",
                "heading": "Examples",
                "failures": [
                    {
                        "category": "content_accuracy",
                        "evidence": "Wrong decorator syntax",
                        "corrective_hint": "Show @ syntax correctly",
                    }
                ],
            }
        ],
        "must_cover_checklist": [
            {"id": "mc_1", "concept": "Intro", "requirement": "Define decorators"},
            {"id": "mc_2", "concept": "Examples", "requirement": "Show usage"},
        ],
    }

    result = asyncio.run(study_agent_node(state, {}))

    doc = json.loads(result["generated_content"])
    assert doc["sections"][0]["content"] == "intro"
    assert doc["sections"][1]["content"] == "fixed examples"
    assert result["fixed_sections"] == [
        {"id": "mc_2", "heading": "Examples", "content": "fixed examples"},
    ]
    mock_groq.assert_awaited_once()


@patch("src.api.control.study_agent.nodes.study_agent_node.llm_settings")
@patch(
    "src.api.control.study_agent.nodes.study_agent_node.call_groq_with_rotation",
    new_callable=AsyncMock,
)
def test_section_patch_then_insert_runs_two_calls(
    mock_groq: AsyncMock,
    mock_settings: SimpleNamespace,
) -> None:
    mock_settings.groq_api_key = "key"
    mock_settings.groq_api_key_2 = None
    mock_settings.groq_api_key_3 = None
    mock_settings.groq_api_key_4 = None
    mock_settings.llm_model = "test-model"

    mock_groq.side_effect = [
        _groq_ok(
            {
                "sections": [
                    {"id": "mc_1", "heading": "Intro", "content": "fixed intro"},
                ]
            }
        ),
        _groq_ok(
            {
                "sections": [
                    {"id": "mc_2", "heading": "Examples", "content": "new examples"},
                ]
            }
        ),
    ]

    state = {
        "node_title": "Python Decorators",
        "effective_instruction": "Teach decorators clearly.",
        "generated_content": json.dumps(
            _doc({"id": "mc_1", "heading": "Intro", "content": "bad intro"})
        ),
        "qc_retry_mode": "section_patch_then_insert",
        "qc_section_failures": [
            {
                "section_id": "mc_1",
                "heading": "Intro",
                "failures": [
                    {
                        "category": "must_cover",
                        "evidence": "Incomplete intro",
                        "corrective_hint": "Expand intro",
                    }
                ],
            }
        ],
        "qc_missing_checklist_ids": ["mc_2"],
        "must_cover_checklist": [
            {"id": "mc_1", "concept": "Intro", "requirement": "Define decorators"},
            {"id": "mc_2", "concept": "Examples", "requirement": "Show usage"},
        ],
    }

    result = asyncio.run(study_agent_node(state, {}))

    doc = json.loads(result["generated_content"])
    assert len(doc["sections"]) == 2
    assert doc["sections"][0]["content"] == "fixed intro"
    assert doc["sections"][1]["content"] == "new examples"
    assert len(result["fixed_sections"]) == 2
    assert mock_groq.await_count == 2
