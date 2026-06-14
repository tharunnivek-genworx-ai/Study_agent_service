# src/api/data/repositories/content_repository/reference_material_repository.py
"""
Repository for reference_materials and node_media DB operations.

Reference materials:
  - Lookup by id, by space, by node (active only, deleted_at IS NULL)
  - Insert, soft-delete (set deleted_at), update visibility

Node media:
  - Lookup by id, by node (active only)
  - Insert, hard delete, bulk order_index update
  - next order_index resolution (MAX + 1)

Immutability rule: reference_materials rows are never updated in-place except
for the is_visible_to_trainees field — all other changes require a new row (EC-17).
"""

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.node_media import NodeMedia
from src.api.data.models.postgres.e_learning_content.reference_materials import (
    ReferenceMaterial,
)

NodeMediaType = Literal["image", "video_url", "article_link"]
ReferenceMaterialScope = Literal["space", "node"]


class ReferenceMaterialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── Reference Material Lookups ───────────────────────────────────────

    async def get_by_id(self, material_id: UUID) -> ReferenceMaterial | None:
        result = await self.db.execute(
            select(ReferenceMaterial).where(
                ReferenceMaterial.material_id == material_id
            )
        )
        return cast(ReferenceMaterial | None, result.scalars().first())

    async def get_by_space(self, space_id: UUID) -> list[ReferenceMaterial]:
        """All active (not soft-deleted) space-scoped materials."""
        result = await self.db.execute(
            select(ReferenceMaterial).where(
                and_(
                    ReferenceMaterial.space_id == space_id,
                    ReferenceMaterial.scope == "space",
                    ReferenceMaterial.deleted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    async def get_by_node(self, node_id: UUID) -> list[ReferenceMaterial]:
        """All active (not soft-deleted) node-scoped materials."""
        result = await self.db.execute(
            select(ReferenceMaterial).where(
                and_(
                    ReferenceMaterial.node_id == node_id,
                    ReferenceMaterial.scope == "node",
                    ReferenceMaterial.deleted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    async def get_latest_by_node(self, node_id: UUID) -> ReferenceMaterial | None:
        """Most recently uploaded active node-scoped material."""
        result = await self.db.execute(
            select(ReferenceMaterial)
            .where(
                and_(
                    ReferenceMaterial.node_id == node_id,
                    ReferenceMaterial.scope == "node",
                    ReferenceMaterial.deleted_at.is_(None),
                )
            )
            .order_by(ReferenceMaterial.created_at.desc())
            .limit(1)
        )
        return cast(ReferenceMaterial | None, result.scalars().first())

    # ── Reference Material Writes ────────────────────────────────────────

    async def create_reference_material(
        self,
        space_id: UUID,
        node_id: UUID | None,
        title: str,
        scope: ReferenceMaterialScope,
        file_url: str,
        file_name: str,
        file_size_bytes: int | None,
        mime_type: str,
        is_visible_to_trainees: bool,
        uploaded_by: UUID,
    ) -> ReferenceMaterial:
        return await self.create_reference_material_with_id(
            material_id=uuid4(),
            space_id=space_id,
            node_id=node_id,
            title=title,
            scope=scope,
            file_url=file_url,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            is_visible_to_trainees=is_visible_to_trainees,
            uploaded_by=uploaded_by,
        )

    async def create_reference_material_with_id(
        self,
        material_id: UUID,
        space_id: UUID,
        node_id: UUID | None,
        title: str,
        scope: ReferenceMaterialScope,
        file_url: str,
        file_name: str,
        file_size_bytes: int | None,
        mime_type: str,
        is_visible_to_trainees: bool,
        uploaded_by: UUID,
    ) -> ReferenceMaterial:
        now = datetime.now(UTC)
        material = ReferenceMaterial(
            material_id=material_id,
            space_id=space_id,
            node_id=node_id,
            title=title,
            scope=scope,
            file_url=file_url,
            file_name=file_name,
            file_size_bytes=file_size_bytes,
            mime_type=mime_type,
            is_visible_to_trainees=is_visible_to_trainees,
            uploaded_by=uploaded_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(material)
        await self.db.commit()
        await self.db.refresh(material)
        return material

    async def update_visibility(
        self, material: ReferenceMaterial, is_visible: bool
    ) -> ReferenceMaterial:
        material.is_visible_to_trainees = is_visible
        material.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(material)
        return material

    async def soft_delete(self, material: ReferenceMaterial) -> None:
        material.deleted_at = datetime.now(UTC)
        await self.db.commit()

    # ── Node Media Lookups ───────────────────────────────────────────────

    async def get_media_by_id(self, media_id: UUID) -> NodeMedia | None:
        result = await self.db.execute(
            select(NodeMedia).where(NodeMedia.media_id == media_id)
        )
        return cast(NodeMedia | None, result.scalars().first())

    async def get_media_by_node(self, node_id: UUID) -> list[NodeMedia]:
        """All active media for a node ordered by order_index ASC."""
        result = await self.db.execute(
            select(NodeMedia)
            .where(NodeMedia.node_id == node_id)
            .order_by(NodeMedia.order_index.asc())
        )
        return list(result.scalars().all())

    async def get_media_by_node_and_reference(
        self,
        node_id: UUID,
        reference_material_id: UUID,
    ) -> list[NodeMedia]:
        """PDF-extracted images for a node scoped to one reference material."""
        result = await self.db.execute(
            select(NodeMedia)
            .where(
                and_(
                    NodeMedia.node_id == node_id,
                    NodeMedia.media_type == "image",
                    NodeMedia.source_pdf_material_id == reference_material_id,
                )
            )
            .order_by(NodeMedia.order_index.asc())
        )
        return list(result.scalars().all())

    async def delete_pdf_extracted_media(
        self,
        node_id: UUID,
        reference_material_id: UUID,
    ) -> int:
        """Hard-delete PDF-extracted image rows for a node + reference material."""
        result = await self.db.execute(
            select(NodeMedia).where(
                and_(
                    NodeMedia.node_id == node_id,
                    NodeMedia.media_type == "image",
                    NodeMedia.source_pdf_material_id == reference_material_id,
                )
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            await self.db.delete(row)
        if rows:
            await self.db.commit()
        return len(rows)

    async def get_next_media_order_index(self, node_id: UUID) -> int:
        """Return MAX(order_index) + 1 for node media. Returns 0 if none exist."""
        result = await self.db.execute(
            select(func.max(NodeMedia.order_index)).where(NodeMedia.node_id == node_id)
        )
        max_index = result.scalar()
        return (max_index + 1) if max_index is not None else 0

    # ── Node Media Writes ────────────────────────────────────────────────

    async def create_media(
        self,
        node_id: UUID,
        space_id: UUID,
        media_type: NodeMediaType,
        title: str | None,
        url: str | None,
        file_url: str | None,
        order_index: int,
        uploaded_by: UUID,
        source_pdf_material_id: UUID | None = None,
        source_page_number: int | None = None,
    ) -> NodeMedia:
        media = NodeMedia(
            media_id=uuid4(),
            node_id=node_id,
            space_id=space_id,
            media_type=media_type,
            title=title,
            url=url,
            file_url=file_url,
            order_index=order_index,
            uploaded_by=uploaded_by,
            source_pdf_material_id=source_pdf_material_id,
            source_page_number=source_page_number,
        )
        self.db.add(media)
        await self.db.commit()
        await self.db.refresh(media)
        return media

    async def bulk_update_media_order(self, order_map: dict[UUID, int]) -> None:
        """Update order_index for multiple media items in one transaction."""
        for media_id, order_index in order_map.items():
            await self.db.execute(
                update(NodeMedia)
                .where(NodeMedia.media_id == media_id)
                .values(order_index=order_index)
            )
        await self.db.commit()

    async def delete_media(self, media: NodeMedia) -> None:
        """Hard delete — no soft-delete for node_media."""
        await self.db.delete(media)
        await self.db.commit()
