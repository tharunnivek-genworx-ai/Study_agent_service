# src/api/core/services/content_service/study_material_service.py
"""
Study material service: all business logic for study_material_versions.

Flow per TDD §3.2.1:
  GENERATE            → access guard → LangGraph (resolver → llamaparse? → agent)
                        → persist vN → deactivate previous active
  REGENERATE          → load active draft + mentor goal → LangGraph (no llamaparse)
                        → persist vN+1 with based_on_version_id
  IMPROVE             → load active draft + mentor feedback → LangGraph (no llamaparse)
                        → persist vN+1 with based_on_version_id
  MANUAL EDIT         → access guard → insert new version row (no LLM)
  PUBLISH / ACTIVATE / LIST / GET — unchanged
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.agents.study_material.runner import (
    run_study_material_generation,
    run_study_material_improve,
    run_study_material_regeneration,
)
from src.api.core.exceptions.study_material_exceptions.study_material_exceptions import (
    StudyMaterialCannotArchivePublishedException,
    StudyMaterialClearDraftsBlockedByQuizException,
    StudyMaterialNoActiveVersionException,
    StudyMaterialNoDraftsException,
    StudyMaterialNotFoundException,
    StudyMaterialPublishBlockedSpaceUnpublishedException,
    StudyMaterialVersionAlreadyArchivedException,
    StudyMaterialVersionAlreadyPublishedException,
    StudyMaterialVersionMismatchException,
    StudyMaterialVersionNotArchivedException,
    StudyMaterialVersionNotPublishedException,
)
from src.api.core.services.study_agent_services.study_material_publish_ops import (
    execute_publish_version_cascade,
    execute_unpublish_version_cascade,
)
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.space_node_repository.node_repository import (
    NodeRepository,
)
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.schemas.study_material_schemas.study_material_schema import (
    PublishedResourceTopicSummary,
    RepublishChecklistNodeOut,
    SpacePublishedResourcesResponse,
    SpaceRepublishChecklistOut,
    StudyMaterialActivateRequest,
    StudyMaterialClearDraftsEligibilityOut,
    StudyMaterialClearDraftsOut,
    StudyMaterialFeedbackResponse,
    StudyMaterialGenerateRequest,
    StudyMaterialImproveRequest,
    StudyMaterialManualEditRequest,
    StudyMaterialMentorUiStateOut,
    StudyMaterialPublishPreviewOut,
    StudyMaterialPublishRequest,
    StudyMaterialRegenerateRequest,
    StudyMaterialUnpublishPreviewOut,
    StudyMaterialVersionHistoryOut,
    StudyMaterialVersionOut,
    StudyMaterialVersionSummary,
)
from src.api.utils.content_utils.node_access import _get_node_and_assert_space_access
from src.api.utils.space_node_utils.build_node import (
    format_effective_instruction,
    resolve_effective_instruction_parts,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_mentor,
    _assert_space_access,
    _get_space_and_assert_owner,
)
from src.api.utils.study_agent_utils.instruction_snapshot import (
    embed_effective_instruction_snapshot,
    extract_effective_instruction_snapshot,
)
from src.api.utils.study_agent_utils.node_media_persistence import (
    persist_reference_images_to_node_media,
)
from src.api.utils.study_agent_utils.publish_cascade import (
    get_quizzes_linked_to_study_material_version,
    partition_quizzes_by_publish_state,
)
from src.api.utils.study_agent_utils.study_material_artifacts import (
    log_study_material_version,
)
from src.api.utils.study_agent_utils.version_actions import (
    compute_version_allowed_actions,
)
from src.api.utils.study_agent_utils.version_labels import build_version_display_label


class StudyMaterialService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _persist_new_version(
        self,
        *,
        node_id: UUID,
        space_id: UUID,
        graph_result: dict[str, Any],
        generation_type: str,
        user_id: UUID,
        mentor_feedback_used: str | None = None,
        reference_material_id: UUID | None = None,
        based_on_version_id: UUID | None = None,
    ) -> StudyMaterialVersionOut:
        repo = StudyMaterialRepository(self.session)
        next_version = await repo.get_next_version_number(node_id)

        active = await repo.get_active_version(node_id)
        if active is not None:
            await repo.deactivate_version(active)

        version = await repo.create_version(
            node_id=node_id,
            space_id=space_id,
            version_number=next_version,
            content=graph_result["generated_content"],
            generation_type=generation_type,
            mentor_feedback_used=mentor_feedback_used,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on_version_id,
            llm_model_used=graph_result.get("llm_model_used"),
            prompt_snapshot=embed_effective_instruction_snapshot(
                graph_result.get("prompt_snapshot"),
                graph_result.get("effective_instruction"),
            ),
            token_usage=graph_result.get("token_usage"),
            is_active=True,
            created_by=user_id,
        )
        topic_title = graph_result.get("node_title") or str(node_id)
        log_study_material_version(
            topic_title=topic_title,
            version_number=next_version,
            generation_type=generation_type,
            version_id=str(version.version_id),
            node_id=str(node_id),
            content=graph_result["generated_content"],
            graph_result=graph_result,
            mentor_feedback_used=mentor_feedback_used,
        )
        return StudyMaterialVersionOut.model_validate(version)

    async def _persist_reference_images_if_any(
        self,
        *,
        node_id: UUID,
        space_id: UUID,
        reference_material_id: UUID | None,
        graph_result: dict[str, Any],
        user_id: UUID,
    ) -> None:
        if reference_material_id is None:
            return
        parsed = graph_result.get("parsed_reference_data") or {}
        if not parsed.get("reference_images"):
            return
        await persist_reference_images_to_node_media(
            self.session,
            node_id=node_id,
            space_id=space_id,
            reference_material_id=reference_material_id,
            structured_data=parsed,
            uploaded_by=user_id,
        )

    # ── generate ───────────────────────────────────────────────────────

    async def generate_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialGenerateRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """First-time generation via LangGraph (includes LlamaParse when PDF attached)."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        # Capture before any commit — ORM attributes expire after commit in async sessions.
        space_id = node.space_id

        graph_result = await run_study_material_generation(
            session=self.session,
            node_id=node_id,
            reference_material_id=request.reference_material_id,
        )
        graph_result["node_title"] = node.title

        await self._persist_reference_images_if_any(
            node_id=node_id,
            space_id=space_id,
            reference_material_id=request.reference_material_id,
            graph_result=graph_result,
            user_id=user_id,
        )

        return await self._persist_new_version(
            node_id=node_id,
            space_id=space_id,
            graph_result=graph_result,
            generation_type="generate",
            user_id=user_id,
            reference_material_id=request.reference_material_id,
            based_on_version_id=None,
        )

    # ── regenerate ─────────────────────────────────────────────────────

    async def regenerate_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialRegenerateRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialFeedbackResponse:
        """Rewrite active draft using mentor feedback. Skips LlamaParse."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        space_id = node.space_id

        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        if active is None:
            raise StudyMaterialNoActiveVersionException()

        reference_material_id = active.reference_material_id
        based_on_version_id = active.version_id
        current_draft_content = active.content

        graph_result = await run_study_material_regeneration(
            session=self.session,
            node_id=node_id,
            current_draft_content=current_draft_content,
            mentor_regeneration_goal=request.mentor_regeneration_goal,
            reference_material_id=reference_material_id,
        )
        graph_result["node_title"] = node.title

        if graph_result.get("regenerate_status") == "vague":
            return StudyMaterialFeedbackResponse(
                has_new_version=False,
                status="regeneration_goal_too_vague",
                status_message=graph_result.get("llm_output_content"),
                new_version=None,
            )

        new_version = await self._persist_new_version(
            node_id=node_id,
            space_id=space_id,
            graph_result=graph_result,
            generation_type="regenerate",
            user_id=user_id,
            mentor_feedback_used=request.mentor_regeneration_goal,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on_version_id,
        )

        return StudyMaterialFeedbackResponse(
            has_new_version=True,
            new_version_id=new_version.version_id,
            status="ok",
            new_version=new_version,
        )

    # ── improve ────────────────────────────────────────────────────────

    async def improve_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialImproveRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialFeedbackResponse:
        """Surgical improvement of active draft via LangGraph. Skips LlamaParse."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        space_id = node.space_id

        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        if active is None:
            raise StudyMaterialNoActiveVersionException()

        reference_material_id = active.reference_material_id
        based_on_version_id = active.version_id
        current_draft_content = active.content

        graph_result = await run_study_material_improve(
            session=self.session,
            node_id=node_id,
            current_draft_content=current_draft_content,
            mentor_feedback=request.mentor_feedback,
            reference_material_id=reference_material_id,
        )
        graph_result["node_title"] = node.title

        if graph_result.get("improve_status") == "vague":
            return StudyMaterialFeedbackResponse(
                has_new_version=False,
                status="feedback_too_vague",
                status_message=graph_result.get("llm_output_content"),
                new_version=None,
            )

        new_version = await self._persist_new_version(
            node_id=node_id,
            space_id=space_id,
            graph_result=graph_result,
            generation_type="improve",
            user_id=user_id,
            mentor_feedback_used=request.mentor_feedback,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on_version_id,
        )

        return StudyMaterialFeedbackResponse(
            has_new_version=True,
            new_version_id=new_version.version_id,
            status="ok",
            new_version=new_version,
        )

    # ── manual edit ────────────────────────────────────────────────────

    async def manual_edit_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialManualEditRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Creates vN+1 directly from mentor rich-text input. No LLM call."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        space_id = node.space_id

        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        based_on = active.version_id if active is not None else None
        reference_material_id = active.reference_material_id if active else None

        if active is not None:
            await repo.deactivate_version(active)

        next_version = await repo.get_next_version_number(node_id)
        version = await repo.create_version(
            node_id=node_id,
            space_id=space_id,
            version_number=next_version,
            content=request.content,
            generation_type="manual_edit",
            mentor_feedback_used=None,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on,
            llm_model_used=None,
            prompt_snapshot=None,
            token_usage=None,
            is_active=True,
            created_by=user_id,
        )
        log_study_material_version(
            topic_title=node.title,
            version_number=next_version,
            generation_type="manual_edit",
            version_id=str(version.version_id),
            node_id=str(node_id),
            content=request.content,
            graph_result={},
            mentor_feedback_used=None,
        )
        return StudyMaterialVersionOut.model_validate(version)

    # ── publish preview / confirm ──────────────────────────────────────

    async def _load_publish_target(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> tuple:
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        space = await _get_space_and_assert_owner(self.session, node.space_id, user_id)
        if not space.is_published:
            raise StudyMaterialPublishBlockedSpaceUnpublishedException()

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if version.is_published:
            raise StudyMaterialVersionAlreadyPublishedException()
        return node, version, repo

    async def preview_publish_study_material(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialPublishPreviewOut:
        """Return pre-publish confirmation requirements without writing."""
        _, version, repo = await self._load_publish_target(
            node_id, version_id, user_id, role
        )
        previous = await repo.get_published_version(node_id)
        new_label = build_version_display_label(
            version.version_number, version.generation_type
        )

        has_draft_quizzes = False
        has_published_quizzes = False
        draft_quiz_count = 0
        previous_label: str | None = None
        current_published_label: str | None = None
        is_republishing_older = False

        if previous is not None:
            previous_label = build_version_display_label(
                previous.version_number, previous.generation_type
            )
            current_published_label = previous_label
            is_republishing_older = version.version_number < previous.version_number

            if previous.version_id != version.version_id:
                linked = await get_quizzes_linked_to_study_material_version(
                    self.session,
                    node_id=node_id,
                    study_material_version_id=previous.version_id,
                )
                draft_quizzes, published_quizzes = partition_quizzes_by_publish_state(
                    linked
                )
                has_draft_quizzes = len(draft_quizzes) > 0
                has_published_quizzes = len(published_quizzes) > 0
                draft_quiz_count = len(draft_quizzes)

        requires_confirmation = has_draft_quizzes or has_published_quizzes
        return StudyMaterialPublishPreviewOut(
            requires_confirmation=requires_confirmation,
            has_draft_quizzes=has_draft_quizzes,
            has_published_quizzes=has_published_quizzes,
            draft_quiz_count=draft_quiz_count,
            previous_version_label=previous_label,
            new_version_label=new_label,
            is_republishing_older=is_republishing_older,
            current_published_version_label=current_published_label,
        )

    async def publish_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialPublishRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Publish a version with atomic quiz cascade when switching versions."""
        _, version, repo = await self._load_publish_target(
            node_id, request.version_id, user_id, role
        )
        previous = await repo.get_published_version(node_id)

        published = await execute_publish_version_cascade(
            self.session,
            node_id=node_id,
            target_version=version,
            previous_published_version=previous,
            published_by=user_id,
        )
        return StudyMaterialVersionOut.model_validate(published)

    async def preview_unpublish_study_material(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialUnpublishPreviewOut:
        """Return pre-unpublish confirmation requirements without writing."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if not version.is_published:
            raise StudyMaterialVersionNotPublishedException()

        linked = await get_quizzes_linked_to_study_material_version(
            self.session,
            node_id=node_id,
            study_material_version_id=version.version_id,
        )
        draft_quizzes, published_quizzes = partition_quizzes_by_publish_state(linked)
        version_label = build_version_display_label(
            version.version_number, version.generation_type
        )

        return StudyMaterialUnpublishPreviewOut(
            requires_confirmation=True,
            has_draft_quizzes=len(draft_quizzes) > 0,
            has_published_quizzes=len(published_quizzes) > 0,
            version_label=version_label,
        )

    async def unpublish_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialPublishRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Unpublish version; cascade-unpublish linked quizzes; retain drafts."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(request.version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if not version.is_published:
            raise StudyMaterialVersionNotPublishedException()

        unpublished = await execute_unpublish_version_cascade(
            self.session,
            node_id=node_id,
            version=version,
        )
        return StudyMaterialVersionOut.model_validate(unpublished)

    # ── activate ───────────────────────────────────────────────────────

    async def activate_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialActivateRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Atomically deactivates the current active version and activates the target."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        target = await repo.get_version_by_id(request.version_id)
        if target is None or target.node_id != node_id:
            raise StudyMaterialVersionMismatchException()

        if target.is_archived:
            target = await repo.unarchive_version(target)

        current_active = await repo.get_active_version(node_id)
        if (
            current_active is not None
            and current_active.version_id != target.version_id
        ):
            await repo.deactivate_version(current_active)

        target = await repo.activate_version(target)
        return StudyMaterialVersionOut.model_validate(target)

    # ── archive / unarchive ──────────────────────────────────────────

    async def archive_study_material_version(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Soft-hide a version from the working history shelf."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if version.is_archived:
            raise StudyMaterialVersionAlreadyArchivedException()
        if version.is_published:
            raise StudyMaterialCannotArchivePublishedException()

        version = await repo.archive_version(version, archived_by=user_id)
        return StudyMaterialVersionOut.model_validate(version)

    async def unarchive_study_material_version(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Restore an archived version to the working history shelf."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if not version.is_archived:
            raise StudyMaterialVersionNotArchivedException()

        version = await repo.unarchive_version(version)
        return StudyMaterialVersionOut.model_validate(version)

    # ── list versions ──────────────────────────────────────────────────

    async def list_versions(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
        *,
        archived: bool = False,
    ) -> StudyMaterialVersionHistoryOut:
        """Returns versions ordered by version_number DESC.

        archived=False — working history (default).
        archived=True — archive shelf.
        """
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        if role == "mentor":
            await repo.reconcile_published_versions(node_id)
        versions = await repo.get_all_versions(node_id, archived=archived)
        all_versions = await repo.get_all_versions(node_id, archived=None)
        version_lookup = {v.version_id: v for v in all_versions}
        summaries = [
            StudyMaterialVersionSummary.from_version_row(
                v, version_lookup=version_lookup
            )
            for v in versions
        ]
        return StudyMaterialVersionHistoryOut(
            node_id=node_id,
            versions=summaries,
            total=len(summaries),
        )

    # ── get single version ─────────────────────────────────────────────

    async def get_version(
        self, node_id: UUID, version_id: UUID, user_id: UUID, role: str
    ) -> StudyMaterialVersionOut:
        """Fetch a single version by ID. Validates it belongs to the node."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialNotFoundException()

        return StudyMaterialVersionOut.model_validate(version)

    # ── active version ─────────────────────────────────────────────────

    async def get_active_version(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> StudyMaterialVersionOut | None:
        """Return the current active study material version for a node, if any."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        if active is None:
            return None
        return StudyMaterialVersionOut.model_validate(active)

    async def get_mentor_ui_state(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
        *,
        viewing_version_id: UUID | None = None,
    ) -> StudyMaterialMentorUiStateOut:
        """Resolve mentor study-material UI flags and allowed actions."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        space = await _get_space_and_assert_owner(self.session, node.space_id, user_id)
        space_is_published = bool(space.is_published)

        node_repo = NodeRepository(self.session)
        ancestors = await node_repo.get_ancestors(node)
        parts = resolve_effective_instruction_parts(node, ancestors)
        # Use the SAME canonical formatter used at generation time so the
        # stored snapshot and this freshly-resolved string are directly
        # comparable. Comparing differently-formatted strings made
        # instruction_changed_since_generation true on every reload/navigation.
        current_instruction = format_effective_instruction(parts)

        sm_repo = StudyMaterialRepository(self.session)
        all_versions = await sm_repo.get_all_versions(node_id, archived=None)
        active = await sm_repo.get_active_version(node_id)
        has_versions = len(all_versions) > 0

        generation_snapshot: str | None = None
        instruction_changed = False
        if active is not None:
            generation_snapshot = extract_effective_instruction_snapshot(
                active.prompt_snapshot
            )
            if generation_snapshot is not None:
                instruction_changed = generation_snapshot != current_instruction

        displayed_version = None
        target_version_id = viewing_version_id or (
            active.version_id if active is not None else None
        )
        published = await sm_repo.get_published_version(node_id)
        if target_version_id is not None:
            target = await sm_repo.get_version_by_id(target_version_id)
            if target is not None and target.node_id == node_id:
                displayed_version = compute_version_allowed_actions(
                    version_id=target.version_id,
                    version_number=target.version_number,
                    generation_type=target.generation_type,
                    is_active=target.is_active,
                    is_published=target.is_published,
                    is_archived=target.is_archived,
                    active_version_id=active.version_id if active else None,
                    viewing_version_id=viewing_version_id,
                    published_version_id=published.version_id if published else None,
                    published_version_number=(
                        published.version_number if published else None
                    ),
                    published_generation_type=(
                        published.generation_type if published else None
                    ),
                    space_is_published=space_is_published,
                )

        can_access_quiz = bool(
            space_is_published
            and published is not None
            and (published.content or "").strip()
        )

        return StudyMaterialMentorUiStateOut(
            node_id=node_id,
            has_versions=has_versions,
            active_version_id=active.version_id if active else None,
            published_version_id=published.version_id if published else None,
            can_access_study_material=has_versions,
            can_access_quiz=can_access_quiz,
            instruction_changed_since_generation=instruction_changed,
            current_effective_instruction=current_instruction,
            generation_instruction_snapshot=generation_snapshot,
            displayed_version_actions=displayed_version,
        )

    # ── clear all drafts ───────────────────────────────────────────────

    async def get_clear_drafts_eligibility(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> StudyMaterialClearDraftsEligibilityOut:
        """Check whether all study material drafts can be cleared for a node."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        sm_repo = StudyMaterialRepository(self.session)
        quiz_repo = QuizRepository(self.session)
        versions = await sm_repo.get_all_versions(node_id, archived=None)
        version_count = len(versions)
        quiz_count = await quiz_repo.count_quizzes_for_node(node_id)

        if version_count == 0:
            return StudyMaterialClearDraftsEligibilityOut(
                can_clear=False,
                version_count=0,
                quiz_count=quiz_count,
                block_reason="No study material drafts exist for this topic.",
            )

        if quiz_count > 0:
            noun = "quiz" if quiz_count == 1 else "quizzes"
            return StudyMaterialClearDraftsEligibilityOut(
                can_clear=False,
                version_count=version_count,
                quiz_count=quiz_count,
                block_reason=(
                    f"This topic has {quiz_count} {noun}. "
                    "Delete the quiz before clearing study material drafts."
                ),
            )

        published_count = sum(1 for v in versions if v.is_published)
        if published_count > 0:
            noun = "version is" if published_count == 1 else "versions are"
            return StudyMaterialClearDraftsEligibilityOut(
                can_clear=False,
                version_count=version_count,
                quiz_count=0,
                block_reason=(
                    f"{published_count} published {noun} visible to trainees. "
                    "Unpublish before clearing drafts."
                ),
            )

        return StudyMaterialClearDraftsEligibilityOut(
            can_clear=True,
            version_count=version_count,
            quiz_count=0,
            block_reason=None,
        )

    async def clear_all_drafts(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> StudyMaterialClearDraftsOut:
        """Delete all study material versions so the mentor can generate fresh content."""
        eligibility = await self.get_clear_drafts_eligibility(node_id, user_id, role)
        if not eligibility.can_clear:
            if eligibility.quiz_count > 0:
                raise StudyMaterialClearDraftsBlockedByQuizException(
                    eligibility.quiz_count
                )
            raise StudyMaterialNoDraftsException()

        sm_repo = StudyMaterialRepository(self.session)
        deleted_count = await sm_repo.delete_all_versions_for_node(node_id)
        return StudyMaterialClearDraftsOut(
            node_id=node_id,
            deleted_count=deleted_count,
        )

    async def get_space_published_resources(
        self, space_id: UUID, user_id: UUID, role: str
    ) -> SpacePublishedResourcesResponse:
        """Resolve all published topics, study materials, and quizzes in a space."""
        _assert_mentor(role)
        await _assert_space_access(self.session, space_id, user_id, role)

        from sqlalchemy import and_, select

        from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
        from src.api.data.models.postgres.e_learning_content.study_material_versions import (
            StudyMaterialVersion,
        )
        from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode

        # Fetch active nodes
        nodes_stmt = select(TopicNode).where(
            and_(
                TopicNode.space_id == space_id,
                TopicNode.is_active.is_(True),
            )
        )
        nodes_res = await self.session.execute(nodes_stmt)
        nodes = list(nodes_res.scalars().all())

        # Fetch published study materials
        sm_stmt = select(StudyMaterialVersion).where(
            and_(
                StudyMaterialVersion.space_id == space_id,
                StudyMaterialVersion.is_published.is_(True),
            )
        )
        sm_res = await self.session.execute(sm_stmt)
        sms = list(sm_res.scalars().all())

        # Fetch published quizzes
        quiz_stmt = select(Quiz).where(
            and_(
                Quiz.space_id == space_id,
                Quiz.is_published.is_(True),
            )
        )
        quiz_res = await self.session.execute(quiz_stmt)
        quizzes = list(quiz_res.scalars().all())

        # Combine
        sm_map = {sm.node_id: sm.version_id for sm in sms}
        quiz_map = {q.node_id: q.quiz_id for q in quizzes}

        published_topics = []
        for node in nodes:
            version_id = sm_map.get(node.node_id)
            quiz_id = quiz_map.get(node.node_id)
            if version_id or quiz_id:
                published_topics.append(
                    PublishedResourceTopicSummary(
                        node_id=node.node_id,
                        topic_title=node.title,
                        published_study_material_version_id=version_id,
                        published_quiz_id=quiz_id,
                    )
                )

        return SpacePublishedResourcesResponse(
            space_id=space_id,
            published_topics=published_topics,
        )

    async def get_space_republish_checklist(
        self, space_id: UUID, user_id: UUID, role: str
    ) -> SpaceRepublishChecklistOut:
        """List per-node content mentors can re-publish after espace republish."""
        _assert_mentor(role)
        await _assert_space_access(self.session, space_id, user_id, role)

        from sqlalchemy import and_, select

        from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
        from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode

        nodes_stmt = select(TopicNode).where(
            and_(
                TopicNode.space_id == space_id,
                TopicNode.is_active.is_(True),
            )
        )
        nodes_res = await self.session.execute(nodes_stmt)
        nodes = list(nodes_res.scalars().all())

        sm_repo = StudyMaterialRepository(self.session)
        checklist: list[RepublishChecklistNodeOut] = []

        for node in nodes:
            versions = await sm_repo.get_all_versions(node.node_id, archived=False)
            publishable_versions = [v for v in versions if (v.content or "").strip()]
            latest_sm = (
                max(publishable_versions, key=lambda v: v.version_number)
                if publishable_versions
                else None
            )

            quiz_stmt = (
                select(Quiz)
                .where(
                    and_(
                        Quiz.node_id == node.node_id,
                        Quiz.space_id == space_id,
                        Quiz.is_published.is_(False),
                    )
                )
                .order_by(Quiz.created_at.desc())
            )
            quiz_res = await self.session.execute(quiz_stmt)
            draft_quiz = quiz_res.scalars().first()

            if latest_sm is None and draft_quiz is None:
                continue

            checklist.append(
                RepublishChecklistNodeOut(
                    node_id=node.node_id,
                    node_title=node.title,
                    last_published_version_id=(
                        latest_sm.version_id if latest_sm is not None else None
                    ),
                    last_published_version_label=(
                        build_version_display_label(
                            latest_sm.version_number, latest_sm.generation_type
                        )
                        if latest_sm is not None
                        else None
                    ),
                    has_unpublished_quiz=draft_quiz is not None,
                    quiz_id=draft_quiz.quiz_id if draft_quiz is not None else None,
                    quiz_title=draft_quiz.title if draft_quiz is not None else None,
                )
            )

        return SpaceRepublishChecklistOut(
            space_id=space_id,
            nodes_with_publishable_material=checklist,
        )
