"""Repository for reference_llamaparse_pdf and reference_llamaparse_images."""

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.reference_llamaparse_images import (
    ReferenceLlamaParseImage,
)
from src.api.data.models.postgres.e_learning_content.reference_llamaparse_pdf import (
    ReferenceLlamaParsePdf,
)


class ReferenceLlamaParseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def get_by_reference_and_node(
        self,
        reference_material_id: UUID,
        node_id: UUID,
    ) -> ReferenceLlamaParsePdf | None:
        result = await self.db.execute(
            select(ReferenceLlamaParsePdf).where(
                and_(
                    ReferenceLlamaParsePdf.reference_material_id
                    == reference_material_id,
                    ReferenceLlamaParsePdf.node_id == node_id,
                )
            )
        )
        return cast(ReferenceLlamaParsePdf | None, result.scalars().first())

    async def get_by_content_hash(
        self, content_hash: str
    ) -> ReferenceLlamaParsePdf | None:
        """Most recent parse row for identical PDF bytes."""
        result = await self.db.execute(
            select(ReferenceLlamaParsePdf)
            .where(ReferenceLlamaParsePdf.content_hash == content_hash)
            .order_by(ReferenceLlamaParsePdf.created_at.desc())
            .limit(1)
        )
        return cast(ReferenceLlamaParsePdf | None, result.scalars().first())

    async def get_with_images_by_content_hash(
        self, content_hash: str
    ) -> tuple[ReferenceLlamaParsePdf, list[ReferenceLlamaParseImage]] | None:
        """Load the latest cached parse row and its figure rows for a content hash."""
        pdf_row = await self.get_by_content_hash(content_hash)
        if pdf_row is None:
            return None
        images = await self.list_images_for_pdf(pdf_row.llamaparse_pdf_id)
        return pdf_row, images

    async def list_images_for_pdf(
        self, llamaparse_pdf_id: UUID
    ) -> list[ReferenceLlamaParseImage]:
        result = await self.db.execute(
            select(ReferenceLlamaParseImage)
            .where(ReferenceLlamaParseImage.llamaparse_pdf_id == llamaparse_pdf_id)
            .order_by(ReferenceLlamaParseImage.order_index.asc())
        )
        return list(result.scalars().all())

    async def list_images_by_reference_and_node(
        self,
        reference_material_id: UUID,
        node_id: UUID,
    ) -> list[ReferenceLlamaParseImage]:
        result = await self.db.execute(
            select(ReferenceLlamaParseImage)
            .where(
                and_(
                    ReferenceLlamaParseImage.reference_material_id
                    == reference_material_id,
                    ReferenceLlamaParseImage.node_id == node_id,
                )
            )
            .order_by(ReferenceLlamaParseImage.order_index.asc())
        )
        return list(result.scalars().all())

    async def upsert_parse_result(
        self,
        *,
        reference_material_id: UUID,
        node_id: UUID,
        space_id: UUID,
        llama_parse_job_id: str,
        llama_parse_parse_job_id: str | None,
        content_hash: str,
        structured_json: dict[str, Any],
        formatted_text: str,
        parsed_by: UUID,
        images: list[dict[str, Any]],
    ) -> ReferenceLlamaParsePdf:
        existing = await self.get_by_reference_and_node(reference_material_id, node_id)
        now = datetime.now(UTC)

        if existing is not None:
            await self.db.execute(
                delete(ReferenceLlamaParseImage).where(
                    ReferenceLlamaParseImage.llamaparse_pdf_id
                    == existing.llamaparse_pdf_id
                )
            )
            existing.llama_parse_job_id = llama_parse_job_id
            existing.llama_parse_parse_job_id = llama_parse_parse_job_id
            existing.content_hash = content_hash
            existing.structured_json = structured_json
            existing.formatted_text = formatted_text
            existing.parsed_by = parsed_by
            existing.updated_at = now
            pdf_row = existing
        else:
            pdf_row = ReferenceLlamaParsePdf(
                llamaparse_pdf_id=uuid4(),
                reference_material_id=reference_material_id,
                node_id=node_id,
                space_id=space_id,
                llama_parse_job_id=llama_parse_job_id,
                llama_parse_parse_job_id=llama_parse_parse_job_id,
                content_hash=content_hash,
                structured_json=structured_json,
                formatted_text=formatted_text,
                parsed_by=parsed_by,
                created_at=now,
                updated_at=now,
            )
            self.db.add(pdf_row)

        await self.db.flush()

        for image in images:
            self.db.add(
                ReferenceLlamaParseImage(
                    llamaparse_image_id=uuid4(),
                    llamaparse_pdf_id=pdf_row.llamaparse_pdf_id,
                    reference_material_id=reference_material_id,
                    node_id=node_id,
                    title=image.get("title"),
                    filename=image["filename"],
                    file_url=image["file_url"],
                    source_page_number=image.get("source_page_number"),
                    figure_index_on_page=image.get("figure_index_on_page"),
                    parse_index=image.get("parse_index"),
                    category=image.get("category"),
                    order_index=image.get("order_index", 0),
                )
            )

        await self.db.flush()
        await self.db.refresh(pdf_row)
        return pdf_row
