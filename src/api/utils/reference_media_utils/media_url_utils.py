"""Convert on-disk upload paths to browser-loadable URLs."""

from __future__ import annotations

from src.api.config.dbconfig import settings


def storage_path_to_url(storage_path: str, base_url: str | None = None) -> str:
    """Convert an on-disk uploads path to a browser-loadable URL."""
    root = base_url or settings.media_base_url
    normalized = storage_path.replace("\\", "/")
    marker = "/uploads/"
    idx = normalized.find(marker)
    if idx != -1:
        return f"{root.rstrip('/')}{normalized[idx:]}"
    if normalized.startswith("/app/"):
        return f"{root.rstrip('/')}{normalized[len('/app') :]}"
    return normalized
