"""
Service layer for trainee study material delivery.

Handles reading published content and PDF export. Progress side effects
(first-view tracking) and scroll updates go through ``TraineeProgressService``.
"""

import mimetypes
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import (
    NodeMediaNotFoundException,
    StudyMaterialNoPublishedVersionException,
    StudyMaterialPdfGenerationFailedException,
)
from src.api.core.services import (
    TraineeProgressService,
)
from src.api.data.repositories import (
    MentorProgressRepository,
    ReferenceMaterialRepository,
    TraineeStudyRepository,
)
from src.api.schemas.study_material_schemas import (
    TraineeArchivedSmItemOut,
    TraineeArchivedSmListOut,
    TraineeArchivedStudyMaterialOut,
    TraineeStudyMaterialOut,
    TraineeTopicResourceListOut,
)
from src.api.utils.content_lifecycle import (
    list_trainee_archive_quizzes,
    list_trainee_archive_sm,
)
from src.api.utils.content_lifecycle.archive_gates import (
    assert_archived_sm_version,
    assert_trainee_archive_context,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_space_access,
    _assert_trainee,
    _get_node_and_assert_space_access,
)
from src.api.utils.study_agent_utils.media.study_material_pdf import (
    build_study_material_pdf_filename,
    render_study_material_pdf,
)
from src.api.utils.study_agent_utils.version.version_labels import (
    build_version_display_label,
)
from src.api.utils.trainee_study_utils.trainee_topic_resource_utils import (
    _storage_filename,
    build_trainee_topic_resource_from_reference,
    build_trainee_topic_resource_out,
)


class TraineeStudyService:
    """Trainee-facing study material read and PDF download."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TraineeStudyRepository(session)
        self.progress_service = TraineeProgressService(session)

    async def get_published_study_material(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
    ) -> TraineeStudyMaterialOut:
        """Return the published study material body for in-panel reading."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        if role == "trainee":
            await self.progress_service.mark_study_material_viewed(
                node_id=node_id,
                user_id=user_id,
                role=role,
            )

        # Load version AFTER mark_study_material_viewed to avoid expired attributes from the commit inside it
        version = await self.repo.get_published_study_material(node_id)
        if version is None:
            raise StudyMaterialNoPublishedVersionException()

        progress_map = await self.progress_service.get_batch_node_progress(
            node_ids=[node_id],
            user_id=user_id,
            role=role,
        )
        snapshot = progress_map[node_id]

        return TraineeStudyMaterialOut(
            version_id=version.version_id,
            node_id=version.node_id,
            space_id=version.space_id,
            version_number=version.version_number,
            content=version.content,
            reference_material_id=version.reference_material_id,
            published_at=version.published_at,
            study_material_read_percent=snapshot.study_material_read_percent,
            study_material_completed=snapshot.study_material_completed,
        )

    async def download_published_pdf(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
    ) -> tuple[bytes, str]:
        """Render published content as a PDF byte stream + filename."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        version = await self.repo.get_published_study_material(node_id)
        if version is None:
            raise StudyMaterialNoPublishedVersionException()

        try:
            pdf_bytes = render_study_material_pdf(node.title, version.content)
        except ValueError:
            raise StudyMaterialPdfGenerationFailedException() from None

        filename = build_study_material_pdf_filename(node.title)
        return pdf_bytes, filename

    async def list_archived_study_material(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
    ) -> TraineeArchivedSmListOut:
        """List superseded SM versions when archived versions exist on the node."""
        await assert_trainee_archive_context(
            self.session, node_id=node_id, user_id=user_id, role=role
        )
        archived_versions = await list_trainee_archive_sm(self.session, node_id)
        progress_repo = MentorProgressRepository(self.session)
        progress_row = await progress_repo.get_node_progress(user_id, node_id)
        you_read_this = progress_row is not None and progress_row.study_material_viewed

        items: list[TraineeArchivedSmItemOut] = []
        for version in archived_versions:
            archived_quizzes = await list_trainee_archive_quizzes(
                self.session,
                node_id,
                study_material_version_id=version.version_id,
            )
            quiz = archived_quizzes[0] if archived_quizzes else None
            items.append(
                TraineeArchivedSmItemOut(
                    version_id=version.version_id,
                    version_number=version.version_number,
                    version_label=build_version_display_label(
                        version.version_number, version.generation_type
                    ),
                    published_at=version.published_at,
                    superseded_at=version.superseded_at,
                    removed_at=version.superseded_at,
                    can_read_material=True,
                    you_read_this=you_read_this,
                    has_archived_quiz=quiz is not None,
                    archived_quiz_id=quiz.quiz_id if quiz else None,
                )
            )

        published_sm = await self.repo.get_published_study_material(node_id)
        if published_sm is not None:
            current_archived_quizzes = await list_trainee_archive_quizzes(
                self.session,
                node_id,
                study_material_version_id=published_sm.version_id,
            )
            if current_archived_quizzes:
                quiz = current_archived_quizzes[0]
                items.insert(
                    0,
                    TraineeArchivedSmItemOut(
                        version_id=published_sm.version_id,
                        version_number=published_sm.version_number,
                        version_label=build_version_display_label(
                            published_sm.version_number,
                            published_sm.generation_type,
                        ),
                        published_at=published_sm.published_at,
                        superseded_at=None,
                        removed_at=quiz.superseded_at,
                        can_read_material=True,
                        you_read_this=you_read_this,
                        has_archived_quiz=True,
                        archived_quiz_id=quiz.quiz_id,
                        is_current_version=True,
                    ),
                )

        if not items:
            return TraineeArchivedSmListOut(node_id=node_id, versions=[])

        return TraineeArchivedSmListOut(node_id=node_id, versions=items)

    async def get_archived_study_material(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> TraineeArchivedStudyMaterialOut:
        """Read-only archived SM content — no progress writes."""
        await assert_trainee_archive_context(
            self.session, node_id=node_id, user_id=user_id, role=role
        )
        version = await assert_archived_sm_version(
            self.session, node_id=node_id, version_id=version_id
        )
        return TraineeArchivedStudyMaterialOut(
            version_id=version.version_id,
            node_id=version.node_id,
            space_id=version.space_id,
            version_number=version.version_number,
            version_label=build_version_display_label(
                version.version_number, version.generation_type
            ),
            content=version.content,
            reference_material_id=version.reference_material_id,
            published_at=version.published_at,
            superseded_at=version.superseded_at,
        )

    async def download_archived_pdf(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> tuple[bytes, str]:
        """PDF download for an archived SM version (read-only)."""
        _assert_trainee(role)
        node, _space = await assert_trainee_archive_context(
            self.session, node_id=node_id, user_id=user_id, role=role
        )
        version = await assert_archived_sm_version(
            self.session, node_id=node_id, version_id=version_id
        )
        try:
            pdf_bytes = render_study_material_pdf(node.title, version.content)
        except ValueError:
            raise StudyMaterialPdfGenerationFailedException() from None
        filename = build_study_material_pdf_filename(
            f"{node.title}-v{version.version_number}"
        )
        return pdf_bytes, filename

    async def list_topic_resources(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
    ) -> TraineeTopicResourceListOut:
        """List mentor-attached topic resources for trainees."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = ReferenceMaterialRepository(self.session)
        visible_refs = await repo.get_visible_by_node(node_id)
        ref_resources = [
            build_trainee_topic_resource_from_reference(
                item, node_id=node_id, order_index=index
            )
            for index, item in enumerate(visible_refs)
        ]
        ref_offset = len(ref_resources)
        node_media = await repo.get_media_by_node(node_id)
        media_resources = [
            build_trainee_topic_resource_out(
                item,
                node_id=node_id,
            ).model_copy(update={"order_index": ref_offset + item.order_index})
            for item in node_media
        ]
        resources = ref_resources + media_resources
        return TraineeTopicResourceListOut(
            node_id=node_id,
            items=resources,
            total=len(resources),
        )

    async def get_topic_resource_file(
        self,
        node_id: UUID,
        media_id: UUID,
        user_id: UUID,
        role: str,
        *,
        as_attachment: bool,
    ) -> tuple[bytes, str, str, str]:
        """Return file bytes, filename, mime type, and Content-Disposition value."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = ReferenceMaterialRepository(self.session)
        media = await repo.get_media_by_id(media_id)
        if media is None or media.node_id != node_id:
            raise NodeMediaNotFoundException()
        if media.media_type not in ("image", "pdf") or not media.file_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This resource cannot be downloaded as a file.",
            )

        file_path = Path(media.file_url.replace("\\", "/"))
        if not file_path.is_file():
            raise NodeMediaNotFoundException()

        filename = _storage_filename(media.file_url)
        mime_type = mimetypes.guess_type(filename)[0] or (
            "application/pdf"
            if media.media_type == "pdf"
            else "application/octet-stream"
        )
        disposition = "attachment" if as_attachment else "inline"
        content_disposition = f'{disposition}; filename="{filename}"'
        return file_path.read_bytes(), filename, mime_type, content_disposition

    async def get_reference_material_file(
        self,
        node_id: UUID,
        material_id: UUID,
        user_id: UUID,
        role: str,
        *,
        as_attachment: bool,
    ) -> tuple[bytes, str, str, str]:
        """Return file bytes for a trainee-visible reference material."""
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = ReferenceMaterialRepository(self.session)
        material = await repo.get_by_id(material_id)
        if (
            material is None
            or material.deleted_at is not None
            or material.node_id != node_id
            or not material.is_visible_to_trainees
        ):
            raise NodeMediaNotFoundException()

        file_path = Path(material.file_url.replace("\\", "/"))
        if not file_path.is_file():
            raise NodeMediaNotFoundException()

        filename = material.file_name
        mime_type = (
            material.mime_type
            or mimetypes.guess_type(filename)[0]
            or ("application/octet-stream")
        )
        disposition = "attachment" if as_attachment else "inline"
        content_disposition = f'{disposition}; filename="{filename}"'
        return file_path.read_bytes(), filename, mime_type, content_disposition
