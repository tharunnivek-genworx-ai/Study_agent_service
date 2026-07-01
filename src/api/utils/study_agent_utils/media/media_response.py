"""Build API response models with resolved public media URLs."""

from __future__ import annotations

from src.api.data.models.postgres.e_learning_content.node_media import NodeMedia
from src.api.schemas.study_material_schemas import NodeMediaOut
from src.api.utils.reference_media_utils.media_url_utils import storage_path_to_url


def build_node_media_out(media: NodeMedia) -> NodeMediaOut:
    out = NodeMediaOut.model_validate(media)
    if media.file_url:
        return out.model_copy(
            update={"public_url": storage_path_to_url(media.file_url)}
        )
    if media.url:
        return out.model_copy(update={"public_url": media.url})
    return out
