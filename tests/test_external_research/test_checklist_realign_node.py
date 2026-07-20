"""Unit tests for checklist_realign_node behavior."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.control.study_agent.nodes.checklist_realign_node import (
    checklist_realign_node,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult

_REPORT_PATCH = "src.api.utils.generation_progress.reporter.maybe_report_node_enter"


def _draft_state(**overrides):
    base = {
        "node_id": uuid4(),
        "node_title": "React Hooks",
        "reference_mode": "external",
        "domain": "Programming",
        "topic_split": [
            {"id": "ts_1", "heading": "useState", "purpose": "State basics"},
        ],
        "must_cover_checklist": [
            {
                "id": "mc_1",
                "concept": "useState",
                "requirement": "Explain useState",
                "priority": "required",
                "section_id": "ts_1",
                "depth_gate": "Runnable example shown.",
            }
        ],
        "checklist_llm_model_used": "draft-model",
        "ground_truth_reference": "- useState(initial) returns [value, setValue]",
        "extracted_reference_text": "- useState(initial) returns [value, setValue]",
        "effective_instruction": "Teach Hooks clearly.",
        "external_research_status": "success",
        "external_source_urls": [],
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_realign_skips_llm_when_no_ground_truth() -> None:
    state = _draft_state(
        ground_truth_reference="",
        extracted_reference_text="",
    )
    with (
        patch(_REPORT_PATCH, new_callable=AsyncMock),
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "_maybe_attach_source_urls",
            new_callable=AsyncMock,
        ) as attach,
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "call_groq_with_rotation",
            new_callable=AsyncMock,
        ) as llm,
    ):
        result = await checklist_realign_node(state, {})

    llm.assert_not_called()
    attach.assert_awaited_once()
    assert result["must_cover_checklist"] == state["must_cover_checklist"]
    assert result["domain"] == "Programming"
    assert result["topic_split"] == state["topic_split"]


@pytest.mark.asyncio
async def test_realign_success_overwrites_checklist_keeps_draft_domain() -> None:
    realigned = {
        "domain": "STEM",  # must be ignored — domain stays draft
        "topic_split": [
            {
                "id": "ts_1",
                "heading": "useState",
                "purpose": "State + Rules of Hooks",
            }
        ],
        "must_cover_checklist": [
            {
                "id": "mc_1",
                "concept": "useState",
                "requirement": "Implement useState with Rules of Hooks",
                "priority": "required",
                "section_id": "ts_1",
                "depth_gate": (
                    "At least one self-contained, runnable code block "
                    "demonstrating useState; explanation states output."
                ),
            }
        ],
    }
    state = _draft_state()
    llm_result = GroqCallResult(
        ok=True,
        content=json.dumps(realigned),
        model="realign-model",
    )

    with (
        patch(_REPORT_PATCH, new_callable=AsyncMock),
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "_maybe_attach_source_urls",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "call_groq_with_rotation",
            new_callable=AsyncMock,
            return_value=llm_result,
        ),
        patch(
            "src.api.utils.study_agent_utils.graph.node_helpers."
            "groq_api_keys_configured",
            return_value=True,
        ),
    ):
        result = await checklist_realign_node(state, {})

    assert result["domain"] == "Programming"
    assert result["must_cover_checklist"][0]["concept"] == "useState"
    assert "Rules of Hooks" in result["must_cover_checklist"][0]["requirement"]
    assert result["checklist_llm_model_used"] == "realign-model"


@pytest.mark.asyncio
async def test_realign_llm_failure_keeps_draft() -> None:
    state = _draft_state()
    llm_result = GroqCallResult(ok=False, error_type="rate_limit", content=None)

    with (
        patch(_REPORT_PATCH, new_callable=AsyncMock),
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "_maybe_attach_source_urls",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "call_groq_with_rotation",
            new_callable=AsyncMock,
            return_value=llm_result,
        ),
        patch(
            "src.api.utils.study_agent_utils.graph.node_helpers."
            "groq_api_keys_configured",
            return_value=True,
        ),
    ):
        result = await checklist_realign_node(state, {})

    assert result["must_cover_checklist"] == state["must_cover_checklist"]
    assert result["topic_split"] == state["topic_split"]
    assert result["checklist_llm_model_used"] == "draft-model"


@pytest.mark.asyncio
async def test_realign_calls_attach_when_urls_present() -> None:
    node_id = uuid4()
    space_id = uuid4()
    mentor_id = uuid4()
    urls = ["https://example.com/hooks", "https://react.dev/reference/react/useState"]
    state = _draft_state(
        node_id=node_id,
        external_source_urls=urls,
        ground_truth_reference="",
        extracted_reference_text="",
    )
    mock_node = MagicMock()
    mock_node.space_id = space_id
    mock_session = MagicMock()
    config = {
        "configurable": {
            "session": mock_session,
            "user_id": str(mentor_id),
        }
    }

    with (
        patch(_REPORT_PATCH, new_callable=AsyncMock),
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node.NodeRepository"
        ) as repo_cls,
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "attach_source_urls_to_node_media",
            new_callable=AsyncMock,
        ) as attach,
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "call_groq_with_rotation",
            new_callable=AsyncMock,
        ) as llm,
    ):
        repo_cls.return_value.get_node_by_id = AsyncMock(return_value=mock_node)
        await checklist_realign_node(state, config)

    llm.assert_not_called()
    attach.assert_awaited_once()
    kwargs = attach.await_args.kwargs
    assert kwargs["node_id"] == node_id
    assert kwargs["space_id"] == space_id
    assert kwargs["mentor_id"] == mentor_id
    assert kwargs["status"] == "success"
    assert kwargs["source_urls"] == urls


@pytest.mark.asyncio
async def test_realign_attaches_videos_on_fail_soft_without_article_success() -> None:
    node_id = uuid4()
    space_id = uuid4()
    mentor_id = uuid4()
    videos = [
        {
            "url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "title": "React Hooks Explained",
            "channel": "Code Channel",
            "duration_sec": 600,
            "views": 10000,
            "likes": 500,
            "score": 123.4,
        }
    ]
    state = _draft_state(
        node_id=node_id,
        external_research_status="fail_soft",
        external_source_urls=[],
        external_video_urls=videos,
        ground_truth_reference="",
        extracted_reference_text="",
    )
    mock_node = MagicMock()
    mock_node.space_id = space_id
    mock_session = MagicMock()
    config = {
        "configurable": {
            "session": mock_session,
            "user_id": str(mentor_id),
        }
    }

    with (
        patch(_REPORT_PATCH, new_callable=AsyncMock),
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node.NodeRepository"
        ) as repo_cls,
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "attach_source_urls_to_node_media",
            new_callable=AsyncMock,
        ) as attach_articles,
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "attach_video_urls_to_node_media",
            new_callable=AsyncMock,
        ) as attach_videos,
        patch(
            "src.api.control.study_agent.nodes.checklist_realign_node."
            "call_groq_with_rotation",
            new_callable=AsyncMock,
        ) as llm,
    ):
        repo_cls.return_value.get_node_by_id = AsyncMock(return_value=mock_node)
        await checklist_realign_node(state, config)

    llm.assert_not_called()
    attach_articles.assert_not_awaited()
    attach_videos.assert_awaited_once()
    kwargs = attach_videos.await_args.kwargs
    assert kwargs["node_id"] == node_id
    assert kwargs["space_id"] == space_id
    assert kwargs["mentor_id"] == mentor_id
    assert kwargs["video_urls"] == videos
