"""Local disk storage under /app/uploads (development and legacy paths)."""

from __future__ import annotations

from pathlib import Path

from src.api.config import settings

_LOCAL_ROOT = Path("/app/uploads")


def _strip_gcs_prefix(key: str) -> str:
    prefix = settings.gcs_prefix.strip("/")
    normalized = key.replace("\\", "/")
    marker = f"{prefix}/"
    if normalized.startswith(marker):
        return normalized[len(marker) :]
    return normalized


def key_to_local_path(key: str) -> Path:
    """Map a logical object key to an on-disk path under /app/uploads."""
    relative = _strip_gcs_prefix(key)
    return _LOCAL_ROOT / relative


def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    """Write bytes to disk and return the absolute path stored in the DB."""
    del content_type
    dest_path = key_to_local_path(key)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(data)
    return str(dest_path)


def download_bytes(storage_ref: str) -> bytes:
    """Read bytes from a local absolute path or logical key."""
    path = Path(storage_ref.replace("\\", "/"))
    if path.is_file():
        return path.read_bytes()
    return key_to_local_path(storage_ref).read_bytes()


def exists(storage_ref: str) -> bool:
    """Return True when the file exists on local disk."""
    path = Path(storage_ref.replace("\\", "/"))
    if path.is_file():
        return True
    return key_to_local_path(storage_ref).is_file()
