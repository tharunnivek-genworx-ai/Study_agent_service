"""
Service layer for trainee study material delivery.

Handles reading published content and PDF export. Progress side effects
(first-view tracking) and scroll updates go through ``TraineeProgressService``.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.study_material_exceptions.study_material_exceptions import (
    StudyMaterialNoPublishedVersionException,
    StudyMaterialPdfGenerationFailedException,
)
from src.api.core.services.progress_services.trainee_progress_service import (
    TraineeProgressService,
)
from src.api.data.repositories.trainee_study_repositories.trainee_study_repository import (
    TraineeStudyRepository,
)
from src.api.schemas.study_material_schemas.study_material_schema import (
    TraineeStudyMaterialOut,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_space_access,
    _assert_trainee,
    _get_node_and_assert_space_access,
)
from src.api.utils.study_agent_utils.study_material_pdf import (
    build_study_material_pdf_filename,
    render_study_material_pdf,
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
