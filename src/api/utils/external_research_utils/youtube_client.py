"""Thin YouTube Data API v3 client for external-research video discovery."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://www.googleapis.com/youtube/v3"
_DEFAULT_TIMEOUT_SEC = 30
_USER_AGENT = "StudyGuruExternalResearch/1.0"


class YouTubeApiError(Exception):
    """Raised when a YouTube Data API request fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason


def _parse_api_error_body(body: dict[str, Any] | None) -> str | None:
    if not body:
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    errors = error.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            reason = first.get("reason")
            if isinstance(reason, str) and reason:
                return reason
    message = error.get("message")
    if isinstance(message, str) and message:
        return message
    return None


def _get(
    endpoint: str,
    params: dict[str, str],
    *,
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    url = f"{API_BASE}/{endpoint}"
    try:
        with httpx.Client(
            timeout=timeout_sec,
            headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
        ) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        reason: str | None = None
        try:
            reason = _parse_api_error_body(exc.response.json())
        except Exception:
            pass
        raise YouTubeApiError(
            f"YouTube API HTTP {exc.response.status_code}",
            status_code=exc.response.status_code,
            reason=reason,
        ) from exc
    except httpx.RequestError as exc:
        raise YouTubeApiError(f"YouTube API request failed: {exc}") from exc

    if not isinstance(payload, dict):
        raise YouTubeApiError("YouTube API returned a non-object response")
    return payload


def search_video_ids(
    api_key: str,
    query: str,
    *,
    max_results: int,
) -> list[str]:
    """Run ``search.list`` and return video IDs in API relevance order."""
    search_query = query.strip()
    if not search_query:
        return []

    payload = _get(
        "search",
        {
            "part": "snippet",
            "type": "video",
            "q": search_query,
            "maxResults": str(max_results),
            "videoEmbeddable": "true",
            "videoDuration": "medium",
            "safeSearch": "moderate",
            "key": api_key,
        },
    )
    items = payload.get("items") or []
    video_ids: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        if not isinstance(item_id, dict):
            continue
        video_id = item_id.get("videoId")
        if isinstance(video_id, str) and video_id:
            video_ids.append(video_id)
    return video_ids


def fetch_video_details(
    api_key: str,
    video_ids: list[str],
) -> list[dict[str, Any]]:
    """Run ``videos.list`` for the given IDs; returns raw API item dicts."""
    if not video_ids:
        return []

    payload = _get(
        "videos",
        {
            "part": "snippet,contentDetails,statistics,status",
            "id": ",".join(video_ids),
            "key": api_key,
        },
    )
    items = payload.get("items") or []
    return [item for item in items if isinstance(item, dict)]
