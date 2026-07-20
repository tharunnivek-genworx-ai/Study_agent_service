"""Graph tests for YouTube discovery routing and article-path isolation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.control.study_agent.graph.external_research_graph import (
    _route_after_cache_check,
    _route_after_youtube_discover,
    external_research_cache_check_node,
    external_research_youtube_discover_node,
)
from src.api.utils.external_research_utils.youtube_client import YouTubeApiError

_REPORT_PATCH = "src.api.utils.generation_progress.reporter.maybe_report_node_enter"


def _config(session: object | None = None, user_id: object | None = None) -> dict:
    return {
        "configurable": {
            "session": session or MagicMock(),
            "user_id": str(user_id or uuid4()),
        }
    }


@pytest.mark.asyncio
async def test_youtube_discover_failure_does_not_set_external_research_status() -> None:
    state = {
        "node_id": uuid4(),
        "external_research_query": "React hooks",
        "external_research_status": "success",
    }

    with (
        patch(_REPORT_PATCH, new_callable=AsyncMock),
        patch(
            "src.api.control.study_agent.graph.external_research_graph."
            "external_research_settings"
        ) as settings,
        patch(
            "src.api.control.study_agent.graph.external_research_graph.search_and_rank",
            side_effect=YouTubeApiError("quota exceeded", status_code=403),
        ),
    ):
        settings.youtube_api_key = "test-key"
        result = await external_research_youtube_discover_node(state, _config())

    assert result["youtube_attach_status"] == "failed"
    assert result["external_video_urls"] == []
    assert "external_research_status" not in result


@pytest.mark.asyncio
async def test_cache_hit_hydrates_external_video_urls() -> None:
    node_id = uuid4()
    videos = [
        {
            "url": "https://www.youtube.com/watch?v=hydrated",
            "video_id": "hydrated",
            "title": "Cached lesson",
            "channel": "Channel",
            "duration_sec": 600,
            "views": 1000,
            "likes": 50,
            "score": 40.0,
        }
    ]
    existing = MagicMock()
    existing.status = "success"
    existing.fail_reason = None
    existing.search_query_used = "React hooks"
    existing.resolved_topic = "React"
    existing.resolved_subtopic = "Hooks"
    existing.knowledge_distillation_model_used = "model"
    existing.ground_truth_reference = "GT notes"
    existing.source_urls = ["https://react.dev/hooks"]
    existing.video_urls = videos

    mock_repo = MagicMock()
    mock_repo.get_by_node_id = AsyncMock(return_value=existing)

    with (
        patch(_REPORT_PATCH, new_callable=AsyncMock),
        patch(
            "src.api.control.study_agent.graph.external_research_graph."
            "ExternalResearchRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.api.control.study_agent.graph.external_research_graph."
            "external_research_settings"
        ) as settings,
    ):
        settings.youtube_api_key = "test-key"
        result = await external_research_cache_check_node(
            {"node_id": node_id},
            _config(),
        )

    assert result["external_research_cache_hit"] is True
    assert result["external_video_urls"] == videos
    assert result["external_research_youtube_backfill_only"] is False


@pytest.mark.asyncio
async def test_cache_hit_with_empty_video_urls_sets_backfill_flag() -> None:
    node_id = uuid4()
    existing = MagicMock()
    existing.status = "fail_soft"
    existing.fail_reason = "all_extractions_failed"
    existing.search_query_used = "React hooks"
    existing.resolved_topic = "React"
    existing.resolved_subtopic = "Hooks"
    existing.knowledge_distillation_model_used = None
    existing.ground_truth_reference = None
    existing.source_urls = []
    existing.video_urls = []

    mock_repo = MagicMock()
    mock_repo.get_by_node_id = AsyncMock(return_value=existing)

    with (
        patch(_REPORT_PATCH, new_callable=AsyncMock),
        patch(
            "src.api.control.study_agent.graph.external_research_graph."
            "ExternalResearchRepository",
            return_value=mock_repo,
        ),
        patch(
            "src.api.control.study_agent.graph.external_research_graph."
            "external_research_settings"
        ) as settings,
    ):
        settings.youtube_api_key = "test-key"
        result = await external_research_cache_check_node(
            {"node_id": node_id},
            _config(),
        )

    assert result["external_video_urls"] == []
    assert result["external_research_youtube_backfill_only"] is True
    assert (
        _route_after_cache_check({**result, "external_research_cache_hit": True})
        == "external_research_youtube_discover"
    )


def test_route_after_youtube_discover_backfill_skips_article_search() -> None:
    state = {"external_research_youtube_backfill_only": True}
    assert _route_after_youtube_discover(state) == "external_research_attach_videos"


def test_route_after_youtube_discover_fresh_run_continues_to_search() -> None:
    state = {"external_research_youtube_backfill_only": False}
    assert _route_after_youtube_discover(state) == "external_research_search"


def test_route_after_cache_check_miss_goes_to_resolve_query() -> None:
    assert _route_after_cache_check({"external_research_cache_hit": False}) == (
        "external_research_resolve_query"
    )


def test_route_after_cache_check_hit_with_videos_ends() -> None:
    state = {
        "external_research_cache_hit": True,
        "external_research_youtube_backfill_only": False,
    }
    assert _route_after_cache_check(state) == "__end__"
