"""Tests for EC-17 reference material replacement on upload."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.sql.dml import Update

from src.api.core.services.study_agent_services.reference_material_service import (
    ReferenceMaterialService,
)
from src.api.data.models.postgres.e_learning_content.reference_materials import (
    ReferenceMaterial,
)
from src.api.data.repositories.study_agent_repositories.reference_material_repository import (
    ReferenceMaterialRepository,
)


def _make_material(
    *,
    material_id: UUID | None = None,
    node_id: UUID | None = None,
    space_id: UUID | None = None,
    scope: str = "node",
    title: str = "test.pdf",
    deleted_at: datetime | None = None,
    created_at: datetime | None = None,
) -> ReferenceMaterial:
    now = created_at or datetime.now(UTC)
    return ReferenceMaterial(
        material_id=material_id or uuid4(),
        space_id=space_id or uuid4(),
        node_id=node_id,
        title=title,
        scope=scope,
        file_url="/tmp/test.pdf",
        file_name="test.pdf",
        file_size_bytes=100,
        mime_type="application/pdf",
        is_visible_to_trainees=True,
        uploaded_by=uuid4(),
        created_at=now,
        updated_at=now,
        deleted_at=deleted_at,
    )


def _upload_file(name: str = "doc.pdf", content: bytes = b"%PDF-1.4") -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


class InMemoryReferenceMaterialRepository(ReferenceMaterialRepository):
    """In-memory repository for EC-17 upload flow tests."""

    def __init__(self, materials: list[ReferenceMaterial]) -> None:
        self._materials = materials
        super().__init__(MagicMock())

    async def soft_delete_active_for_node(self, node_id: UUID) -> int:
        count = 0
        now = datetime.now(UTC)
        for material in self._materials:
            if (
                material.node_id == node_id
                and material.scope == "node"
                and material.deleted_at is None
            ):
                material.deleted_at = now
                count += 1
        return count

    async def soft_delete_active_for_space(self, space_id: UUID) -> int:
        count = 0
        now = datetime.now(UTC)
        for material in self._materials:
            if (
                material.space_id == space_id
                and material.scope == "space"
                and material.deleted_at is None
            ):
                material.deleted_at = now
                count += 1
        return count

    async def create_reference_material_with_id(
        self,
        material_id: UUID,
        space_id: UUID,
        node_id: UUID | None,
        title: str,
        scope: str,
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
        self._materials.append(material)
        return material

    async def get_by_node(self, node_id: UUID) -> list[ReferenceMaterial]:
        return [
            material
            for material in self._materials
            if material.node_id == node_id
            and material.scope == "node"
            and material.deleted_at is None
        ]

    async def get_latest_by_node(self, node_id: UUID) -> ReferenceMaterial | None:
        active = await self.get_by_node(node_id)
        if not active:
            return None
        return max(active, key=lambda material: material.created_at)


def test_soft_delete_active_for_node_issues_bulk_update() -> None:
    async def _run() -> None:
        node_id = uuid4()
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(rowcount=2))
        session.flush = AsyncMock()

        repo = ReferenceMaterialRepository(session)
        deleted_count = await repo.soft_delete_active_for_node(node_id)

        session.execute.assert_awaited_once()
        statement = session.execute.await_args.args[0]
        assert isinstance(statement, Update)
        assert deleted_count == 2
        session.flush.assert_awaited_once()

    asyncio.run(_run())


def test_soft_delete_active_for_space_issues_bulk_update() -> None:
    async def _run() -> None:
        space_id = uuid4()
        session = MagicMock()
        session.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        session.flush = AsyncMock()

        repo = ReferenceMaterialRepository(session)
        deleted_count = await repo.soft_delete_active_for_space(space_id)

        session.execute.assert_awaited_once()
        statement = session.execute.await_args.args[0]
        assert isinstance(statement, Update)
        assert deleted_count == 1
        session.flush.assert_awaited_once()

    asyncio.run(_run())


def test_upload_twice_to_same_node_leaves_one_active_row() -> None:
    """EC-17: second upload soft-deletes the first; only the latest stays active."""

    async def _run() -> None:
        node_id = uuid4()
        space_id = uuid4()
        user_id = uuid4()
        materials: list[ReferenceMaterial] = []

        first_id = uuid4()
        first_created = datetime(2026, 1, 1, tzinfo=UTC)
        materials.append(
            _make_material(
                material_id=first_id,
                node_id=node_id,
                space_id=space_id,
                title="first.pdf",
                created_at=first_created,
            )
        )

        repo = InMemoryReferenceMaterialRepository(materials)
        service = ReferenceMaterialService(MagicMock())

        with (
            patch(
                "src.api.core.services.study_agent_services.reference_material_service._get_space_and_assert_owner",
                new_callable=AsyncMock,
            ),
            patch(
                "src.api.core.services.study_agent_services.reference_material_service.upload_bytes",
                new_callable=AsyncMock,
                return_value="/tmp/second.pdf",
            ),
            patch(
                "src.api.core.services.study_agent_services.reference_material_service.ReferenceMaterialRepository",
                return_value=repo,
            ),
        ):
            second = await service.upload_reference_material(
                space_id=space_id,
                file=_upload_file("second.pdf"),
                title="second.pdf",
                scope="node",
                node_id=node_id,
                is_visible_to_trainees=True,
                user_id=user_id,
                role="mentor",
            )

        active = await repo.get_by_node(node_id)
        assert len(active) == 1
        assert active[0].material_id == second.material_id

        first = next(
            material for material in materials if material.material_id == first_id
        )
        assert first.deleted_at is not None

        latest = await repo.get_latest_by_node(node_id)
        assert latest is not None
        assert latest.material_id == second.material_id

    asyncio.run(_run())


def test_upload_reference_material_soft_deletes_prior_node_materials() -> None:
    async def _run() -> None:
        node_id = uuid4()
        space_id = uuid4()
        user_id = uuid4()
        mock_repo = MagicMock()
        mock_repo.soft_delete_active_for_node = AsyncMock(return_value=1)
        mock_repo.soft_delete_active_for_space = AsyncMock(return_value=0)
        mock_repo.create_reference_material_with_id = AsyncMock(
            return_value=_make_material(node_id=node_id, space_id=space_id)
        )

        service = ReferenceMaterialService(MagicMock())

        with (
            patch(
                "src.api.core.services.study_agent_services.reference_material_service._get_space_and_assert_owner",
                new_callable=AsyncMock,
            ),
            patch(
                "src.api.core.services.study_agent_services.reference_material_service.upload_bytes",
                new_callable=AsyncMock,
                return_value="/tmp/upload.pdf",
            ),
            patch(
                "src.api.core.services.study_agent_services.reference_material_service.ReferenceMaterialRepository",
                return_value=mock_repo,
            ),
        ):
            await service.upload_reference_material(
                space_id=space_id,
                file=_upload_file(),
                title="doc.pdf",
                scope="node",
                node_id=node_id,
                is_visible_to_trainees=True,
                user_id=user_id,
                role="mentor",
            )

        mock_repo.soft_delete_active_for_node.assert_awaited_once_with(node_id)
        mock_repo.soft_delete_active_for_space.assert_not_called()
        mock_repo.create_reference_material_with_id.assert_awaited_once()

    asyncio.run(_run())


def test_upload_reference_material_soft_deletes_prior_space_materials() -> None:
    async def _run() -> None:
        space_id = uuid4()
        user_id = uuid4()
        mock_repo = MagicMock()
        mock_repo.soft_delete_active_for_node = AsyncMock(return_value=0)
        mock_repo.soft_delete_active_for_space = AsyncMock(return_value=1)
        mock_repo.create_reference_material_with_id = AsyncMock(
            return_value=_make_material(node_id=None, space_id=space_id, scope="space")
        )

        service = ReferenceMaterialService(MagicMock())

        with (
            patch(
                "src.api.core.services.study_agent_services.reference_material_service._get_space_and_assert_owner",
                new_callable=AsyncMock,
            ),
            patch(
                "src.api.core.services.study_agent_services.reference_material_service.upload_bytes",
                new_callable=AsyncMock,
                return_value="/tmp/upload.pdf",
            ),
            patch(
                "src.api.core.services.study_agent_services.reference_material_service.ReferenceMaterialRepository",
                return_value=mock_repo,
            ),
        ):
            await service.upload_reference_material(
                space_id=space_id,
                file=_upload_file(),
                title="doc.pdf",
                scope="space",
                node_id=None,
                is_visible_to_trainees=True,
                user_id=user_id,
                role="mentor",
            )

        mock_repo.soft_delete_active_for_space.assert_awaited_once_with(space_id)
        mock_repo.soft_delete_active_for_node.assert_not_called()
        mock_repo.create_reference_material_with_id.assert_awaited_once()

    asyncio.run(_run())
