"""YouTube search, filter, and engagement ranking for student video resources."""

from __future__ import annotations

import logging
import math
import re
from typing import Any

from src.api.config import external_research_settings
from src.api.utils.external_research_utils.youtube_client import (
    fetch_video_details,
    search_video_ids,
)

logger = logging.getLogger(__name__)

_SPONSOR_RE = re.compile(
    r"(#ad\b|#sponsored\b|#paid\b|paid\s+partnership|sponsored\s+by|"
    r"affiliate\s+link|thanks\s+to\s+our\s+sponsor)",
    re.IGNORECASE,
)
_SHORTS_HASHTAG_RE = re.compile(r"#shorts\b", re.IGNORECASE)
_ISO8601_DURATION_RE = re.compile(
    r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
)


def parse_iso8601_duration(value: str) -> int:
    """Parse YouTube ISO 8601 duration (e.g. ``PT4M13S``) to seconds."""
    match = _ISO8601_DURATION_RE.fullmatch(value or "")
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def is_short(title: str, description: str, duration_sec: int) -> bool:
    if duration_sec > 0 and duration_sec <= 60:
        return True
    return bool(_SHORTS_HASHTAG_RE.search(f"{title}\n{description}"))


def looks_sponsored(title: str, description: str) -> bool:
    return bool(_SPONSOR_RE.search(f"{title}\n{description}"))


def engagement_score(views: int, likes: int) -> float:
    """Composite score: sqrt(views) weighted by like ratio."""
    if views <= 0:
        return 0.0
    like_ratio = likes / views
    return math.sqrt(views) * (1.0 + 50.0 * like_ratio)


def _passes_filters(
    *,
    title: str,
    description: str,
    duration_sec: int,
    embeddable: bool,
    min_duration_sec: int,
) -> bool:
    if is_short(title, description, duration_sec):
        return False
    if looks_sponsored(title, description):
        return False
    if not embeddable:
        return False
    if duration_sec < min_duration_sec:
        return False
    return True


def _item_to_ranked_video(
    item: dict[str, Any],
    *,
    min_duration_sec: int,
) -> dict[str, Any] | None:
    snippet = item.get("snippet") or {}
    stats = item.get("statistics") or {}
    content = item.get("contentDetails") or {}
    status = item.get("status") or {}

    video_id = item.get("id") or ""
    if not isinstance(video_id, str) or not video_id:
        return None

    title = snippet.get("title") or ""
    description = snippet.get("description") or ""
    duration_sec = parse_iso8601_duration(content.get("duration") or "")
    embeddable = bool(status.get("embeddable", True))

    if not _passes_filters(
        title=title,
        description=description,
        duration_sec=duration_sec,
        embeddable=embeddable,
        min_duration_sec=min_duration_sec,
    ):
        return None

    views = int(stats.get("viewCount") or 0)
    likes = int(stats.get("likeCount") or 0)
    score = round(engagement_score(views, likes), 2)

    return {
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "video_id": video_id,
        "title": title,
        "channel": snippet.get("channelTitle") or "",
        "duration_sec": duration_sec,
        "views": views,
        "likes": likes,
        "score": score,
    }


def _rank_videos(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        videos,
        key=lambda row: (row["score"], row["views"], row["likes"]),
        reverse=True,
    )


def search_and_rank(
    query: str,
    *,
    api_key: str | None = None,
    max_videos: int | None = None,
    search_pool: int | None = None,
    min_duration_sec: int | None = None,
) -> list[dict[str, Any]]:
    """Search YouTube, filter candidates, and return top-ranked video metadata.

    Raises ``YouTubeApiError`` on API/network failures. Returns an empty list when
    the API key is missing, the query is blank, or no videos pass filters.
    """
    search_query = query.strip()
    if not search_query:
        return []

    resolved_api_key = (
        api_key or external_research_settings.youtube_api_key or ""
    ).strip()
    if not resolved_api_key:
        logger.warning("YOUTUBE_API_KEY is not configured — YouTube discovery skipped")
        return []

    resolved_pool = (
        search_pool
        if search_pool is not None
        else external_research_settings.external_research_youtube_search_pool
    )
    resolved_max = (
        max_videos
        if max_videos is not None
        else external_research_settings.external_research_max_youtube_videos
    )
    resolved_min_duration = (
        min_duration_sec
        if min_duration_sec is not None
        else external_research_settings.external_research_min_video_duration_sec
    )

    video_ids = search_video_ids(
        resolved_api_key,
        search_query,
        max_results=resolved_pool,
    )
    if not video_ids:
        logger.info("YouTube search returned no candidates for query=%r", search_query)
        return []

    details = fetch_video_details(resolved_api_key, video_ids)
    ranked: list[dict[str, Any]] = []
    for item in details:
        video = _item_to_ranked_video(item, min_duration_sec=resolved_min_duration)
        if video is not None:
            ranked.append(video)

    top = _rank_videos(ranked)[:resolved_max]
    logger.info(
        "YouTube rank query=%r candidates=%d kept=%d returning=%d",
        search_query,
        len(details),
        len(ranked),
        len(top),
    )
    return top
