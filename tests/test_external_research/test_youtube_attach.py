"""Unit tests for attach_video_urls_to_node_media."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.utils.external_research_utils.attach_sources import (
    attach_video_urls_to_node_media,
)


def _video(
    video_id: str,
    *,
    title: str | None = None,
    url: str | None = None,
) -> dict:
    resolved_url = url or f"https://www.youtube.com/watch?v={video_id}"
    return {
        "url": resolved_url,
        "video_id": video_id,
        "title": title or f"Video {video_id}",
        "channel": "Channel",
        "duration_sec": 600,
        "views": 1000,
        "likes": 50,
        "score": 42.0,
    }


@pytest.mark.asyncio
async def test_attach_creates_video_url_rows_with_metadata_title() -> None:
    node_id = uuid4()
    space_id = uuid4()
    mentor_id = uuid4()
    mock_session = MagicMock()
    mock_repo = MagicMock()
    mock_repo.get_media_by_node = AsyncMock(return_value=[])
    mock_repo.create_media = AsyncMock()

    with patch(
        "src.api.utils.external_research_utils.attach_sources.ReferenceMaterialRepository",
        return_value=mock_repo,
    ):
        await attach_video_urls_to_node_media(
            mock_session,
            node_id=node_id,
            space_id=space_id,
            mentor_id=mentor_id,
            video_urls=[_video("abc123", title="React Hooks Explained")],
        )

    mock_repo.create_media.assert_awaited_once()
    kwargs = mock_repo.create_media.await_args.kwargs
    assert kwargs["media_type"] == "video_url"
    assert kwargs["title"] == "React Hooks Explained"
    assert kwargs["url"] == "https://www.youtube.com/watch?v=abc123"
    assert kwargs["order_index"] == 0


@pytest.mark.asyncio
async def test_attach_skips_duplicate_urls() -> None:
    node_id = uuid4()
    space_id = uuid4()
    mentor_id = uuid4()
    existing_url = "https://www.youtube.com/watch?v=existing"
    existing = MagicMock()
    existing.url = existing_url
    existing.media_type = "video_url"
    existing.order_index = 2

    mock_repo = MagicMock()
    mock_repo.get_media_by_node = AsyncMock(return_value=[existing])
    mock_repo.create_media = AsyncMock()

    with patch(
        "src.api.utils.external_research_utils.attach_sources.ReferenceMaterialRepository",
        return_value=mock_repo,
    ):
        await attach_video_urls_to_node_media(
            MagicMock(),
            node_id=node_id,
            space_id=space_id,
            mentor_id=mentor_id,
            video_urls=[
                _video("existing", url=existing_url),
                _video("newvid", title="New video"),
            ],
        )

    mock_repo.create_media.assert_awaited_once()
    kwargs = mock_repo.create_media.await_args.kwargs
    assert kwargs["url"] == "https://www.youtube.com/watch?v=newvid"
    assert kwargs["order_index"] == 3


@pytest.mark.asyncio
async def test_attach_skips_urls_already_present_as_article_link() -> None:
    existing = MagicMock()
    existing.url = "https://www.youtube.com/watch?v=shared"
    existing.media_type = "article_link"
    existing.order_index = 0

    mock_repo = MagicMock()
    mock_repo.get_media_by_node = AsyncMock(return_value=[existing])
    mock_repo.create_media = AsyncMock()

    with patch(
        "src.api.utils.external_research_utils.attach_sources.ReferenceMaterialRepository",
        return_value=mock_repo,
    ):
        await attach_video_urls_to_node_media(
            MagicMock(),
            node_id=uuid4(),
            space_id=uuid4(),
            mentor_id=uuid4(),
            video_urls=[_video("shared", url="https://www.youtube.com/watch?v=shared")],
        )

    mock_repo.create_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_attach_enforces_max_videos_cap() -> None:
    mock_repo = MagicMock()
    mock_repo.get_media_by_node = AsyncMock(return_value=[])
    mock_repo.create_media = AsyncMock()

    videos = [_video(f"id{i}", title=f"Video {i}") for i in range(5)]

    with patch(
        "src.api.utils.external_research_utils.attach_sources.ReferenceMaterialRepository",
        return_value=mock_repo,
    ):
        await attach_video_urls_to_node_media(
            MagicMock(),
            node_id=uuid4(),
            space_id=uuid4(),
            mentor_id=uuid4(),
            video_urls=videos,
            max_videos=3,
        )

    assert mock_repo.create_media.await_count == 3
    created_urls = [
        call.kwargs["url"] for call in mock_repo.create_media.await_args_list
    ]
    assert created_urls == [video["url"] for video in videos[:3]]


@pytest.mark.asyncio
async def test_attach_swallows_repository_errors() -> None:
    mock_repo = MagicMock()
    mock_repo.get_media_by_node = AsyncMock(side_effect=RuntimeError("db down"))

    with patch(
        "src.api.utils.external_research_utils.attach_sources.ReferenceMaterialRepository",
        return_value=mock_repo,
    ):
        await attach_video_urls_to_node_media(
            MagicMock(),
            node_id=uuid4(),
            space_id=uuid4(),
            mentor_id=uuid4(),
            video_urls=[_video("safe")],
        )
