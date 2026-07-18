"""Repository for externalresearchreference cache rows."""

from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.external_research_reference import (
    ExternalResearchReference,
)


class ExternalResearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_by_node_id(self, node_id: UUID) -> ExternalResearchReference | None:
        result = await self.db.execute(
            select(ExternalResearchReference).where(
                ExternalResearchReference.node_id == node_id
            )
        )
        return cast(ExternalResearchReference | None, result.scalars().first())

    async def create(
        self,
        *,
        node_id: UUID,
        space_id: UUID,
        status: str,
        fail_reason: str | None,
        search_query_used: str | None,
        resolved_topic: str | None,
        resolved_subtopic: str | None,
        ground_truth_reference: str | None,
        source_urls: list[Any],
        per_website_summary_count: int,
        token_count: int | None,
        knowledge_distillation_model_used: str | None,
        requested_by: UUID,
    ) -> ExternalResearchReference:
        """Insert-if-absent. Concurrent UniqueViolation is treated as a cache hit."""
        existing = await self.get_by_node_id(node_id)
        if existing is not None:
            return existing

        row = ExternalResearchReference(
            external_research_id=uuid4(),
            node_id=node_id,
            space_id=space_id,
            status=status,
            fail_reason=fail_reason,
            search_query_used=search_query_used,
            resolved_topic=resolved_topic,
            resolved_subtopic=resolved_subtopic,
            ground_truth_reference=ground_truth_reference,
            source_urls=source_urls,
            per_website_summary_count=per_website_summary_count,
            token_count=token_count,
            knowledge_distillation_model_used=knowledge_distillation_model_used,
            requested_by=requested_by,
        )

        try:
            async with self.db.begin_nested():
                self.db.add(row)
                await self.db.flush()
        except IntegrityError:
            existing = await self.get_by_node_id(node_id)
            if existing is None:
                raise
            return existing

        await self.db.refresh(row)
        return row
