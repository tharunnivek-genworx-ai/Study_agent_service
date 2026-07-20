"""Unit tests for YouTube filter/rank pipeline (no live API)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.api.utils.external_research_utils.youtube_rank import (
    _rank_videos,
    engagement_score,
    is_short,
    looks_sponsored,
    parse_iso8601_duration,
    search_and_rank,
)


def _video_item(
    video_id: str,
    *,
    title: str = "Lesson title",
    description: str = "",
    duration: str = "PT10M0S",
    views: int = 10_000,
    likes: int = 500,
    embeddable: bool = True,
) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "description": description,
            "channelTitle": "Test Channel",
        },
        "contentDetails": {"duration": duration},
        "statistics": {
            "viewCount": str(views),
            "likeCount": str(likes),
        },
        "status": {"embeddable": embeddable},
    }


def test_parse_iso8601_duration() -> None:
    assert parse_iso8601_duration("PT4M13S") == 253
    assert parse_iso8601_duration("PT1H2M3S") == 3723
    assert parse_iso8601_duration("") == 0


@pytest.mark.parametrize(
    ("title", "description", "duration_sec", "expected"),
    [
        ("Quick tip", "", 45, True),
        ("Full lecture", "", 600, False),
        ("Tutorial", "#shorts clip", 120, True),
    ],
)
def test_is_short(
    title: str, description: str, duration_sec: int, expected: bool
) -> None:
    assert is_short(title, description, duration_sec) is expected


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        ("Topic overview", "A clear explanation.", False),
        ("Sponsored lesson", "#ad check this out", True),
        ("Partner video", "Thanks to our sponsor Acme", True),
    ],
)
def test_looks_sponsored(title: str, description: str, expected: bool) -> None:
    assert looks_sponsored(title, description) is expected


def test_engagement_score_prefers_higher_views_and_likes() -> None:
    low = engagement_score(1_000, 10)
    high_views = engagement_score(1_000_000, 10)
    high_likes = engagement_score(1_000, 500)
    assert high_views > low
    assert high_likes > low
    assert engagement_score(0, 100) == 0.0


@patch(
    "src.api.utils.external_research_utils.youtube_rank.fetch_video_details",
)
@patch(
    "src.api.utils.external_research_utils.youtube_rank.search_video_ids",
)
def test_search_and_rank_filters_short_sponsor_and_short_duration(
    mock_search: object,
    mock_details: object,
) -> None:
    mock_search.return_value = ["ok", "short", "sponsor", "brief", "blocked"]
    mock_details.return_value = [
        _video_item("ok", duration="PT8M0S", views=50_000, likes=2_000),
        _video_item("short", duration="PT0M45S", views=1_000_000, likes=50_000),
        _video_item(
            "sponsor",
            title="Paid walkthrough",
            description="#sponsored content",
            duration="PT12M0S",
        ),
        _video_item("brief", duration="PT4M0S", views=20_000, likes=800),
        _video_item("blocked", duration="PT9M0S", embeddable=False),
    ]

    ranked = search_and_rank(
        "React hooks",
        api_key="test-key",
        max_videos=3,
        min_duration_sec=300,
    )

    assert len(ranked) == 1
    assert ranked[0]["video_id"] == "ok"
    assert ranked[0]["duration_sec"] == 480


@patch(
    "src.api.utils.external_research_utils.youtube_rank.fetch_video_details",
)
@patch(
    "src.api.utils.external_research_utils.youtube_rank.search_video_ids",
)
def test_search_and_rank_orders_by_score_and_caps_max(
    mock_search: object,
    mock_details: object,
) -> None:
    mock_search.return_value = ["a", "b", "c", "d"]
    mock_details.return_value = [
        _video_item("a", duration="PT6M0S", views=10_000, likes=100),
        _video_item("b", duration="PT7M0S", views=1_000_000, likes=50_000),
        _video_item("c", duration="PT8M0S", views=500_000, likes=20_000),
        _video_item("d", duration="PT9M0S", views=100_000, likes=5_000),
    ]

    ranked = search_and_rank(
        "calculus",
        api_key="test-key",
        max_videos=3,
        min_duration_sec=300,
    )

    assert len(ranked) == 3
    assert [row["video_id"] for row in ranked] == ["b", "c", "d"]
    scores = [row["score"] for row in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_videos_tie_breaks_by_views_then_likes() -> None:
    rows = [
        {
            "video_id": "low_views",
            "score": 100.0,
            "views": 5_000,
            "likes": 250,
            "url": "https://www.youtube.com/watch?v=low_views",
            "title": "A",
            "channel": "C",
            "duration_sec": 600,
        },
        {
            "video_id": "high_views",
            "score": 100.0,
            "views": 20_000,
            "likes": 1_000,
            "url": "https://www.youtube.com/watch?v=high_views",
            "title": "B",
            "channel": "C",
            "duration_sec": 600,
        },
    ]

    ranked = _rank_videos(rows)

    assert [row["video_id"] for row in ranked] == ["high_views", "low_views"]


def test_search_and_rank_returns_empty_without_api_key() -> None:
    assert search_and_rank("topic", api_key="") == []
