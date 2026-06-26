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
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.schemas.study_material_schemas.study_material_schema import RetentionMode
from src.api.utils.content_lifecycle import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_DISCARDED,
    LIFECYCLE_DRAFT,
    LIFECYCLE_HIDDEN,
    transition_sm_to_active,
    transition_sm_to_archived,
    transition_sm_to_hidden,
)
from src.api.utils.content_lifecycle.visibility import exclude_discarded

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
                    exclude_discarded(StudyMaterialVersion.lifecycle_status),
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
                    exclude_discarded(StudyMaterialVersion.lifecycle_status),
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
            and_(
                StudyMaterialVersion.node_id == node_id,
                exclude_discarded(StudyMaterialVersion.lifecycle_status),
            )
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
        qc_passed: bool = False,
        qc_attempt_count: int = 0,
        generation_run_id: str | None = None,
        concept_plan: dict[str, Any] | None = None,
        checklist_llm_model_used: str | None = None,
        qc_verification_mode: str | None = None,
        qc_frozen_check_ids: list[str] | None = None,
        qc_frozen_section_keys: list[str] | None = None,
        next_llm_retry_at: datetime | None = None,
        *,
        commit: bool = True,
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
            qc_passed=qc_passed,
            qc_attempt_count=qc_attempt_count,
            generation_run_id=generation_run_id,
            concept_plan=concept_plan,
            checklist_llm_model_used=checklist_llm_model_used,
            qc_verification_mode=qc_verification_mode,
            qc_frozen_check_ids=qc_frozen_check_ids,
            qc_frozen_section_keys=qc_frozen_section_keys,
            next_llm_retry_at=next_llm_retry_at,
            lifecycle_status=LIFECYCLE_DRAFT,
        )
        self.db.add(version)
        if commit:
            await self.db.commit()
            await self.db.refresh(version)
        else:
            await self.db.flush()
            await self.db.refresh(version)
        return version

    async def create_version_with_deactivate(
        self,
        *,
        active_version: StudyMaterialVersion | None,
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
        created_by: UUID,
        qc_failed_permanently: bool = False,
        qc_result: dict | None = None,
        qc_passed: bool = False,
        qc_attempt_count: int = 0,
        generation_run_id: str | None = None,
        concept_plan: dict[str, Any] | None = None,
        checklist_llm_model_used: str | None = None,
        qc_verification_mode: str | None = None,
        qc_frozen_check_ids: list[str] | None = None,
        qc_frozen_section_keys: list[str] | None = None,
        next_llm_retry_at: datetime | None = None,
    ) -> StudyMaterialVersion:
        """Deactivate the current active version and insert a new one atomically."""
        if active_version is not None:
            active_version.is_active = False
        return await self.create_version(
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
            is_active=True,
            created_by=created_by,
            qc_failed_permanently=qc_failed_permanently,
            qc_result=qc_result,
            qc_passed=qc_passed,
            qc_attempt_count=qc_attempt_count,
            generation_run_id=generation_run_id,
            concept_plan=concept_plan,
            checklist_llm_model_used=checklist_llm_model_used,
            qc_verification_mode=qc_verification_mode,
            qc_frozen_check_ids=qc_frozen_check_ids,
            qc_frozen_section_keys=qc_frozen_section_keys,
            next_llm_retry_at=next_llm_retry_at,
            commit=True,
        )

    async def deactivate_version(self, version: StudyMaterialVersion) -> None:
        """Set is_active=False. Called before activating a new version."""
        version.is_active = False
        await self.db.commit()
        await self.db.refresh(version)

    async def activate_version(
        self, version: StudyMaterialVersion
    ) -> StudyMaterialVersion:
        """Set is_active=True and refresh."""
        version.is_active = True
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def unpublish_other_versions(
        self,
        node_id: UUID,
        except_version_id: UUID,
        *,
        retention_mode: RetentionMode = RetentionMode.keep_for_review,
        commit: bool = True,
    ) -> None:
        """Retire other published versions when superseding or re-publishing."""
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
            if retention_mode == RetentionMode.keep_for_review:
                transition_sm_to_archived(other)
            else:
                transition_sm_to_hidden(other)
        if commit:
            await self.db.commit()

    async def publish_version(
        self,
        version: StudyMaterialVersion,
        published_by: UUID,
        *,
        superseded_retention_mode: RetentionMode = RetentionMode.keep_for_review,
        commit: bool = True,
    ) -> StudyMaterialVersion:
        """Publish target version and retire any other published versions."""
        await self.unpublish_other_versions(
            version.node_id,
            version.version_id,
            retention_mode=superseded_retention_mode,
            commit=False,
        )
        transition_sm_to_active(version, published_by)
        if commit:
            await self.db.commit()
            await self.db.refresh(version)
        return version

    async def unpublish_version(
        self, version: StudyMaterialVersion, *, commit: bool = True
    ) -> StudyMaterialVersion:
        """Hide a published version from trainees while retaining publish metadata."""
        transition_sm_to_hidden(version)
        if commit:
            await self.db.commit()
            await self.db.refresh(version)
        return version

    async def archive_version(
        self, version: StudyMaterialVersion, archived_by: UUID
    ) -> StudyMaterialVersion:
        """Mentor shelf archive: hide from working history; never touches lifecycle.

        ``is_archived`` is orthogonal to ``lifecycle_status``. Shelf-archived rows
        remain trainee-invisible regardless of lifecycle (service layer enforces
        draft-only eligibility before calling this method).
        """
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
        """Restore a shelf-archived WIP draft to mentor working history only."""
        version.is_archived = False
        version.archived_at = None
        version.archived_by = None
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def discard_draft_versions_for_node(self, node_id: UUID) -> int:
        """Soft-discard mentor workspace study material for a node (workspace trash).

        Clears draft and unpublished-hidden rows from the mentor working history.
        Linked draft quizzes for those versions are discarded in the same transaction.
        Live published, superseded trainee archive, and shelf-archived rows are untouched.
        """
        discardable_filter = and_(
            StudyMaterialVersion.node_id == node_id,
            StudyMaterialVersion.is_archived.is_(False),
            or_(
                StudyMaterialVersion.lifecycle_status.in_(
                    (LIFECYCLE_DRAFT, LIFECYCLE_HIDDEN)
                ),
                and_(
                    StudyMaterialVersion.lifecycle_status == LIFECYCLE_ACTIVE,
                    StudyMaterialVersion.is_published.is_(False),
                ),
            ),
        )
        result = await self.db.execute(
            select(StudyMaterialVersion.version_id).where(discardable_filter)
        )
        draft_ids = list(result.scalars().all())
        if not draft_ids:
            return 0

        from src.api.data.repositories.quiz_repositories.quiz_repository import (  # noqa: PLC0415
            QuizRepository,
        )

        quiz_repo = QuizRepository(self.db)
        await quiz_repo.discard_drafts_for_sm_versions(draft_ids, commit=False)

        sm_result = await self.db.execute(
            update(StudyMaterialVersion)
            .where(discardable_filter)
            .values(
                lifecycle_status=LIFECYCLE_DISCARDED,
                is_published=False,
                is_active=False,
            )
        )
        await self.db.commit()
        return int(getattr(sm_result, "rowcount", 0) or 0)
