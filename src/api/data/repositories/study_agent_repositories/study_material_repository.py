# src/api/data/repositories/content_repository/study_material_repository.py
"""
Repository for study_material_versions DB operations.

Handles:
  - Version lookups (by id, active, published, all by node)
  - Version insert
  - Deactivate / activate version (is_active flip)
  - Publish version (is_published=True, published_at, published_by)
  - Next version_number resolution (MAX + 1)

Version activation: only one version per node has is_active=True at a time.
Enforced at the service layer — the repo provides atomic deactivate + activate
helpers rather than doing both in a single call (service controls the transaction).
"""

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)

GenerationType = Literal["generate", "regenerate", "improve", "manual_edit"]


class StudyMaterialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── Lookups ─────────────────────────────────────────────────────────

    async def get_version_by_id(self, version_id: UUID) -> StudyMaterialVersion | None:
        result = await self.db.execute(
            select(StudyMaterialVersion).where(
                StudyMaterialVersion.version_id == version_id
            )
        )
        return cast(StudyMaterialVersion | None, result.scalars().first())

    async def get_active_version(self, node_id: UUID) -> StudyMaterialVersion | None:
        """Return the single is_active=True non-archived version for a node, or None."""
        result = await self.db.execute(
            select(StudyMaterialVersion).where(
                and_(
                    StudyMaterialVersion.node_id == node_id,
                    StudyMaterialVersion.is_active.is_(True),
                    StudyMaterialVersion.is_archived.is_(False),
                )
            )
        )
        return cast(StudyMaterialVersion | None, result.scalars().first())

    async def get_published_version(self, node_id: UUID) -> StudyMaterialVersion | None:
        """Return the latest is_published=True version for a node, or None."""
        result = await self.db.execute(
            select(StudyMaterialVersion)
            .where(
                and_(
                    StudyMaterialVersion.node_id == node_id,
                    StudyMaterialVersion.is_published.is_(True),
                )
            )
            .order_by(StudyMaterialVersion.version_number.desc())
            .limit(1)
        )
        return cast(StudyMaterialVersion | None, result.scalars().first())

    async def reconcile_published_versions(self, node_id: UUID) -> None:
        """Ensure at most one published version — keeps the highest version number."""
        result = await self.db.execute(
            select(StudyMaterialVersion)
            .where(
                and_(
                    StudyMaterialVersion.node_id == node_id,
                    StudyMaterialVersion.is_published.is_(True),
                )
            )
            .order_by(StudyMaterialVersion.version_number.desc())
        )
        published = list(result.scalars().all())
        if len(published) <= 1:
            return
        keeper = published[0]
        await self.unpublish_other_versions(node_id, keeper.version_id)

    async def get_all_versions(
        self, node_id: UUID, *, archived: bool | None = None
    ) -> list[StudyMaterialVersion]:
        """Return versions for a node ordered by version_number DESC.

        archived=None returns all versions (for lineage resolution).
        archived=False returns active history; archived=True returns archive shelf.
        """
        query = select(StudyMaterialVersion).where(
            StudyMaterialVersion.node_id == node_id
        )
        if archived is not None:
            query = query.where(StudyMaterialVersion.is_archived.is_(archived))
        query = query.order_by(StudyMaterialVersion.version_number.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_next_version_number(self, node_id: UUID) -> int:
        """Return MAX(version_number) + 1 for the node. Returns 1 if no versions exist."""
        result = await self.db.execute(
            select(func.max(StudyMaterialVersion.version_number)).where(
                StudyMaterialVersion.node_id == node_id
            )
        )
        max_ver = result.scalar()
        return (max_ver + 1) if max_ver is not None else 1

    # ── Writes ──────────────────────────────────────────────────────────

    async def create_version(
        self,
        node_id: UUID,
        space_id: UUID,
        version_number: int,
        content: str,
        generation_type: GenerationType,
        mentor_feedback_used: str | None,
        reference_material_id: UUID | None,
        based_on_version_id: UUID | None,
        llm_model_used: str | None,
        prompt_snapshot: str | None,
        token_usage: int | None,
        is_active: bool,
        created_by: UUID,
        qc_failed_permanently: bool = False,
        qc_result: dict | None = None,
    ) -> StudyMaterialVersion:
        now = datetime.now(UTC)
        version = StudyMaterialVersion(
            version_id=uuid4(),
            node_id=node_id,
            space_id=space_id,
            version_number=version_number,
            content=content,
            generation_type=generation_type,
            mentor_feedback_used=mentor_feedback_used,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on_version_id,
            llm_model_used=llm_model_used,
            prompt_snapshot=prompt_snapshot,
            token_usage=token_usage,
            is_active=is_active,
            is_published=False,
            published_at=None,
            published_by=None,
            created_by=created_by,
            created_at=now,
            qc_failed_permanently=qc_failed_permanently,
            qc_result=qc_result,
        )
        self.db.add(version)
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def deactivate_version(self, version: StudyMaterialVersion) -> None:
        """Set is_active=False. Called before activating a new version."""
        version.is_active = False
        await self.db.commit()

    async def activate_version(
        self, version: StudyMaterialVersion
    ) -> StudyMaterialVersion:
        """Set is_active=True and refresh."""
        version.is_active = True
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def unpublish_other_versions(
        self, node_id: UUID, except_version_id: UUID, *, commit: bool = True
    ) -> None:
        """Clear publish flags on all other versions for this node."""
        result = await self.db.execute(
            select(StudyMaterialVersion).where(
                and_(
                    StudyMaterialVersion.node_id == node_id,
                    StudyMaterialVersion.is_published.is_(True),
                    StudyMaterialVersion.version_id != except_version_id,
                )
            )
        )
        for other in result.scalars().all():
            other.is_published = False
            other.published_at = None
            other.published_by = None
        if commit:
            await self.db.commit()

    async def publish_version(
        self, version: StudyMaterialVersion, published_by: UUID, *, commit: bool = True
    ) -> StudyMaterialVersion:
        """Set is_published=True, published_at, published_by."""
        await self.unpublish_other_versions(
            version.node_id, version.version_id, commit=False
        )
        now = datetime.now(UTC)
        version.is_published = True
        version.published_at = now
        version.published_by = published_by
        if commit:
            await self.db.commit()
            await self.db.refresh(version)
        return version

    async def unpublish_version(
        self, version: StudyMaterialVersion, *, commit: bool = True
    ) -> StudyMaterialVersion:
        """Clear publish flags on a version."""
        version.is_published = False
        version.published_at = None
        version.published_by = None
        if commit:
            await self.db.commit()
            await self.db.refresh(version)
        return version

    async def archive_version(
        self, version: StudyMaterialVersion, archived_by: UUID
    ) -> StudyMaterialVersion:
        now = datetime.now(UTC)
        version.is_archived = True
        version.archived_at = now
        version.archived_by = archived_by
        if version.is_active:
            version.is_active = False
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def unarchive_version(
        self, version: StudyMaterialVersion
    ) -> StudyMaterialVersion:
        version.is_archived = False
        version.archived_at = None
        version.archived_by = None
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def delete_all_versions_for_node(self, node_id: UUID) -> int:
        """Hard-delete all study material versions for a node.

        studymaterialversions.based_on_version_id is a self-referential FK
        (lineage: Improve/Regenerate point a new draft at its parent). Deleting
        rows individually lets SQLAlchemy batch them into one DELETE whose row
        order does not respect that dependency, so deleting a parent that is
        still referenced by a child raises a ForeignKeyViolationError. Break the
        lineage links first, then bulk-delete everything for the node.
        """
        versions = await self.get_all_versions(node_id, archived=None)
        if not versions:
            return 0
        await self.db.execute(
            update(StudyMaterialVersion)
            .where(StudyMaterialVersion.node_id == node_id)
            .where(StudyMaterialVersion.based_on_version_id.is_not(None))
            .values(based_on_version_id=None)
        )
        await self.db.execute(
            delete(StudyMaterialVersion).where(StudyMaterialVersion.node_id == node_id)
        )
        await self.db.commit()
        return len(versions)
