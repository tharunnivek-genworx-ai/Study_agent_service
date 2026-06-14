"""List LlamaParse-downloaded reference figures for a reference PDF."""

from __future__ import annotations

import re
from pathlib import Path

from src.api.config.dbconfig import settings

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
_PAGE_FILENAME_RE = re.compile(
    r"page_(\d+)_(?:chart|image)_(\d+)",
    re.IGNORECASE,
)


def reference_images_dir_for_pdf(pdf_path: Path) -> Path:
    """Directory where Parse job saves figures for this PDF."""
    return pdf_path.parent / f"{pdf_path.stem}_images"


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


def _page_from_filename(filename: str) -> int | None:
    match = _PAGE_FILENAME_RE.search(filename)
    if match:
        return int(match.group(1))
    return None


def list_downloaded_reference_images(
    pdf_path: Path,
    base_url: str | None = None,
) -> list[dict[str, str | int | None]]:
    """Return metadata for every image file in the PDF's extracted images folder."""
    images_dir = reference_images_dir_for_pdf(pdf_path)
    if not images_dir.is_dir():
        return []

    resolved_base = base_url or settings.media_base_url
    records: list[dict[str, str | int | None]] = []

    for path in sorted(images_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        records.append(
            {
                "filename": path.name,
                "storage_path": str(path),
                "url": storage_path_to_url(str(path), resolved_base),
                "source_page": _page_from_filename(path.name),
            }
        )

    return records
