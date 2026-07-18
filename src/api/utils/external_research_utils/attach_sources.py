"""Attach merge-surviving URLs to node_media as article_link (design §12.4 / A.10)."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.repositories.study_agent_repositories.reference_material_repository import (
    ReferenceMaterialRepository,
)

logger = logging.getLogger(__name__)


async def attach_source_urls_to_node_media(
    session: AsyncSession,
    *,
    node_id: UUID,
    space_id: UUID,
    mentor_id: UUID,
    status: str | None,
    source_urls: list[str] | None,
) -> None:
    """Attach only URLs that survived the final merge. No-op on fail_soft."""
    if status != "success":
        return

    urls = [url for url in (source_urls or []) if url]
    if not urls:
        return

    media_repo = ReferenceMaterialRepository(session)
    existing = await media_repo.get_media_by_node(node_id)
    existing_urls = {
        str(item.url)
        for item in existing
        if getattr(item, "media_type", None) == "article_link" and item.url
    }

    next_order = 0
    if existing:
        next_order = max(int(item.order_index or 0) for item in existing) + 1

    for offset, url in enumerate(urls):
        if url in existing_urls:
            continue
        title = _title_from_url(url)
        await media_repo.create_media(
            node_id=node_id,
            space_id=space_id,
            media_type="article_link",
            title=title,
            url=url,
            file_url=None,
            order_index=next_order + offset,
            uploaded_by=mentor_id,
        )
        logger.info(
            "Attached external research article_link for node %s: %s", node_id, url
        )


def _title_from_url(url: str) -> str:
    """Short display title derived from the URL host/path."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.netloc or "").replace("www.", "")
    path = (parsed.path or "").strip("/")
    if path:
        leaf = path.split("/")[-1] or host
        return f"{host} — {leaf}"[:200] if host else leaf[:200]
    return host[:200] or url[:200]
