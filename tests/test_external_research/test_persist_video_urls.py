"""Tests for external research cache persistence of video_urls."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.utils.external_research_utils.persist import (
    persist_external_research_cache,
)


@pytest.mark.asyncio
async def test_persist_passes_video_urls_on_fail_soft() -> None:
    node_id = uuid4()
    space_id = uuid4()
    mentor_id = uuid4()
    videos = [
        {
            "url": "https://www.youtube.com/watch?v=abc123",
            "video_id": "abc123",
            "title": "Topic overview",
            "channel": "Learn Channel",
            "duration_sec": 420,
            "views": 5000,
            "likes": 200,
            "score": 88.0,
        }
    ]
    mock_session = MagicMock()

    with patch(
        "src.api.utils.external_research_utils.persist.ExternalResearchRepository"
    ) as repo_cls:
        repo = repo_cls.return_value
        repo.create = AsyncMock()
        await persist_external_research_cache(
            mock_session,
            node_id=node_id,
            space_id=space_id,
            mentor_id=mentor_id,
            status="fail_soft",
            fail_reason="all_extractions_failed",
            search_query_used="React hooks tutorial",
            resolved_topic="React",
            resolved_subtopic="Hooks",
            ground_truth_reference=None,
            source_urls=[],
            video_urls=videos,
            per_website_summary_count=0,
            knowledge_distillation_model_used=None,
        )

    repo.create.assert_awaited_once()
    kwargs = repo.create.await_args.kwargs
    assert kwargs["video_urls"] == videos
    assert kwargs["status"] == "fail_soft"
    assert kwargs["source_urls"] == []
