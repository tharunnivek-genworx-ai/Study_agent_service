"""Persist external_research_reference cache rows (design §12.3)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.repositories.study_agent_repositories.external_research_repository import (
    ExternalResearchRepository,
)
from src.api.utils.external_research_utils.tokens import rough_token_count


async def persist_external_research_cache(
    session: AsyncSession,
    *,
    node_id: UUID,
    space_id: UUID,
    mentor_id: UUID,
    status: str,
    fail_reason: str | None,
    search_query_used: str | None,
    resolved_topic: str | None,
    resolved_subtopic: str | None,
    ground_truth_reference: str | None,
    source_urls: list[Any] | None,
    video_urls: list[Any] | None = None,
    per_website_summary_count: int,
    knowledge_distillation_model_used: str | None,
) -> None:
    """Insert-if-absent cache row for success or fail_soft outcomes."""
    repo = ExternalResearchRepository(session)
    token_count = (
        rough_token_count(ground_truth_reference) if ground_truth_reference else 0
    )
    await repo.create(
        node_id=node_id,
        space_id=space_id,
        status=status,
        fail_reason=fail_reason,
        search_query_used=search_query_used,
        resolved_topic=resolved_topic,
        resolved_subtopic=resolved_subtopic,
        ground_truth_reference=ground_truth_reference,
        source_urls=list(source_urls or []),
        video_urls=list(video_urls or []),
        per_website_summary_count=per_website_summary_count,
        token_count=token_count,
        knowledge_distillation_model_used=knowledge_distillation_model_used,
        requested_by=mentor_id,
    )
