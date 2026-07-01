from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import UUID

from src.api.config import settings
from src.api.data.models.postgres.e_learning_content.node_media import NodeMedia
from src.api.data.models.postgres.e_learning_content.reference_materials import (
    ReferenceMaterial,
)
from src.api.schemas.study_material_schemas import (
    TraineeTopicResourceOut,
)
from src.api.schemas.study_material_schemas.node_media_schema import NodeMediaType

_MEDIA_TYPE_LABELS: dict[str, str] = {
    "image": "Image",
    "pdf": "PDF",
    "video_url": "Video",
    "article_link": "Link",
}


def _api_url(path: str) -> str:
    return f"{settings.media_base_url.rstrip('/')}{path}"


def _storage_filename(file_url: str) -> str:
    name = Path(file_url.replace("\\", "/")).name
    if "_" in name:
        return name.split("_", 1)[1]
    return name


def _default_title(media: NodeMedia) -> str:
    if media.title and str(media.title).strip():
        return str(media.title).strip()
    if media.url:
        return str(media.url)
    if media.file_url:
        return _storage_filename(str(media.file_url))
    return str(_MEDIA_TYPE_LABELS.get(media.media_type, "Resource"))


def build_trainee_topic_resource_out(
    media: NodeMedia,
    *,
    node_id: UUID,
) -> TraineeTopicResourceOut:
    display_title = _default_title(media)
    subtitle: str | None = None
    view_action_label = "Open"
    download_action_label: str | None = None
    view_url: str
    download_url: str | None = None
    download_filename: str | None = None
    mime_type: str | None = None
    is_downloadable = False

    if media.media_type in ("image", "pdf") and media.file_url:
        filename = _storage_filename(media.file_url)
        mime_type = mimetypes.guess_type(filename)[0] or (
            "application/pdf" if media.media_type == "pdf" else "image/jpeg"
        )
        download_filename = filename
        file_path = _api_url(
            f"/trainee/nodes/{node_id}/topic-resources/{media.media_id}/file"
        )
        download_path = _api_url(
            f"/trainee/nodes/{node_id}/topic-resources/{media.media_id}/download"
        )
        view_url = file_path
        download_url = download_path
        subtitle = filename
        is_downloadable = True
        view_action_label = "View" if media.media_type == "image" else "Open"
        download_action_label = "Download"
    elif media.url:
        view_url = media.url
        subtitle = media.url
        view_action_label = "Watch" if media.media_type == "video_url" else "Open link"
    else:
        view_url = ""
        subtitle = None

    return TraineeTopicResourceOut(
        media_id=media.media_id,
        media_type=media.media_type,
        type_label=_MEDIA_TYPE_LABELS.get(media.media_type, "Resource"),
        display_title=display_title,
        subtitle=subtitle,
        view_action_label=view_action_label,
        download_action_label=download_action_label,
        view_url=view_url,
        download_url=download_url,
        download_filename=download_filename,
        mime_type=mime_type,
        is_downloadable=is_downloadable,
        order_index=media.order_index,
    )


def _reference_media_type(mime_type: str) -> NodeMediaType:
    if mime_type == "application/pdf":
        return "pdf"
    return "pdf"


def _reference_type_label(mime_type: str) -> str:
    if mime_type == "application/pdf":
        return "PDF"
    if "word" in mime_type or mime_type.endswith("document"):
        return "Document"
    if "presentation" in mime_type or "powerpoint" in mime_type:
        return "Slides"
    return "Document"


def build_trainee_topic_resource_from_reference(
    material: ReferenceMaterial,
    *,
    node_id: UUID,
    order_index: int,
) -> TraineeTopicResourceOut:
    filename = material.file_name
    mime_type = (
        material.mime_type
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )
    media_type = _reference_media_type(mime_type)
    file_path = _api_url(
        f"/trainee/nodes/{node_id}/topic-resources/reference/{material.material_id}/file"
    )
    download_path = _api_url(
        f"/trainee/nodes/{node_id}/topic-resources/reference/{material.material_id}/download"
    )
    return TraineeTopicResourceOut(
        media_id=material.material_id,
        media_type=media_type,
        type_label=_reference_type_label(mime_type),
        display_title=material.title,
        subtitle=filename,
        view_action_label="Open" if media_type == "pdf" else "View",
        download_action_label="Download",
        view_url=file_path,
        download_url=download_path,
        download_filename=filename,
        mime_type=mime_type,
        is_downloadable=True,
        order_index=order_index,
    )
