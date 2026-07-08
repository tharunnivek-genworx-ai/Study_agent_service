"""Public facade routing uploads and downloads between local disk and GCS."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from src.api.config import settings
from src.api.utils.storage import gcs_storage, local_storage
from src.api.utils.storage.media_access_token import media_access_url


def _use_gcs() -> bool:
    return settings.storage_backend == "gcs"


def _normalized_prefix() -> str:
    return settings.gcs_prefix.strip("/")


def _safe_filename(filename: str) -> str:
    return Path(filename).name


def build_reference_material_key(
    space_id: UUID,
    node_id: UUID | None,
    material_id: UUID,
    filename: str,
) -> str:
    scope_dir = str(node_id) if node_id else "space"
    safe_name = _safe_filename(filename)
    return (
        f"{_normalized_prefix()}/reference_materials/"
        f"{space_id}/{scope_dir}/{material_id}_{safe_name}"
    )


def build_node_media_key(
    space_id: UUID,
    node_id: UUID,
    media_id: UUID,
    filename: str,
) -> str:
    safe_name = _safe_filename(filename)
    return (
        f"{_normalized_prefix()}/node_media/{space_id}/{node_id}/{media_id}_{safe_name}"
    )


def build_llamaparse_image_key(
    material_id: UUID,
    node_id: UUID,
    stamp: str,
    filename: str,
) -> str:
    safe_name = _safe_filename(filename)
    return (
        f"{_normalized_prefix()}/reference_llamaparse/"
        f"{material_id}/{node_id}/images_{stamp}/{safe_name}"
    )


def is_local_path(storage_ref: str) -> bool:
    normalized = storage_ref.replace("\\", "/")
    return normalized.startswith("/app/") or (
        Path(normalized).is_absolute() and not normalized.startswith("http")
    )


async def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    """Upload bytes and return the DB storage reference (object key or local path)."""
    if _use_gcs():
        return await asyncio.to_thread(
            gcs_storage.upload_bytes, key, data, content_type
        )
    return await asyncio.to_thread(local_storage.upload_bytes, key, data, content_type)


def upload_bytes_sync(key: str, data: bytes, content_type: str) -> str:
    """Synchronous upload for callers running outside an event loop."""
    if _use_gcs():
        return gcs_storage.upload_bytes(key, data, content_type)
    return local_storage.upload_bytes(key, data, content_type)


async def download_bytes(storage_ref: str) -> bytes:
    """Download file bytes from local disk or GCS."""
    if is_local_path(storage_ref):
        return await asyncio.to_thread(local_storage.download_bytes, storage_ref)
    if _use_gcs():
        return await asyncio.to_thread(gcs_storage.download_bytes, storage_ref)
    return await asyncio.to_thread(local_storage.download_bytes, storage_ref)


async def exists(storage_ref: str) -> bool:
    """Return True when the storage reference is readable."""
    if is_local_path(storage_ref):
        return await asyncio.to_thread(local_storage.exists, storage_ref)
    if _use_gcs():
        return await asyncio.to_thread(gcs_storage.exists, storage_ref)
    return await asyncio.to_thread(local_storage.exists, storage_ref)


def generate_signed_url(storage_ref: str) -> str:
    """Return a signed GCS URL for an object key."""
    return gcs_storage.generate_signed_url(storage_ref)


def _local_public_url(storage_ref: str) -> str:
    root = settings.media_base_url.rstrip("/")
    normalized = storage_ref.replace("\\", "/")
    marker = "/uploads/"
    idx = normalized.find(marker)
    if idx != -1:
        return f"{root}{normalized[idx:]}"
    if normalized.startswith("/app/"):
        return f"{root}{normalized[len('/app') :]}"
    return normalized


def resolve_public_url(storage_ref: str) -> str:
    """Return a browser-loadable URL (app media token URL or local /uploads URL)."""
    if is_local_path(storage_ref):
        return _local_public_url(storage_ref)
    if _use_gcs():
        return media_access_url(storage_ref)
    return _local_public_url(storage_ref)
