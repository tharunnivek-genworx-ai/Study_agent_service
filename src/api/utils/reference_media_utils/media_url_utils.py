"""Convert storage references to browser-loadable URLs."""

from __future__ import annotations

from src.api.utils.storage.object_storage import resolve_public_url


def storage_path_to_url(storage_path: str, base_url: str | None = None) -> str:
    """Convert a storage reference to a browser-loadable URL."""
    del base_url
    return resolve_public_url(storage_path)
