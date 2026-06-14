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
    StudyMaterialNoPublishedVersionException,
    StudyMaterialNotFoundException,
    StudyMaterialPdfGenerationFailedException,
    StudyMaterialVersionAlreadyArchivedException,
    StudyMaterialVersionAlreadyPublishedException,
    StudyMaterialVersionMismatchException,
    StudyMaterialVersionNotArchivedException,
    StudyMaterialVersionNotPublishedException,
)
from src.api.data.repositories.progress_repositories.trainee_node_progress_repository import (
    TraineeNodeProgressRepository,
)
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.space_node_repository.node_repository import (
    NodeRepository,
)
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.schemas.study_material_schemas.study_material_schema import (
    StudyMaterialActivateRequest,
    StudyMaterialClearDraftsEligibilityOut,
    StudyMaterialClearDraftsOut,
    StudyMaterialGenerateRequest,
    StudyMaterialImproveRequest,
    StudyMaterialManualEditRequest,
    StudyMaterialMentorUiStateOut,
    StudyMaterialProgressOut,
    StudyMaterialProgressUpdateRequest,
    StudyMaterialPublishRequest,
    StudyMaterialRegenerateRequest,
    StudyMaterialVersionHistoryOut,
    StudyMaterialVersionOut,
    StudyMaterialVersionSummary,
    TraineeStudyMaterialOut,
)
from src.api.utils.content_utils.node_access import _get_node_and_assert_space_access
from src.api.utils.space_node_utils.build_node import (
    format_effective_instruction,
    resolve_effective_instruction_parts,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_mentor,
    _assert_space_access,
    _assert_trainee,
)
from src.api.utils.study_agent_utils.instruction_snapshot import (
    embed_effective_instruction_snapshot,
    extract_effective_instruction_snapshot,
)
from src.api.utils.study_agent_utils.node_media_persistence import (
    persist_reference_images_to_node_media,
)
from src.api.utils.study_agent_utils.study_material_artifacts import (
    log_study_material_version,
)
from src.api.utils.study_agent_utils.study_material_pdf import (
    build_study_material_pdf_filename,
    render_study_material_pdf,
)
from src.api.utils.study_agent_utils.version_actions import (
    compute_version_allowed_actions,
)


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
    ) -> StudyMaterialVersionOut:
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

        return await self._persist_new_version(
            node_id=node_id,
            space_id=space_id,
            graph_result=graph_result,
            generation_type="regenerate",
            user_id=user_id,
            mentor_feedback_used=request.mentor_regeneration_goal,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on_version_id,
        )

    # ── improve ────────────────────────────────────────────────────────

    async def improve_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialImproveRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
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

        return await self._persist_new_version(
            node_id=node_id,
            space_id=space_id,
            graph_result=graph_result,
            generation_type="improve",
            user_id=user_id,
            mentor_feedback_used=request.mentor_feedback,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on_version_id,
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

    # ── publish ────────────────────────────────────────────────────────

    async def publish_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialPublishRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Sets is_published=True on a specific version."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(request.version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()

        if version.is_published:
            raise StudyMaterialVersionAlreadyPublishedException()

        version = await repo.publish_version(version, published_by=user_id)
        return StudyMaterialVersionOut.model_validate(version)

    async def unpublish_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialPublishRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Clears is_published on a specific version (hides from trainees)."""
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

        version = await repo.unpublish_version(version)
        return StudyMaterialVersionOut.model_validate(version)

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
        if target_version_id is not None:
            target = await sm_repo.get_version_by_id(target_version_id)
            if target is not None and target.node_id == node_id:
                displayed_version = compute_version_allowed_actions(
                    version_id=target.version_id,
                    is_active=target.is_active,
                    is_published=target.is_published,
                    is_archived=target.is_archived,
                    active_version_id=active.version_id if active else None,
                    viewing_version_id=viewing_version_id,
                )

        can_access_quiz = bool(
            has_versions and active is not None and (active.content or "").strip()
        )

        return StudyMaterialMentorUiStateOut(
            node_id=node_id,
            has_versions=has_versions,
            active_version_id=active.version_id if active else None,
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

    # ── trainee: get published ─────────────────────────────────────────

    async def get_published(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> TraineeStudyMaterialOut:
        """Returns the is_published=True version for a node. Trainee-safe."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_published_version(node_id)
        if version is None:
            raise StudyMaterialNoPublishedVersionException()

        # Serialize BEFORE any commit. session.commit() expires all ORM-instance
        # attributes (expire_on_commit=True is the default). If we committed first
        # and then called model_validate, Pydantic would touch published_at /
        # content / etc. on an expired instance, triggering an implicit async
        # reload that has no greenlet context → MissingGreenlet crash.
        result = TraineeStudyMaterialOut.model_validate(version)

        if role == "trainee":
            progress_repo = TraineeNodeProgressRepository(self.session)
            await progress_repo.mark_study_material_viewed(
                user_id, node_id, node.space_id
            )
            await self.session.commit()

        return result

    async def download_published_pdf(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> tuple[bytes, str]:
        """Render the published study material as a PDF for trainees."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_published_version(node_id)
        if version is None:
            raise StudyMaterialNoPublishedVersionException()

        try:
            pdf_bytes = render_study_material_pdf(node.title, version.content)
        except ValueError:
            raise StudyMaterialPdfGenerationFailedException() from None

        filename = build_study_material_pdf_filename(node.title)
        return pdf_bytes, filename

    async def update_study_material_progress(
        self,
        node_id: UUID,
        request: StudyMaterialProgressUpdateRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialProgressOut:
        """Trainee scroll progress — backend keeps the max read_percent (TDD §3.2.4)."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        published = await repo.get_published_version(node_id)
        if published is None:
            raise StudyMaterialNoPublishedVersionException()

        progress_repo = TraineeNodeProgressRepository(self.session)
        row = await progress_repo.update_read_progress(
            user_id, node_id, node.space_id, request.read_percent
        )
        # Serialize before commit — same expire-on-commit safety as get_published.
        result = StudyMaterialProgressOut.model_validate(row)
        await self.session.commit()
        return result
