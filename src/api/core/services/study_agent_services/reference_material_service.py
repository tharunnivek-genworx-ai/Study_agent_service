# src/api/core/services/content_service/reference_material_service.py
"""
Reference material and node media service.

Reference materials (TDD §3.3.2):
  UPLOAD     → validate ownership → scope/node_id guard → GCS stub upload
               → insert row (GCS upload first, then DB)
  LIST       → access guard → return active rows for space or node
  VISIBILITY → ownership guard → update is_visible_to_trainees
  DELETE     → ownership guard → soft-delete (set deleted_at)

Node media (TDD §3.3.2):
  ATTACH     → ownership guard → cross-field type/url guard
               → GCS stub for images → insert row
  LIST       → access guard → return active rows ordered by order_index
  REORDER    → ownership guard → validate complete set → bulk update
  DELETE     → ownership guard → hard delete (no soft-delete for media)

GCS upload is a placeholder stub until the GCS client is wired in.
"""

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.study_material_exceptions.reference_material_exceptions import (
    InvalidMediaTypePayloadException,
    NodeMediaNotFoundException,
    NodeMediaReorderIncompleteException,
    ReferenceMaterialNodeScopeMismatchException,
    ReferenceMaterialNotFoundForDeleteException,
)
from src.api.data.models.postgres.e_learning_content.reference_llamaparse_images import (
    ReferenceLlamaParseImage,
)
from src.api.data.repositories.study_agent_repositories.reference_llamaparse_repository import (
    ReferenceLlamaParseRepository,
)
from src.api.data.repositories.study_agent_repositories.reference_material_repository import (
    ReferenceMaterialRepository,
)
from src.api.schemas.study_material_schemas.node_media_schema import (
    NodeMediaAttachRequest,
    NodeMediaDeletedOut,
    NodeMediaListOut,
    NodeMediaOut,
    NodeMediaReorderRequest,
)
from src.api.schemas.study_material_schemas.reference_material_schema import (
    ReferenceImageListOut,
    ReferenceImageOut,
    ReferenceMaterialDeletedOut,
    ReferenceMaterialListOut,
    ReferenceMaterialOut,
    ReferenceMaterialScope,
    ReferenceMaterialVisibilityUpdate,
)
from src.api.utils.reference_media_utils.media_url_utils import storage_path_to_url
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_mentor,
    _assert_space_access,
    _get_node_and_assert_space_access,
    _get_space_and_assert_owner,
)
from src.api.utils.study_agent_utils.media_response import build_node_media_out

_UPLOAD_ROOT = Path("/app/uploads/reference_materials")


def _reference_image_items(
    images: list[ReferenceLlamaParseImage],
) -> list[ReferenceImageOut]:
    return [
        ReferenceImageOut(
            llamaparse_image_id=image.llamaparse_image_id,
            filename=image.filename,
            title=image.title,
            url=storage_path_to_url(image.file_url),
            source_page=image.source_page_number,
        )
        for image in images
    ]


async def _save_file_locally(
    file: UploadFile,
    space_id: UUID,
    node_id: UUID | None,
    material_id: UUID,
) -> str:
    """Save uploaded file to the local uploads directory and return the absolute path."""
    scope_dir = str(node_id) if node_id else "space"
    dest_dir = _UPLOAD_ROOT / str(space_id) / scope_dir
    dest_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename or "upload").name
    dest_path = dest_dir / f"{material_id}_{safe_name}"

    contents = await file.read()
    dest_path.write_bytes(contents)
    await file.seek(0)

    return str(dest_path)


class ReferenceMaterialService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Reference Materials ────────────────────────────────────────────

    async def upload_reference_material(
        self,
        space_id: UUID,
        file: UploadFile,
        title: str,
        scope: ReferenceMaterialScope,
        node_id: UUID | None,
        is_visible_to_trainees: bool,
        user_id: UUID,
        role: str,
    ) -> ReferenceMaterialOut:
        """Upload a reference material to GCS and insert the DB row."""
        _assert_mentor(role)
        await _get_space_and_assert_owner(self.session, space_id, user_id)

        # scope / node_id cross-field guard
        if scope == "node" and node_id is None:
            raise ReferenceMaterialNodeScopeMismatchException()
        if scope == "space" and node_id is not None:
            raise ReferenceMaterialNodeScopeMismatchException()

        material_id = uuid4()
        file_url = await _save_file_locally(file, space_id, node_id, material_id)

        content = await file.read()
        file_size = len(content)
        await file.seek(0)

        repo = ReferenceMaterialRepository(self.session)
        material = await repo.create_reference_material_with_id(
            material_id=material_id,
            space_id=space_id,
            node_id=node_id,
            title=title,
            scope=scope,
            file_url=file_url,
            file_name=file.filename or "upload",
            file_size_bytes=file_size,
            mime_type=file.content_type or "application/octet-stream",
            is_visible_to_trainees=is_visible_to_trainees,
            uploaded_by=user_id,
        )
        return ReferenceMaterialOut.model_validate(material)

    async def list_by_space(
        self, space_id: UUID, user_id: UUID, role: str
    ) -> ReferenceMaterialListOut:
        """List active reference materials scoped to a space."""
        await _assert_space_access(self.session, space_id, user_id, role)

        repo = ReferenceMaterialRepository(self.session)
        items = await repo.get_by_space(space_id)
        return ReferenceMaterialListOut(
            items=[ReferenceMaterialOut.model_validate(i) for i in items],
            total=len(items),
        )

    async def list_by_node(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> ReferenceMaterialListOut:
        """List active reference materials scoped to a node."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = ReferenceMaterialRepository(self.session)
        items = await repo.get_by_node(node_id)
        return ReferenceMaterialListOut(
            items=[ReferenceMaterialOut.model_validate(i) for i in items],
            total=len(items),
        )

    async def get_latest_by_node(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> ReferenceMaterialOut | None:
        """Return the most recently uploaded node-scoped reference material."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = ReferenceMaterialRepository(self.session)
        material = await repo.get_latest_by_node(node_id)
        if material is None:
            return None
        return ReferenceMaterialOut.model_validate(material)

    async def update_visibility(
        self,
        material_id: UUID,
        request: ReferenceMaterialVisibilityUpdate,
        user_id: UUID,
        role: str,
    ) -> ReferenceMaterialOut:
        """Toggle is_visible_to_trainees. Only mutable post-upload field (EC-17)."""
        _assert_mentor(role)
        repo = ReferenceMaterialRepository(self.session)
        material = await repo.get_by_id(material_id)

        if material is None or material.deleted_at is not None:
            raise ReferenceMaterialNotFoundForDeleteException()

        await _get_space_and_assert_owner(self.session, material.space_id, user_id)

        material = await repo.update_visibility(
            material, request.is_visible_to_trainees
        )
        return ReferenceMaterialOut.model_validate(material)

    async def delete_reference_material(
        self, material_id: UUID, user_id: UUID, role: str
    ) -> ReferenceMaterialDeletedOut:
        """Soft-delete a reference material (set deleted_at)."""
        _assert_mentor(role)
        repo = ReferenceMaterialRepository(self.session)
        material = await repo.get_by_id(material_id)

        if material is None or material.deleted_at is not None:
            raise ReferenceMaterialNotFoundForDeleteException()

        await _get_space_and_assert_owner(self.session, material.space_id, user_id)

        await repo.soft_delete(material)
        return ReferenceMaterialDeletedOut(material_id=material_id)

    # ── Node Media ─────────────────────────────────────────────────────

    async def attach_media(
        self,
        node_id: UUID,
        request: NodeMediaAttachRequest,
        file: UploadFile | None,
        user_id: UUID,
        role: str,
    ) -> NodeMediaOut:
        """Attach a media item to a node. Cross-field type/url guard at service layer."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        # Cross-field validation
        if request.media_type == "image" and file is None:
            raise InvalidMediaTypePayloadException()
        if request.media_type in ("video_url", "article_link") and not request.url:
            raise InvalidMediaTypePayloadException()

        file_url: str | None = None
        url: str | None = request.url

        if request.media_type == "image" and file is not None:
            file_url = (
                f"https://storage.googleapis.com/studyguru-placeholder/{file.filename}"
            )
            url = None

        repo = ReferenceMaterialRepository(self.session)
        next_order = await repo.get_next_media_order_index(node_id)

        media = await repo.create_media(
            node_id=node_id,
            space_id=node.space_id,
            media_type=request.media_type,
            title=request.title,
            url=url,
            file_url=file_url,
            order_index=next_order,
            uploaded_by=user_id,
        )
        return build_node_media_out(media)

    async def list_media(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
        reference_material_id: UUID | None = None,
    ) -> NodeMediaListOut | ReferenceImageListOut:
        """List mentor media for a node, or LlamaParse figures for one reference PDF."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        if reference_material_id is not None:
            material_repo = ReferenceMaterialRepository(self.session)
            material = await material_repo.get_by_id(reference_material_id)

            if material is None or material.deleted_at is not None:
                raise ReferenceMaterialNotFoundForDeleteException()

            if material.node_id is not None:
                await _get_node_and_assert_space_access(
                    self.session, material.node_id, user_id, owner_only=False
                )
            else:
                await _assert_space_access(
                    self.session, material.space_id, user_id, role
                )

            parse_repo = ReferenceLlamaParseRepository(self.session)
            images = await parse_repo.list_images_by_reference_and_node(
                reference_material_id, node_id
            )
            items = _reference_image_items(images)
            return ReferenceImageListOut(
                material_id=reference_material_id,
                node_id=node_id,
                items=items,
                total=len(items),
            )

        repo = ReferenceMaterialRepository(self.session)
        items = await repo.get_media_by_node(node_id)
        return NodeMediaListOut(
            items=[build_node_media_out(i) for i in items],
            total=len(items),
        )

    async def reorder_media(
        self,
        node_id: UUID,
        request: NodeMediaReorderRequest,
        user_id: UUID,
        role: str,
    ) -> dict[str, object]:
        """Bulk-update order_index. Payload must include all active media_ids."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = ReferenceMaterialRepository(self.session)
        all_active = await repo.get_media_by_node(node_id)
        all_active_ids = {m.media_id for m in all_active}
        payload_ids = set(request.media_ids)

        if all_active_ids != payload_ids:
            raise NodeMediaReorderIncompleteException()

        order_map = {mid: idx for idx, mid in enumerate(request.media_ids)}
        await repo.bulk_update_media_order(order_map)

        return {"detail": "Media reordered successfully."}

    async def delete_media(
        self, node_id: UUID, media_id: UUID, user_id: UUID, role: str
    ) -> NodeMediaDeletedOut:
        """Hard-delete a media item from a node."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = ReferenceMaterialRepository(self.session)
        media = await repo.get_media_by_id(media_id)
        if media is None or media.node_id != node_id:
            raise NodeMediaNotFoundException()

        await repo.delete_media(media)
        return NodeMediaDeletedOut(media_id=media_id)
